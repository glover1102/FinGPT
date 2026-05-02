"""Minimal in-process watchlist scheduler.

A single ``asyncio.Task`` polls the watchlist every ``poll_interval_s`` seconds,
picks up items whose ``interval_hours`` has elapsed, and runs the standard
research pipeline via ``run_pipeline_async``. Results flow through the normal
run-history archival path, so scheduled runs appear in the UI's history panel
just like manual runs.

Why not APScheduler/celery?
  - The project is explicitly single-machine, single-user. A stdlib-only task
    keeps dependencies minimal and avoids the operational surface area of a
    real job runner.
  - Runs are coarse (hours, not seconds). A 60-second wakeup loop is plenty
    precise for the stated use case ("morning check on my 5 watchlist names").

Concurrency & safety:
  - ``_semaphore`` caps simultaneous pipeline runs so the scheduler can't
    starve the interactive UI requests when several items come due at once.
  - Pipeline exceptions are caught per-item; the loop never dies from one bad
    run. Failures are persisted via ``store.mark_run(status="failed", ...)``.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Optional

from core.schemas.request import AnalysisRequest
from core.utils.logger import get_logger
from pipelines.orchestration.research_pipeline import run_pipeline_async
from pipelines.watchlist import store

logger = get_logger("pipelines.watchlist.scheduler")


class WatchlistScheduler:
    def __init__(self, *, poll_interval_s: float = 60.0, max_parallel: int = 1) -> None:
        self._poll_interval_s = max(5.0, float(poll_interval_s))
        self._max_parallel = max(1, int(max_parallel))
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(self._max_parallel)
        self._started_at: Optional[float] = None
        self._last_poll_at: Optional[float] = None
        self._runs_triggered: int = 0

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "running": self.running,
            "poll_interval_s": self._poll_interval_s,
            "max_parallel": self._max_parallel,
            "started_at": self._started_at,
            "last_poll_at": self._last_poll_at,
            "runs_triggered": self._runs_triggered,
        }

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        self._started_at = loop.time()
        self._task = asyncio.create_task(self._loop(), name="watchlist-scheduler")
        logger.info("[WATCHLIST_SCHED] started (poll=%ss)", self._poll_interval_s)

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None
        logger.info("[WATCHLIST_SCHED] stopped")

    async def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await self._tick()
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_s)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("[WATCHLIST_SCHED] loop crashed: %s", exc)

    async def _tick(self) -> None:
        loop = asyncio.get_event_loop()
        self._last_poll_at = loop.time()
        try:
            due = store.due_items()
        except Exception as exc:  # noqa: BLE001
            logger.error("[WATCHLIST_SCHED] failed to read watchlist: %s", exc)
            return
        if not due:
            return
        logger.info("[WATCHLIST_SCHED] %d items due", len(due))
        # Run concurrently under the semaphore so the interactive UI stays
        # responsive even when several items come due at the same wakeup.
        await asyncio.gather(*(self._run_item(item) for item in due), return_exceptions=True)

    async def _run_item(self, item: store.WatchlistItem) -> None:
        async with self._semaphore:
            self._runs_triggered += 1
            try:
                request = AnalysisRequest(
                    ticker=item.ticker,
                    question=item.question,
                    sources=list(item.sources),
                    lookback_days=item.lookback_days,
                    top_k=item.top_k,
                    model=item.model,
                )
                logger.info("[WATCHLIST_SCHED] running id=%s ticker=%s", item.id, item.ticker)
                response = await run_pipeline_async(request)
                store.mark_run(item.id, status=response.status, error=response.error_metadata, run_id=None)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[WATCHLIST_SCHED] run failed id=%s: %s", item.id, exc)
                store.mark_run(item.id, status="failed", error=str(exc))


# Lazy singleton so ``start_scheduler`` is idempotent even across uvicorn reloads.
_scheduler: Optional[WatchlistScheduler] = None


def get_scheduler() -> WatchlistScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = WatchlistScheduler()
    return _scheduler
