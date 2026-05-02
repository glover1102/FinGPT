"""Compare endpoint tests.

These stub out ``run_pipeline_async`` so we can verify batch orchestration
(dedupe, per-ticker error isolation, concurrency cap) without touching any
external service.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import server as api_server
from core.schemas.response import AnalysisResponse


def _mk_response(ticker: str, status: str = "success") -> AnalysisResponse:
    return AnalysisResponse(
        ticker=ticker,
        question="q",
        status=status,
        summary=f"{ticker} summary",
        sentiment="Neutral",
        confidence=0.5,
        conclusion=f"{ticker} conclusion",
    )


class CompareEndpointTests(unittest.TestCase):
    def test_returns_result_per_ticker_and_dedupes(self):
        async def fake(request, **_):
            await asyncio.sleep(0)
            return _mk_response(request.ticker)

        with patch.object(api_server, "run_pipeline_async", side_effect=fake):
            client = TestClient(api_server.app)
            resp = client.post(
                "/api/v1/research/compare",
                json={
                    "tickers": ["aapl", "MSFT", "aapl", " nvda "],
                    "question": "Share catalysts",
                    "sources": ["news"],
                    "lookback_days": 14,
                    "top_k": 5,
                    "model": "mistral",
                    "concurrency": 2,
                },
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tickers"], ["AAPL", "MSFT", "NVDA"])
        self.assertEqual(set(body["results"].keys()), {"AAPL", "MSFT", "NVDA"})
        for t in ("AAPL", "MSFT", "NVDA"):
            self.assertEqual(body["results"][t]["status"], "success")
            self.assertEqual(body["results"][t]["ticker"], t)
        # Local Ollama JSON generation is serialized even when a higher
        # request-level concurrency is supplied.
        self.assertEqual(body["concurrency"], 1)
        self.assertGreaterEqual(body["elapsed_s"], 0.0)

    def test_individual_failures_do_not_abort_batch(self):
        async def fake(request, **_):
            if request.ticker == "MSFT":
                raise RuntimeError("simulated ollama timeout")
            return _mk_response(request.ticker)

        with patch.object(api_server, "run_pipeline_async", side_effect=fake):
            client = TestClient(api_server.app)
            resp = client.post(
                "/api/v1/research/compare",
                json={
                    "tickers": ["AAPL", "MSFT"],
                    "question": "q",
                },
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["results"]["AAPL"]["status"], "success")
        self.assertEqual(body["results"]["MSFT"]["status"], "failed")
        self.assertIn("simulated ollama timeout", body["results"]["MSFT"]["error_metadata"])

    def test_rejects_single_ticker(self):
        client = TestClient(api_server.app)
        resp = client.post(
            "/api/v1/research/compare",
            json={"tickers": ["AAPL"], "question": "q"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_rejects_too_many_tickers(self):
        client = TestClient(api_server.app)
        resp = client.post(
            "/api/v1/research/compare",
            json={"tickers": ["A", "B", "C", "D", "E", "F"], "question": "q"},
        )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
