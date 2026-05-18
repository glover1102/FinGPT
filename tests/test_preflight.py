import unittest
import subprocess
from unittest.mock import Mock, patch

import httpx

from core.config.settings import Settings
from core import preflight


def _ok_probe(name: str) -> tuple[str, bool, str]:
    return name, True, "ok"


def _completed(args: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
    process = Mock()
    process.args = args
    process.returncode = returncode
    process.stdout = stdout
    process.stderr = stderr
    return process


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.local_settings = Settings(
            qdrant_url="http://localhost:6333",
            fmp_api_key="test-key",
            fmp_enabled=True,
            primary_model="mistral:7b",
        )
        self.remote_settings = Settings(
            qdrant_url="https://cluster.example.com",
            fmp_api_key="test-key",
            fmp_enabled=True,
            primary_model="mistral:7b",
        )

    def test_local_qdrant_service_reports_missing_docker_cli(self):
        with patch.object(preflight, "_http_get", side_effect=httpx.ConnectError("refused"), create=True), \
             patch.object(preflight, "_run_command", side_effect=FileNotFoundError("docker"), create=True):
            name, ok, detail = preflight._check_qdrant_service(self.local_settings)

        self.assertEqual(name, "QDRANT_SERVICE")
        self.assertFalse(ok)
        self.assertIn("Install Docker Desktop", detail)

    def test_local_qdrant_service_reports_docker_daemon_down(self):
        responses = [
            _completed(["docker", "--version"], returncode=0, stdout="Docker version 28.0.0"),
            _completed(["docker", "info"], returncode=1, stderr="daemon not running"),
        ]

        with patch.object(preflight, "_http_get", side_effect=httpx.ConnectError("refused"), create=True), \
             patch.object(preflight, "_run_command", side_effect=responses, create=True):
            name, ok, detail = preflight._check_qdrant_service(self.local_settings)

        self.assertEqual(name, "QDRANT_SERVICE")
        self.assertFalse(ok)
        self.assertIn("Docker Desktop", detail)

    def test_local_qdrant_service_handles_docker_info_timeout(self):
        responses = [
            _completed(["docker", "--version"], returncode=0, stdout="Docker version 28.0.0"),
            subprocess.TimeoutExpired(["docker", "info"], timeout=8.0),
        ]

        with patch.object(preflight, "_http_get", side_effect=httpx.ConnectError("refused"), create=True), \
             patch.object(preflight, "_run_command", side_effect=responses, create=True):
            name, ok, detail = preflight._check_qdrant_service(self.local_settings)

        self.assertEqual(name, "QDRANT_SERVICE")
        self.assertFalse(ok)
        self.assertIn("Docker Desktop", detail)

    def test_local_qdrant_service_reports_port_conflict(self):
        responses = [
            _completed(["docker", "--version"], returncode=0, stdout="Docker version 28.0.0"),
            _completed(["docker", "info"], returncode=0, stdout="Server Version: 28.0.0"),
            _completed(["docker", "ps", "-a"], returncode=0, stdout=""),
        ]

        with patch.object(preflight, "_http_get", side_effect=httpx.ConnectError("refused"), create=True), \
             patch.object(preflight, "_run_command", side_effect=responses, create=True), \
             patch.object(preflight, "_get_local_port_process", return_value={"pid": 4242, "name": "python.exe"}, create=True):
            name, ok, detail = preflight._check_qdrant_service(self.local_settings)

        self.assertEqual(name, "QDRANT_SERVICE")
        self.assertFalse(ok)
        self.assertIn("python.exe", detail)
        self.assertIn("4242", detail)

    def test_local_qdrant_service_reports_container_down(self):
        responses = [
            _completed(["docker", "--version"], returncode=0, stdout="Docker version 28.0.0"),
            _completed(["docker", "info"], returncode=0, stdout="Server Version: 28.0.0"),
            _completed(["docker", "ps", "-a"], returncode=0, stdout="fingpt-qdrant|Exited (1) 2 minutes ago"),
        ]

        with patch.object(preflight, "_http_get", side_effect=httpx.ConnectError("refused"), create=True), \
             patch.object(preflight, "_run_command", side_effect=responses, create=True), \
             patch.object(preflight, "_get_local_port_process", return_value=None, create=True):
            name, ok, detail = preflight._check_qdrant_service(self.local_settings)

        self.assertEqual(name, "QDRANT_SERVICE")
        self.assertFalse(ok)
        self.assertIn("docker compose up -d qdrant", detail)

    def test_run_preflight_reports_both_qdrant_checks_when_ready(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"result": {"collections": [{"name": "market_docs"}]}}
        client = Mock()

        with patch.object(preflight, "load_settings", return_value=self.local_settings), \
             patch.object(preflight, "_check_fmp_key", return_value=_ok_probe("FMP_API_KEY")), \
             patch.object(preflight, "_check_hf_token", return_value=_ok_probe("HF_TOKEN")), \
             patch.object(preflight, "_check_openbb_package", return_value=_ok_probe("OPENBB_PACKAGE")), \
             patch.object(preflight, "_check_openbb_news_runtime", return_value=_ok_probe("OPENBB_NEWS_RUNTIME")), \
             patch.object(preflight, "_check_yfinance_feed", return_value=_ok_probe("YFINANCE_FEED")), \
             patch.object(preflight, "_check_fmp_stock_news", return_value=_ok_probe("FMP_STOCK_NEWS")), \
             patch.object(preflight, "_check_sec_filings", return_value=_ok_probe("SEC_FILINGS")), \
             patch.object(preflight, "_check_fred_macro", return_value=_ok_probe("FRED_MACRO")), \
             patch.object(preflight, "_check_alpha_vantage_news", return_value=_ok_probe("ALPHA_VANTAGE_NEWS")), \
             patch.object(preflight, "_check_transcript_provider", return_value=_ok_probe("TRANSCRIPT_PROVIDER")), \
             patch.object(preflight, "_check_ollama", return_value=_ok_probe("OLLAMA_SERVICE")), \
             patch.object(preflight, "_check_ollama_model", return_value=_ok_probe("OLLAMA_MODEL (mistral:7b)")), \
             patch.object(preflight, "_http_get", return_value=response, create=True), \
             patch("core.utils.qdrant_helpers.get_qdrant_client", return_value=client), \
             patch("core.utils.qdrant_helpers.ensure_collection"), \
             patch("core.utils.qdrant_helpers.add_documents_to_qdrant", return_value=["doc-1"]), \
             patch("core.utils.qdrant_helpers.search_documents", return_value=[{"score": 0.9, "metadata": {"ticker": "MSFT"}, "document": "test"}]):
            report = preflight.run_preflight()

        self.assertTrue(report["passed"])
        names = [check["name"] for check in report["checks"]]
        self.assertIn("QDRANT_SERVICE", names)
        self.assertIn("QDRANT_QUERY_STACK", names)
        self.assertIn("QDRANT_COLLECTION_SCHEMA", names)
        self.assertIn("OPENBB_PACKAGE", names)
        self.assertIn("OPENBB_NEWS_RUNTIME", names)
        self.assertIn("OPENBB_AGENT_CONTRACT", names)
        self.assertIn("YFINANCE_FEED", names)
        self.assertIn("FRED_MACRO", names)
        self.assertIn("ALPHA_VANTAGE_NEWS", names)
        self.assertIn("FMP_STOCK_NEWS", names)
        self.assertIn("SEC_FILINGS", names)
        self.assertIn("TRANSCRIPT_PROVIDER", names)

    def test_run_preflight_fails_when_query_stack_is_not_ready(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"result": {"collections": [{"name": "market_docs"}]}}
        client = Mock()

        with patch.object(preflight, "load_settings", return_value=self.local_settings), \
             patch.object(preflight, "_check_fmp_key", return_value=_ok_probe("FMP_API_KEY")), \
             patch.object(preflight, "_check_hf_token", return_value=_ok_probe("HF_TOKEN")), \
             patch.object(preflight, "_check_openbb_package", return_value=_ok_probe("OPENBB_PACKAGE")), \
             patch.object(preflight, "_check_openbb_news_runtime", return_value=_ok_probe("OPENBB_NEWS_RUNTIME")), \
             patch.object(preflight, "_check_yfinance_feed", return_value=_ok_probe("YFINANCE_FEED")), \
             patch.object(preflight, "_check_fmp_stock_news", return_value=_ok_probe("FMP_STOCK_NEWS")), \
             patch.object(preflight, "_check_sec_filings", return_value=_ok_probe("SEC_FILINGS")), \
             patch.object(preflight, "_check_fred_macro", return_value=_ok_probe("FRED_MACRO")), \
             patch.object(preflight, "_check_alpha_vantage_news", return_value=_ok_probe("ALPHA_VANTAGE_NEWS")), \
             patch.object(preflight, "_check_transcript_provider", return_value=_ok_probe("TRANSCRIPT_PROVIDER")), \
             patch.object(preflight, "_check_ollama", return_value=_ok_probe("OLLAMA_SERVICE")), \
             patch.object(preflight, "_check_ollama_model", return_value=_ok_probe("OLLAMA_MODEL (mistral:7b)")), \
             patch.object(preflight, "_http_get", return_value=response, create=True), \
             patch("core.utils.qdrant_helpers.get_qdrant_client", return_value=client), \
             patch("core.utils.qdrant_helpers.ensure_collection"), \
             patch("core.utils.qdrant_helpers.add_documents_to_qdrant", side_effect=RuntimeError("embedding init failed")), \
             patch("core.utils.qdrant_helpers.search_documents", return_value=[]):
            report = preflight.run_preflight()

        self.assertFalse(report["passed"])
        query_stack = next(check for check in report["checks"] if check["name"] == "QDRANT_QUERY_STACK")
        self.assertIn("not ready", query_stack["detail"])

    def test_fmp_checks_are_disabled_when_fmp_is_auxiliary_off(self):
        settings = Settings(fmp_api_key="", fmp_enabled=False)

        self.assertTrue(preflight._check_fmp_key(settings)[1])
        self.assertTrue(preflight._check_fmp_stock_news(settings)[1])
        self.assertTrue(preflight._check_transcript_provider(settings)[1])
        self.assertIn("Disabled", preflight._check_fmp_stock_news(settings)[2])

    def test_openbb_news_runtime_is_disabled_by_default(self):
        settings = Settings(openbb_enabled=True, openbb_news_enabled=False)

        name, ok, detail = preflight._check_openbb_news_runtime(settings)

        self.assertEqual(name, "OPENBB_NEWS_RUNTIME")
        self.assertTrue(ok)
        self.assertIn("OPENBB_NEWS_ENABLED=false", detail)

    def test_alpha_vantage_news_is_disabled_by_default(self):
        settings = Settings(alpha_vantage_enabled=False, alpha_vantage_api_key="")

        name, ok, detail = preflight._check_alpha_vantage_news(settings)

        self.assertEqual(name, "ALPHA_VANTAGE_NEWS")
        self.assertTrue(ok)
        self.assertIn("ALPHA_VANTAGE_ENABLED=false", detail)

    def test_alpha_vantage_rate_limit_is_optional_degraded_not_blocking(self):
        settings = Settings(alpha_vantage_enabled=True, alpha_vantage_api_key="test-key")
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"Note": "API call frequency limit reached."}

        with patch.object(preflight, "_http_get", return_value=response):
            name, ok, detail = preflight._check_alpha_vantage_news(settings)

        self.assertEqual(name, "ALPHA_VANTAGE_NEWS")
        self.assertTrue(ok)
        self.assertIn("Optional provider degraded", detail)

    def test_qdrant_collection_schema_warns_on_dense_fallback(self):
        settings = Settings(hybrid_search_enabled=True, hybrid_search_auto_migrate_sparse=False)

        with patch("core.utils.qdrant_helpers.get_qdrant_client", return_value=Mock()), \
             patch("core.utils.qdrant_helpers.ensure_collection"), \
             patch("core.utils.qdrant_helpers.collection_has_sparse_vectors", return_value=False), \
             patch("core.utils.qdrant_helpers.ensure_sparse_vectors", return_value=False):
            name, ok, detail = preflight._check_qdrant_collection_schema(settings)

        self.assertEqual(name, "QDRANT_COLLECTION_SCHEMA")
        self.assertFalse(ok)
        self.assertIn("dense fallback", detail)

    def test_fred_macro_reports_missing_key(self):
        settings = Settings(fred_api_key="")

        name, ok, detail = preflight._check_fred_macro(settings)

        self.assertEqual(name, "FRED_MACRO")
        self.assertFalse(ok)
        self.assertIn("FRED_API_KEY", detail)

    def test_transcript_provider_reports_402_as_entitlement_required(self):
        response = Mock()
        response.status_code = 402
        response.text = "upgrade required"

        with patch.object(preflight, "_http_get", return_value=response):
            name, ok, detail = preflight._check_transcript_provider(self.local_settings)

        self.assertEqual(name, "TRANSCRIPT_PROVIDER")
        self.assertFalse(ok)
        self.assertIn("entitlement_required", detail)

    def test_fmp_stock_news_reports_402_as_entitlement_required(self):
        response = Mock()
        response.status_code = 402
        response.text = "upgrade required"

        with patch.object(preflight, "_http_get", return_value=response):
            name, ok, detail = preflight._check_fmp_stock_news(self.local_settings)

        self.assertEqual(name, "FMP_STOCK_NEWS")
        self.assertFalse(ok)
        self.assertIn("entitlement_required", detail)

    def test_sec_filings_probe_reports_rate_limit(self):
        response = Mock()
        response.status_code = 429
        response.text = "too many requests"

        with patch.object(preflight, "_http_get", return_value=response):
            name, ok, detail = preflight._check_sec_filings(self.local_settings)

        self.assertEqual(name, "SEC_FILINGS")
        self.assertFalse(ok)
        self.assertIn("rate-limiting", detail)

    def test_remote_qdrant_service_skips_docker_specific_branch(self):
        with patch.object(preflight, "_http_get", side_effect=httpx.ConnectError("remote refused"), create=True), \
             patch.object(preflight, "_run_command", side_effect=AssertionError("docker should not be queried"), create=True):
            name, ok, detail = preflight._check_qdrant_service(self.remote_settings)

        self.assertEqual(name, "QDRANT_SERVICE")
        self.assertFalse(ok)
        self.assertNotIn("Docker", detail)


if __name__ == "__main__":
    unittest.main()
