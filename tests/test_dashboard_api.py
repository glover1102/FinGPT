from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi.testclient import TestClient

from app.api import server as api_server
from app.api.routers import dashboard as dashboard_router


class _FakeTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    def history(self, period: str, interval: str, auto_adjust: bool = False, **kwargs):
        if interval == "5m":
            ny_tz = ZoneInfo("America/New_York")
            now_ny = datetime.now(ny_tz)
            latest = now_ny.replace(second=0, microsecond=0)
            previous_day = latest - timedelta(days=1)
            idx = pd.DatetimeIndex([
                previous_day.replace(hour=15, minute=55),
                latest - timedelta(minutes=5),
                latest,
            ])
            base = 100 + (sum(ord(ch) for ch in self.symbol) % 17)
            return pd.DataFrame({"Close": [base, base + 0.25, base + 0.5]}, index=idx)
        idx = pd.date_range("2026-01-01", periods=90, freq="B")
        base = 100 + (sum(ord(ch) for ch in self.symbol) % 17)
        closes = [base + i * 0.25 for i in range(len(idx))]
        return pd.DataFrame({"Close": closes}, index=idx)


def _fake_intraday_download(tickers, *args, **kwargs):
    symbols = list(tickers)
    ny_tz = ZoneInfo("America/New_York")
    now_ny = datetime.now(ny_tz).replace(second=0, microsecond=0)
    previous_day = now_ny - timedelta(days=1)
    idx = pd.DatetimeIndex([
        previous_day.replace(hour=15, minute=55),
        now_ny - timedelta(minutes=5),
        now_ny,
    ])
    data = {}
    for pos, symbol in enumerate(symbols):
        base = 100 + pos
        data[(symbol, "Close")] = [base, base + 1, base + 2]
        data[(symbol, "Volume")] = [1000, 1500, 2000]
    return pd.DataFrame(data, index=idx)


def _fake_stale_intraday_download(tickers, *args, **kwargs):
    symbols = list(tickers)
    idx = pd.to_datetime([
        "2026-01-05 15:50:00-05:00",
        "2026-01-06 15:55:00-05:00",
    ])
    data = {}
    for pos, symbol in enumerate(symbols):
        base = 100 + pos
        data[(symbol, "Close")] = [base, base + 1]
        data[(symbol, "Volume")] = [1000, 2000]
    return pd.DataFrame(data, index=idx)


class DashboardApiTests(unittest.TestCase):
    def test_dashboard_news_includes_category(self):
        docs = [
            {
                "title": "Rates and credit risk update",
                "source": "Example",
                "url": "https://example.com/rates",
                "published_at": "2026-04-24T00:00:00+00:00",
                "text": "summary",
            }
        ]
        client = TestClient(api_server.app)

        def fake_collect(symbol: str, *args, **kwargs):
            return symbol, docs if symbol == "TLT" else []

        with patch.object(dashboard_router, "collect_news_from_google_rss", side_effect=fake_collect):
            resp = client.get("/api/v1/dashboard/news?limit=3")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"][0]["category"], "rates_credit")
        self.assertEqual(body["items"][0]["symbol"], "TLT")

    def test_dashboard_market_returns_as_of_quant_snapshot(self):
        fake_yf = types.SimpleNamespace(Ticker=lambda symbol: _FakeTicker(symbol))
        client = TestClient(api_server.app)

        with patch.dict(sys.modules, {"yfinance": fake_yf}):
            resp = client.get("/api/v1/dashboard/market")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["provider"], "yfinance")
        self.assertGreaterEqual(body["ok_count"], 6)
        self.assertGreaterEqual(body["decision_usable_count"], 6)
        first = body["items"][0]
        self.assertEqual(first["status"], "ok")
        self.assertTrue(first["is_decision_usable"])
        self.assertEqual(first["source"], "yfinance_intraday_5m")
        self.assertIn("T", first["as_of"])
        self.assertIn(first["freshness_status"], {"fresh", "delayed", "closed"})
        self.assertIn("1d", first["returns"])
        self.assertIsInstance(first["returns"]["1d"], float)

    def test_dashboard_equity_heatmap_returns_intraday_as_of_and_freshness(self):
        fake_yf = types.SimpleNamespace(download=_fake_intraday_download)
        client = TestClient(api_server.app)

        with patch.dict(sys.modules, {"yfinance": fake_yf}):
            resp = client.get("/api/v1/dashboard/equity-heatmap?force=true")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["provider"], "yfinance")
        self.assertEqual(body["interval"], "5m")
        self.assertGreaterEqual(body["universe_size"], 200)
        self.assertEqual(body["universe_size"], len(body["items"]))
        self.assertGreater(body["ok_count"], 100)
        sectors = {item["sector"] for item in body["items"]}
        self.assertGreaterEqual(len(sectors), 10)
        self.assertIn("REAL ESTATE", sectors)
        self.assertIn("BASIC MATERIALS", sectors)
        first = body["items"][0]
        self.assertEqual(first["status"], "ok")
        self.assertTrue(first["is_decision_usable"])
        self.assertEqual(first["source"], "yfinance_intraday_5m")
        self.assertIn("industry", first)
        self.assertIn("T", first["as_of"])
        self.assertIn("change_pct", first)
        self.assertIn(first["freshness_status"], {"fresh", "delayed", "closed"})
        self.assertIn("tile_span", first)

    def test_dashboard_equity_heatmap_marks_old_prior_close_as_not_decision_usable(self):
        fake_yf = types.SimpleNamespace(download=_fake_stale_intraday_download)
        client = TestClient(api_server.app)

        with patch.dict(sys.modules, {"yfinance": fake_yf}):
            resp = client.get("/api/v1/dashboard/equity-heatmap?force=true")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["ok_count"], 0)
        self.assertGreater(body["stale_or_unavailable_count"], 0)
        first = body["items"][0]
        self.assertEqual(first["status"], "stale")
        self.assertFalse(first["is_decision_usable"])
        self.assertEqual(first["freshness_status"], "stale_prior_close")


if __name__ == "__main__":
    unittest.main()
