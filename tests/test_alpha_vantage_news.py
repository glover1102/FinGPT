from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import httpx

from pipelines.collect import alpha_vantage_news


def _response(status_code: int, payload=None, text: str = ""):
    response = Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload if payload is not None else {}
    return response


class AlphaVantageNewsTests(unittest.TestCase):
    def test_collect_news_normalizes_success_payload(self):
        payload = {
            "feed": [
                {
                    "title": "Microsoft credit risk remains contained",
                    "summary": "Microsoft (MSFT) balance sheet strength offsets near-term credit risk concerns.",
                    "time_published": "20260420T100000",
                    "source": "Example Wire",
                    "url": "https://example.com/msft-credit",
                }
            ]
        }

        with patch.object(alpha_vantage_news, "_now", return_value=alpha_vantage_news.datetime(2026, 4, 21, 0, 0, 0)), \
             patch.object(alpha_vantage_news.httpx, "get", return_value=_response(200, payload)):
            result, documents = alpha_vantage_news.collect_news_from_alpha_vantage("MSFT", 7, "test-key")

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["source"], "Example Wire")
        self.assertEqual(documents[0]["doc_type"], "news")
        self.assertIn("collected_at", documents[0])

    def test_collect_news_classifies_rate_limit_message(self):
        payload = {"Information": "API rate limit reached."}

        with patch.object(alpha_vantage_news.httpx, "get", return_value=_response(200, payload)):
            result, documents = alpha_vantage_news.collect_news_from_alpha_vantage("MSFT", 7, "test-key")

        self.assertEqual(result.status, "rate_limited")
        self.assertEqual(documents, [])

    def test_collect_news_returns_timeout_on_http_timeout(self):
        with patch.object(alpha_vantage_news.httpx, "get", side_effect=httpx.TimeoutException("slow")):
            result, documents = alpha_vantage_news.collect_news_from_alpha_vantage("MSFT", 7, "test-key")

        self.assertEqual(result.status, "timeout")
        self.assertEqual(documents, [])


if __name__ == "__main__":
    unittest.main()
