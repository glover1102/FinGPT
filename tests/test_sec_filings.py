import unittest
from unittest.mock import Mock, patch

import httpx

from pipelines.collect import sec_filings


def _response(status_code: int, payload=None, text: str = ""):
    response = Mock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload if payload is not None else {}
    return response


def _ticker_payload():
    return {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [
            [789019, "MICROSOFT CORP", "MSFT", "Nasdaq"],
        ],
    }


def _submissions_payload(filing_date: str = "2026-04-20"):
    return {
        "name": "MICROSOFT CORP",
        "filings": {
            "recent": {
                "accessionNumber": ["0000789019-26-000001"],
                "filingDate": [filing_date],
                "reportDate": [filing_date],
                "form": ["8-K"],
                "primaryDocument": ["msft-20260420.htm"],
                "primaryDocDescription": ["Current report"],
            }
        },
    }


class SecFilingsTests(unittest.TestCase):
    def test_collect_sec_filings_normalizes_recent_submission(self):
        responses = [
            _response(200, _ticker_payload()),
            _response(200, _submissions_payload()),
        ]

        with patch.object(sec_filings, "_now", return_value=sec_filings.datetime(2026, 4, 21, 0, 0, 0)), \
             patch.object(sec_filings.httpx, "get", side_effect=responses):
            result, documents = sec_filings.collect_sec_filings_as_news(
                "MSFT",
                lookback_days=7,
                sec_user_agent="FinGPT test@example.com",
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["source"], "SEC EDGAR")
        self.assertEqual(documents[0]["doc_type"], "news")
        self.assertIn("(MSFT)", documents[0]["text"])
        self.assertIn("collected_at", documents[0])

    def test_collect_sec_filings_returns_rate_limited_on_429(self):
        with patch.object(sec_filings.httpx, "get", return_value=_response(429, text="too many requests")):
            result, documents = sec_filings.collect_sec_filings_as_news(
                "MSFT",
                lookback_days=7,
                sec_user_agent="FinGPT test@example.com",
            )

        self.assertEqual(result.status, "rate_limited")
        self.assertEqual(documents, [])

    def test_collect_sec_filings_filters_old_dates(self):
        responses = [
            _response(200, _ticker_payload()),
            _response(200, _submissions_payload("2026-03-01")),
        ]

        with patch.object(sec_filings, "_now", return_value=sec_filings.datetime(2026, 4, 21, 0, 0, 0)), \
             patch.object(sec_filings.httpx, "get", side_effect=responses):
            result, documents = sec_filings.collect_sec_filings_as_news(
                "MSFT",
                lookback_days=7,
                sec_user_agent="FinGPT test@example.com",
            )

        self.assertEqual(result.status, "empty")
        self.assertEqual(documents, [])
        self.assertIn("lookback", result.detail)

    def test_collect_sec_filings_timeout(self):
        with patch.object(sec_filings.httpx, "get", side_effect=httpx.TimeoutException("slow")):
            result, documents = sec_filings.collect_sec_filings_as_news(
                "MSFT",
                lookback_days=7,
                sec_user_agent="FinGPT test@example.com",
            )

        self.assertEqual(result.status, "timeout")
        self.assertEqual(documents, [])


if __name__ == "__main__":
    unittest.main()
