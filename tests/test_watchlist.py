"""Watchlist persistence + scheduler + endpoint tests."""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import server as api_server
from core.schemas.response import AnalysisResponse
from pipelines.watchlist import store as wl_store
from pipelines.watchlist import scheduler as wl_scheduler


class _TmpDataDirMixin:
    """Swap settings.data_dir into a tmp folder so the tests never touch the
    developer's real ``data/watchlist.json``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(
            wl_store,
            "load_settings",
            lambda: type("S", (), {"data_dir": Path(self.tmp.name)})(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)


class WatchlistStoreTests(_TmpDataDirMixin, unittest.TestCase):
    def _payload(self, **overrides):
        return {
            "ticker": overrides.get("ticker", "AAPL"),
            "question": overrides.get("question", "catalysts"),
            "sources": ["news"],
            "lookback_days": 14,
            "top_k": 5,
            "model": "mistral",
            **overrides,
        }

    def test_upsert_persists_and_lists(self):
        item = wl_store.upsert_item(self._payload())
        self.assertTrue(item.id)
        self.assertEqual(item.ticker, "AAPL")
        listed = wl_store.list_items()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].ticker, "AAPL")
        self.assertTrue(Path(self.tmp.name, "watchlist.json").exists())

    def test_upsert_merges_duplicate_ticker_question(self):
        first = wl_store.upsert_item(self._payload(lookback_days=7))
        second = wl_store.upsert_item(self._payload(lookback_days=30))
        self.assertEqual(first.id, second.id)
        self.assertEqual(wl_store.list_items()[0].lookback_days, 30)

    def test_delete_round_trip(self):
        item = wl_store.upsert_item(self._payload())
        self.assertTrue(wl_store.delete_item(item.id))
        self.assertFalse(wl_store.delete_item(item.id))
        self.assertEqual(wl_store.list_items(), [])

    def test_due_items_honors_interval_and_last_run(self):
        item = wl_store.upsert_item(self._payload(interval_hours=1))
        # Never run -> immediately due.
        self.assertEqual(len(wl_store.due_items()), 1)
        # Stamp a run ~2h ago; still due because elapsed > interval.
        old_ts = time.time() - 2 * 3600
        from datetime import datetime, timezone
        patched_item = wl_store.mark_run(item.id, status="success")
        # mark_run stamps `now`, so manually rewrite last_run_at to 2h ago.
        raw = json.loads(Path(self.tmp.name, "watchlist.json").read_text("utf-8"))
        raw["items"][0]["last_run_at"] = (
            datetime.fromtimestamp(old_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        )
        Path(self.tmp.name, "watchlist.json").write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(len(wl_store.due_items()), 1)

        # Fresh run (just now) -> not due.
        wl_store.mark_run(item.id, status="success")
        self.assertEqual(len(wl_store.due_items()), 0)

    def test_disabled_items_are_not_due(self):
        wl_store.upsert_item(self._payload(interval_hours=1, enabled=False))
        self.assertEqual(wl_store.due_items(), [])


class WatchlistEndpointTests(_TmpDataDirMixin, unittest.TestCase):
    def test_endpoints_crud_and_run(self):
        client = TestClient(api_server.app)

        async def fake_pipeline(request, **_):
            return AnalysisResponse(
                ticker=request.ticker,
                question=request.question,
                status="success",
                summary="ok",
                sentiment="Positive",
                conclusion="ok",
            )

        with patch.object(api_server, "run_pipeline_async", side_effect=fake_pipeline):
            # Create
            resp = client.post(
                "/api/v1/watchlist",
                json={"ticker": "msft", "question": "earnings"},
            )
            self.assertEqual(resp.status_code, 200)
            item_id = resp.json()["id"]
            self.assertEqual(resp.json()["ticker"], "MSFT")

            # List
            resp = client.get("/api/v1/watchlist")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(len(body["items"]), 1)
            self.assertIn("scheduler", body)

            # Run now
            resp = client.post(f"/api/v1/watchlist/{item_id}/run")
            self.assertEqual(resp.status_code, 200)
            run_body = resp.json()
            self.assertEqual(run_body["response"]["status"], "success")
            self.assertEqual(run_body["item"]["last_run_status"], "success")
            self.assertEqual(run_body["item"]["run_count"], 1)

            # Update
            resp = client.put(
                f"/api/v1/watchlist/{item_id}",
                json={"ticker": "MSFT", "question": "earnings", "enabled": False},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.json()["enabled"])

            # Delete
            resp = client.delete(f"/api/v1/watchlist/{item_id}")
            self.assertEqual(resp.status_code, 200)

            resp = client.get("/api/v1/watchlist")
            self.assertEqual(resp.json()["items"], [])

    def test_create_rejects_missing_ticker(self):
        client = TestClient(api_server.app)
        resp = client.post("/api/v1/watchlist", json={"question": "x"})
        self.assertEqual(resp.status_code, 400)


class WatchlistSchedulerTests(_TmpDataDirMixin, unittest.IsolatedAsyncioTestCase):
    async def test_tick_runs_due_items_and_marks_result(self):
        wl_store.upsert_item({
            "ticker": "NVDA", "question": "q", "sources": ["news"],
            "interval_hours": 1,
        })

        async def fake_pipeline(request, **_):
            return AnalysisResponse(
                ticker=request.ticker, question=request.question,
                status="success", summary="ok", sentiment="Neutral", conclusion="ok",
            )

        sched = wl_scheduler.WatchlistScheduler(poll_interval_s=5, max_parallel=2)
        with patch.object(wl_scheduler, "run_pipeline_async", side_effect=fake_pipeline):
            await sched._tick()
        item = wl_store.list_items()[0]
        self.assertEqual(item.last_run_status, "success")
        self.assertEqual(item.run_count, 1)

    async def test_scheduler_survives_pipeline_exceptions(self):
        wl_store.upsert_item({
            "ticker": "TSLA", "question": "q", "sources": ["news"],
            "interval_hours": 1,
        })

        async def failing(request, **_):
            raise RuntimeError("ollama down")

        sched = wl_scheduler.WatchlistScheduler()
        with patch.object(wl_scheduler, "run_pipeline_async", side_effect=failing):
            await sched._tick()
        item = wl_store.list_items()[0]
        self.assertEqual(item.last_run_status, "failed")
        self.assertIn("ollama down", item.last_run_error)


if __name__ == "__main__":
    unittest.main()
