import unittest
from unittest.mock import Mock, patch

import httpx

from pipelines.collect import fmp_news


def _response(status_code: int, payload=None, text: str = ""):
    response = Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload if payload is not None else []
    return response


class FmpNewsTests(unittest.TestCase):
    def test_collect_stock_news_normalizes_success_payload(self):
        payload = [
            {
                "title": "Microsoft expands Azure AI",
                "text": "Microsoft (MSFT) announced new Azure AI services for enterprise customers.",
                "publishedDate": "2026-04-20T10:00:00Z",
                "site": "FMP",
                "url": "https://example.com/msft",
            }
        ]

        with patch.object(fmp_news, "_now", return_value=fmp_news.datetime(2026, 4, 21, 0, 0, 0)), \
             patch.object(fmp_news.httpx, "get", return_value=_response(200, payload)):
            result, documents = fmp_news.collect_stock_news_from_fmp("MSFT", 7, "test-key", limit=10)

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["source"], "FMP")
        self.assertEqual(documents[0]["doc_type"], "news")
        self.assertIn("collected_at", documents[0])

    def test_collect_stock_news_classifies_402_as_entitlement_required(self):
        with patch.object(fmp_news.httpx, "get", return_value=_response(402, text="upgrade required")):
            result, documents = fmp_news.collect_stock_news_from_fmp("MSFT", 7, "test-key")

        self.assertEqual(result.status, "entitlement_required")
        self.assertEqual(documents, [])
        self.assertIn("entitlement", result.detail.lower())

    def test_collect_stock_news_filters_old_and_unparseable_dates(self):
        payload = [
            {
                "title": "Old Microsoft story",
                "text": "Microsoft (MSFT) old story.",
                "publishedDate": "2026-03-01T10:00:00Z",
            },
            {
                "title": "Undated Microsoft story",
                "text": "Microsoft (MSFT) undated story.",
                "publishedDate": "not-a-date",
            },
        ]

        with patch.object(fmp_news, "_now", return_value=fmp_news.datetime(2026, 4, 21, 0, 0, 0)), \
             patch.object(fmp_news.httpx, "get", return_value=_response(200, payload)):
            result, documents = fmp_news.collect_stock_news_from_fmp("MSFT", 7, "test-key")

        self.assertEqual(result.status, "empty")
        self.assertEqual(documents, [])
        self.assertIn("published_at", result.detail)

    def test_collect_stock_news_returns_timeout_on_http_timeout(self):
        with patch.object(fmp_news.httpx, "get", side_effect=httpx.TimeoutException("slow")):
            result, documents = fmp_news.collect_stock_news_from_fmp("MSFT", 7, "test-key")

        self.assertEqual(result.status, "timeout")
        self.assertEqual(documents, [])


if __name__ == "__main__":
    unittest.main()
