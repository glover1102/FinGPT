from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Optional

from core.config.settings import load_settings
from core.schemas.ai_portfolio import SecDataRefreshRequest
from core.utils.logger import get_logger

logger = get_logger("pipelines.data_mart.scheduler")


class DataMartRefreshScheduler:
    def __init__(self) -> None:
        settings = load_settings()
        explicit_enabled = os.getenv("DATA_MART_AUTO_REFRESH_ENABLED")
        self._enabled = bool(getattr(settings, "data_mart_auto_refresh_enabled", True))
        if explicit_enabled is None and os.getenv("PYTEST_CURRENT_TEST"):
            self._enabled = False
        self._sec_enabled = bool(getattr(settings, "data_mart_auto_refresh_sec_enabled", True))
        self._macro_enabled = bool(getattr(settings, "data_mart_auto_refresh_macro_enabled", True))
        interval_hours = float(getattr(settings, "data_mart_auto_refresh_interval_hours", 24.0) or 24.0)
        self._interval_s = max(3600.0, interval_hours * 3600.0)
        self._initial_delay_s = max(0.0, float(getattr(settings, "data_mart_auto_refresh_initial_delay_s", 120.0) or 0.0))
        self._poll_interval_s = min(300.0, max(30.0, self._initial_delay_s or 60.0))
        self._universe_id = str(getattr(settings, "data_mart_auto_refresh_universe_id", "all_supported") or "all_supported")
        self._max_assets = max(1, int(getattr(settings, "data_mart_auto_refresh_max_assets", 250) or 250))
        self._sec_lookback_days = max(1, int(getattr(settings, "data_mart_auto_refresh_sec_lookback_days", 365 * 3) or 365 * 3))
        self._macro_lookback_days = max(1, int(getattr(settings, "data_mart_auto_refresh_macro_lookback_days", 365 * 5) or 365 * 5))
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._started_at: Optional[float] = None
        self._last_poll_at: Optional[float] = None
        self._last_run_at: Optional[float] = None
        self._next_run_at: Optional[float] = None
        self._runs_triggered = 0
        self._last_result: dict | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "running": self.running,
            "interval_s": self._interval_s,
            "initial_delay_s": self._initial_delay_s,
            "jobs": {
                "sec_company_data": self._sec_enabled,
                "macro_platform_data": self._macro_enabled,
            },
            "universe_id": self._universe_id,
            "max_assets": self._max_assets,
            "sec_lookback_days": self._sec_lookback_days,
            "macro_lookback_days": self._macro_lookback_days,
            "started_at": self._started_at,
            "last_poll_at": self._last_poll_at,
            "last_run_at": self._last_run_at,
            "next_run_at": self._next_run_at,
            "runs_triggered": self._runs_triggered,
            "last_result": self._last_result,
        }

    async def start(self) -> None:
        if not self._enabled:
            logger.info("[DATA_MART_SCHED] disabled")
            return
        if self.running:
            return
        self._stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        self._started_at = loop.time()
        self._next_run_at = self._started_at + self._initial_delay_s
        self._task = asyncio.create_task(self._loop(), name="data-mart-refresh-scheduler")
        logger.info("[DATA_MART_SCHED] started interval=%ss universe=%s", self._interval_s, self._universe_id)

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None
        logger.info("[DATA_MART_SCHED] stopped")

    async def run_once(self) -> dict:
        from pipelines.ai_portfolio.service import run_sec_data_refresh
        from pipelines.data_mart.jobs.update_macro_daily import update_macro_platform_data
        from pipelines.macro import macro_service

        result: dict = {"status": "success", "jobs": {}}
        if self._sec_enabled:
            request = SecDataRefreshRequest(
                universe_id=self._universe_id,
                max_assets=self._max_assets,
                lookback_days=self._sec_lookback_days,
                hydrate_financials=True,
            )
            sec_result = await asyncio.to_thread(run_sec_data_refresh, request)
            result["jobs"]["sec_company_data"] = {
                "operation_id": sec_result.get("operation_id"),
                "status": sec_result.get("status"),
                "created_at": sec_result.get("created_at"),
                "ticker_count": sec_result.get("ticker_count"),
                "sec_result": sec_result.get("sec_result"),
            }
        if self._macro_enabled:
            macro_result = await asyncio.to_thread(update_macro_platform_data, lookback_days=self._macro_lookback_days)
            macro_service.clear_macro_caches()
            result["jobs"]["macro_platform_data"] = {
                "run_id": macro_result.run_id,
                "status": macro_result.status,
                "rows_inserted": macro_result.rows_inserted,
                "rows_updated": macro_result.rows_updated,
                "providers": [
                    {
                        "provider": provider.provider,
                        "status": provider.status,
                        "rows": provider.rows,
                        "error": provider.error,
                        "detail": provider.detail,
                    }
                    for provider in macro_result.providers
                ],
            }
        statuses = [
            str(job.get("status") or "").lower()
            for job in result["jobs"].values()
            if isinstance(job, dict)
        ]
        if statuses and any(status == "failed" for status in statuses):
            result["status"] = "failed"
        elif statuses and any(status in {"partial", "unavailable"} for status in statuses):
            result["status"] = "partial"
        elif not statuses:
            result["status"] = "skipped"
        loop = asyncio.get_event_loop()
        self._last_run_at = loop.time()
        self._next_run_at = self._last_run_at + self._interval_s
        self._runs_triggered += 1
        self._last_result = result
        return result

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
            logger.exception("[DATA_MART_SCHED] loop crashed: %s", exc)

    async def _tick(self) -> None:
        loop = asyncio.get_event_loop()
        now = loop.time()
        self._last_poll_at = now
        if self._next_run_at is None:
            self._next_run_at = now + self._initial_delay_s
        if now < self._next_run_at:
            return
        try:
            await self.run_once()
        except Exception as exc:  # noqa: BLE001
            self._last_result = {"status": "failed", "error": str(exc)}
            self._next_run_at = now + min(self._interval_s, 3600.0)
            logger.exception("[DATA_MART_SCHED] refresh failed: %s", exc)


_scheduler: Optional[DataMartRefreshScheduler] = None


def get_scheduler() -> DataMartRefreshScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = DataMartRefreshScheduler()
    return _scheduler
