import unittest
from unittest.mock import Mock, patch

import httpx

from pipelines.collect import fmp_transcripts


class FmpTranscriptTests(unittest.TestCase):
    def test_collect_transcripts_returns_no_data_when_dates_list_is_empty(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = []

        with patch.object(fmp_transcripts.httpx, "get", return_value=response):
            result, documents = fmp_transcripts.collect_transcripts_from_fmp("MSFT", 30, "test-key")

        self.assertEqual(result.status, "no_data_in_window")
        self.assertEqual(documents, [])

    def test_collect_transcripts_returns_provider_unavailable_on_server_error(self):
        response = Mock()
        response.status_code = 503
        response.text = "upstream unavailable"

        with patch.object(fmp_transcripts.httpx, "get", return_value=response):
            result, documents = fmp_transcripts.collect_transcripts_from_fmp("MSFT", 30, "test-key")

        self.assertEqual(result.status, "provider_unavailable")
        self.assertEqual(documents, [])

    def test_collect_transcripts_returns_entitlement_required_on_402(self):
        response = Mock()
        response.status_code = 402
        response.text = "upgrade required"

        with patch.object(fmp_transcripts.httpx, "get", return_value=response):
            result, documents = fmp_transcripts.collect_transcripts_from_fmp("MSFT", 30, "test-key")

        self.assertEqual(result.status, "entitlement_required")
        self.assertEqual(documents, [])

    def test_collect_transcripts_returns_timeout_on_http_timeout(self):
        with patch.object(fmp_transcripts.httpx, "get", side_effect=httpx.TimeoutException("slow")):
            result, documents = fmp_transcripts.collect_transcripts_from_fmp("MSFT", 30, "test-key")

        self.assertEqual(result.status, "timeout")
        self.assertEqual(documents, [])


if __name__ == "__main__":
    unittest.main()
