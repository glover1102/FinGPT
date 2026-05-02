import unittest
from unittest.mock import patch

from core.config.settings import Settings
from core.schemas.request import AnalysisRequest
from core.schemas.retrieval import RetrievalItem
from pipelines.collect import openbb_collector as collector
from pipelines.collect.cache import get_cache as _get_collection_cache
from pipelines.orchestration import precheck, research_pipeline


def _news_doc(doc_id: str = "doc-1") -> dict:
    return {
        "doc_id": doc_id,
        "ticker": "MSFT",
        "symbol": "MSFT",
        "doc_type": "news",
        "source": "Yahoo Finance",
        "published_at": "2026-04-20T00:00:00+00:00",
        "title": "Microsoft article",
        "text": "Microsoft article body",
        "url": "https://example.com/article",
        "admitted_by": "ticker_match",
    }


class SourceValidationTests(unittest.TestCase):
    def test_report_only_request_is_rejected(self):
        request = AnalysisRequest(ticker="MSFT", question="Test", sources=["report"])

        error = precheck.run_execution_precheck(request)

        self.assertIn("report", error.lower())
        self.assertIn("disabled", error.lower())

    def test_unknown_source_is_rejected(self):
        request = AnalysisRequest(ticker="MSFT", question="Test", sources=["news", "rss"])

        error = precheck.run_execution_precheck(request)

        self.assertIn("unsupported", error.lower())
        self.assertIn("rss", error)


class CollectionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            alpha_vantage_enabled=False,
            fmp_enabled=False,
            openbb_news_enabled=False,
            data_provider_priority="yfinance,sec,google,openbb,alpha_vantage,fmp",
        )
        # Collection results are now cached by (ticker, sources, lookback).
        # Tests in this class share keys, so start each test with a clean cache.
        _get_collection_cache(self.settings).invalidate(None)

    def test_collect_data_marks_report_as_disabled_without_degrading_run(self):
        news_result = collector.SourceCollectionResult(
            source="news",
            status="ok",
            doc_count=1,
            elapsed_s=1.2,
            detail="news ok",
        )

        with patch.object(collector, "load_settings", return_value=self.settings), \
             patch.object(collector, "_collect_news_source", return_value=(news_result, [_news_doc()], [])), \
             patch.object(collector, "write_documents"):
            outcome = collector.collect_data("MSFT", ["news", "report"], 30)

        statuses = {result.source: result.status for result in outcome.source_results}
        self.assertEqual(statuses["news"], "ok")
        self.assertEqual(statuses["report"], "disabled")
        self.assertFalse(outcome.degraded)
        self.assertEqual(len(outcome.documents), 1)

    def test_collect_data_prefers_sec_when_yahoo_returns_too_few_docs(self):
        yahoo_result = collector.SourceCollectionResult(
            source="news",
            status="ok",
            doc_count=1,
            elapsed_s=1.0,
            detail="Yahoo Finance news collected.",
        )
        sec_result = collector.SourceCollectionResult(
            source="news",
            status="ok",
            doc_count=2,
            elapsed_s=0.5,
            detail="SEC filings collected.",
        )
        sec_docs = [_news_doc("doc-2"), _news_doc("doc-3")]

        with patch.object(collector, "load_settings", return_value=self.settings), \
             patch.object(collector, "_collect_yfinance_news_source", return_value=(yahoo_result, [_news_doc()])), \
             patch.object(collector, "collect_sec_filings_as_news", return_value=(sec_result, sec_docs)), \
             patch.object(collector, "collect_news_from_google_rss", side_effect=AssertionError("Google should not run once SEC clears the threshold")), \
             patch.object(collector, "collect_stock_news_from_fmp", side_effect=AssertionError("FMP should not run by default")), \
             patch.object(collector, "write_documents"):
            outcome = collector.collect_data("MSFT", ["news"], 30)

        self.assertEqual(outcome.source_results[0].source, "news")
        self.assertEqual(outcome.source_results[0].status, "ok")
        self.assertEqual(outcome.source_results[0].doc_count, 3)
        self.assertIn("yfinance=ok", outcome.source_results[0].detail)
        self.assertIn("sec_filings=ok", outcome.source_results[0].detail)
        self.assertEqual(len(outcome.provider_results), 2)
        self.assertEqual(len(outcome.documents), 3)

    def test_collect_data_uses_auxiliary_fmp_only_when_enabled_and_primary_sources_insufficient(self):
        settings = Settings(fmp_enabled=True, fmp_api_key="test-key", data_provider_priority="yfinance,sec,google,fmp")
        _get_collection_cache(settings).invalidate(None)
        yahoo_result = collector.SourceCollectionResult(
            source="news",
            status="empty",
            doc_count=0,
            elapsed_s=1.0,
            detail="Yahoo empty.",
        )
        sec_empty = collector.SourceCollectionResult(
            source="news",
            status="empty",
            doc_count=0,
            elapsed_s=0.4,
            detail="SEC empty.",
        )
        google_empty = collector.SourceCollectionResult(
            source="news",
            status="empty",
            doc_count=0,
            elapsed_s=0.3,
            detail="Google empty.",
        )
        fmp_result = collector.SourceCollectionResult(
            source="news",
            status="ok",
            doc_count=1,
            elapsed_s=0.5,
            detail="FMP stock news collected.",
        )
        fmp_docs = [_news_doc("fmp-doc-1")]

        with patch.object(collector, "load_settings", return_value=settings), \
             patch.object(collector, "_collect_yfinance_news_source", return_value=(yahoo_result, [])), \
             patch.object(collector, "collect_sec_filings_as_news", return_value=(sec_empty, [])), \
             patch.object(collector, "collect_news_from_google_rss", return_value=(google_empty, [])), \
             patch.object(collector, "collect_stock_news_from_fmp", return_value=(fmp_result, fmp_docs)), \
             patch.object(collector, "write_documents"):
            outcome = collector.collect_data("MSFT", ["news"], 30)

        self.assertEqual(outcome.source_results[0].status, "ok")
        self.assertIn("fmp_stock_news=ok", outcome.source_results[0].detail)
        self.assertEqual(
            [result.source for result in outcome.provider_results],
            ["news:yfinance", "news:sec_filings", "news:google_news_rss", "news:fmp_stock_news"],
        )
        self.assertEqual(len(outcome.documents), 1)

    def test_collect_data_uses_alpha_vantage_before_auxiliary_fmp(self):
        settings = Settings(
            alpha_vantage_enabled=True,
            alpha_vantage_api_key="test-key",
            fmp_enabled=True,
            fmp_api_key="fmp-key",
            data_provider_priority="yfinance,sec,google,alpha_vantage,fmp",
        )
        _get_collection_cache(settings).invalidate(None)
        empty = collector.SourceCollectionResult("news", "empty", 0, 0.1, "empty")
        alpha_result = collector.SourceCollectionResult("news", "ok", 3, 0.2, "Alpha ok")
        alpha_docs = [_news_doc("alpha-1"), _news_doc("alpha-2"), _news_doc("alpha-3")]

        with patch.object(collector, "load_settings", return_value=settings), \
             patch.object(collector, "_collect_yfinance_news_source", return_value=(empty, [])), \
             patch.object(collector, "collect_sec_filings_as_news", return_value=(empty, [])), \
             patch.object(collector, "collect_news_from_google_rss", return_value=(empty, [])), \
             patch.object(collector, "collect_news_from_alpha_vantage", return_value=(alpha_result, alpha_docs)), \
             patch.object(collector, "collect_stock_news_from_fmp", side_effect=AssertionError("FMP should not run once Alpha Vantage clears the threshold")), \
             patch.object(collector, "write_documents"):
            outcome = collector.collect_data("MSFT", ["news"], 30)

        self.assertEqual(outcome.source_results[0].status, "ok")
        self.assertIn("alpha_vantage_news=ok", outcome.source_results[0].detail)
        self.assertEqual(
            [result.source for result in outcome.provider_results],
            ["news:yfinance", "news:sec_filings", "news:google_news_rss", "news:alpha_vantage_news"],
        )
        self.assertEqual(len(outcome.documents), 3)

    def test_collect_data_uses_sec_filings_without_touching_fmp_by_default(self):
        yahoo_result = collector.SourceCollectionResult(
            source="news",
            status="empty",
            doc_count=0,
            elapsed_s=1.0,
            detail="Yahoo empty.",
        )
        sec_result = collector.SourceCollectionResult(
            source="news",
            status="ok",
            doc_count=1,
            elapsed_s=0.4,
            detail="SEC filings collected.",
        )
        sec_docs = [_news_doc("sec-doc-1")]

        google_empty = collector.SourceCollectionResult(
            source="news",
            status="empty",
            doc_count=0,
            elapsed_s=0.3,
            detail="google_news empty.",
        )

        with patch.object(collector, "load_settings", return_value=self.settings), \
             patch.object(collector, "_collect_yfinance_news_source", return_value=(yahoo_result, [])), \
             patch.object(collector, "collect_news_from_google_rss", return_value=(google_empty, [])), \
             patch.object(collector, "collect_sec_filings_as_news", return_value=(sec_result, sec_docs)), \
             patch.object(collector, "collect_stock_news_from_fmp", side_effect=AssertionError("FMP should not run by default")), \
             patch.object(collector, "write_documents"):
            outcome = collector.collect_data("MSFT", ["news"], 30)

        self.assertEqual(outcome.source_results[0].status, "ok")
        self.assertIn("sec_filings=ok", outcome.source_results[0].detail)
        self.assertEqual(
            [result.source for result in outcome.provider_results],
            [
                "news:yfinance",
                "news:sec_filings",
                "news:google_news_rss",
                "news:openbb_news",
                "news:alpha_vantage_news",
                "news:fmp_stock_news",
            ],
        )
        self.assertEqual(outcome.provider_results[-1].status, "disabled")
        self.assertEqual(len(outcome.documents), 1)

    def test_collect_data_skips_fmp_news_when_yahoo_has_enough_docs(self):
        yahoo_result = collector.SourceCollectionResult(
            source="news",
            status="ok",
            doc_count=3,
            elapsed_s=1.0,
            detail="Yahoo Finance news collected.",
        )
        yahoo_docs = [_news_doc("doc-1"), _news_doc("doc-2"), _news_doc("doc-3")]

        with patch.object(collector, "load_settings", return_value=self.settings), \
             patch.object(collector, "_collect_yfinance_news_source", return_value=(yahoo_result, yahoo_docs)), \
             patch.object(collector, "collect_stock_news_from_fmp", side_effect=AssertionError("FMP fallback should not run")), \
             patch.object(collector, "collect_sec_filings_as_news", side_effect=AssertionError("SEC fallback should not run")), \
             patch.object(collector, "collect_news_from_google_rss", side_effect=AssertionError("Google fallback should not run")), \
             patch.object(collector, "write_documents"):
            outcome = collector.collect_data("MSFT", ["news"], 30)

        self.assertEqual(outcome.source_results[0].status, "ok")
        self.assertEqual(len(outcome.provider_results), 1)
        self.assertEqual(len(outcome.documents), 3)

    def test_collect_data_disables_transcripts_when_fmp_is_not_enabled(self):
        with patch.object(collector, "load_settings", return_value=self.settings), \
             patch.object(collector, "collect_transcripts_from_fmp", side_effect=AssertionError("FMP transcripts should be disabled by default")), \
             patch.object(collector, "write_documents"):
            outcome = collector.collect_data("MSFT", ["transcript"], 30)

        self.assertEqual(outcome.source_results[0].source, "transcript")
        self.assertEqual(outcome.source_results[0].status, "disabled")
        self.assertFalse(outcome.degraded)
        self.assertEqual(outcome.provider_results[0].source, "transcript:fmp")
        self.assertEqual(outcome.provider_results[0].status, "disabled")

    def test_apply_collection_outcome_keeps_success_when_primary_source_is_ok(self):
        outcome = collector.CollectionOutcome(
            documents=[_news_doc()],
            source_results=[
                collector.SourceCollectionResult("news", "ok", 1, 1.0, "news ok"),
                collector.SourceCollectionResult("transcript", "provider_unavailable", 0, 0.8, "provider down"),
            ],
            degraded=True,
            summary_detail="collection degraded: transcript=provider_unavailable",
        )

        status, error_metadata = research_pipeline._apply_collection_outcome("success", None, outcome)

        self.assertEqual(status, "success")
        self.assertIsNone(error_metadata)

    def test_apply_collection_outcome_marks_partial_when_primary_source_fails(self):
        outcome = collector.CollectionOutcome(
            documents=[],
            source_results=[
                collector.SourceCollectionResult("news", "timeout", 0, 10.0, "news timed out"),
                collector.SourceCollectionResult("transcript", "provider_unavailable", 0, 0.8, "provider down"),
            ],
            degraded=True,
            summary_detail="collection degraded: news=timeout; transcript=provider_unavailable",
        )

        status, error_metadata = research_pipeline._apply_collection_outcome("success", None, outcome)

        self.assertEqual(status, "partial")
        self.assertEqual(error_metadata, "collection degraded: news=timeout; transcript=provider_unavailable")


class NoContextPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self._structured_context_patchers = [
            patch.object(research_pipeline, "build_structured_context", return_value={}),
            patch.object(research_pipeline, "structured_context_to_retrieval_item", return_value=None),
            patch.object(research_pipeline, "structured_context_metrics", return_value=[]),
        ]
        for patcher in self._structured_context_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_empty_context_returns_partial_without_invoking_inference(self):
        request = AnalysisRequest(
            ticker="JPM",
            question="What macro or company-specific developments are most relevant for JPMorgan Chase right now?",
            sources=["news", "transcript"],
            lookback_days=21,
            top_k=5,
        )
        outcome = collector.CollectionOutcome(
            documents=[],
            source_results=[
                collector.SourceCollectionResult("news", "empty", 0, 14.0, "Yahoo Finance returned zero articles."),
                collector.SourceCollectionResult("transcript", "provider_unavailable", 0, 1.2, "Transcript provider unavailable."),
            ],
            degraded=True,
            summary_detail="collection degraded: news=empty; transcript=provider_unavailable",
        )

        with patch.object(research_pipeline, "run_execution_precheck", return_value=None), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "retrieve_context", return_value=[]), \
             patch.object(research_pipeline, "build_report", return_value=("md", "html")), \
             patch.object(research_pipeline, "save_outputs"), \
             patch.object(research_pipeline, "run_inference", side_effect=AssertionError("inference should not run without context")):
            response = await research_pipeline.run_pipeline_async(request)

        self.assertEqual(response.status, "partial")
        self.assertIn("collection degraded: news=empty; transcript=provider_unavailable", response.error_metadata)
        self.assertIn("No usable current-run primary documents", response.error_metadata)
        self.assertIn("신뢰할 만한 최신 근거", response.summary)
        self.assertEqual(response.sentiment, "Neutral")

    async def test_empty_current_primary_docs_skips_retrieval_and_inference(self):
        request = AnalysisRequest(
            ticker="JPM",
            question="What macro developments matter?",
            sources=["news", "transcript"],
            lookback_days=21,
            top_k=5,
        )
        outcome = collector.CollectionOutcome(
            documents=[],
            source_results=[
                collector.SourceCollectionResult("news", "empty", 0, 12.0, "news empty"),
                collector.SourceCollectionResult("transcript", "entitlement_required", 0, 0.5, "plan upgrade required"),
            ],
            degraded=True,
            summary_detail="collection degraded: news=empty; transcript=entitlement_required",
            current_doc_ids=[],
        )

        with patch.object(research_pipeline, "run_execution_precheck", return_value=None), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "retrieve_context", side_effect=AssertionError("retrieval should not run without current primary docs")), \
             patch.object(research_pipeline, "build_report", return_value=("md", "html")), \
             patch.object(research_pipeline, "save_outputs"), \
             patch.object(research_pipeline, "run_inference", side_effect=AssertionError("inference should not run without current context")):
            response = await research_pipeline.run_pipeline_async(request)

        self.assertEqual(response.status, "partial")
        self.assertIn("No usable current-run primary documents", response.error_metadata)

    async def test_transcript_only_without_current_docs_skips_retrieval_and_inference(self):
        request = AnalysisRequest(
            ticker="MSFT",
            question="What did management say recently?",
            sources=["transcript"],
            lookback_days=21,
            top_k=5,
        )
        outcome = collector.CollectionOutcome(
            documents=[],
            source_results=[
                collector.SourceCollectionResult("transcript", "entitlement_required", 0, 0.5, "plan upgrade required"),
            ],
            degraded=True,
            summary_detail="collection degraded: transcript=entitlement_required",
            current_doc_ids=[],
        )

        with patch.object(research_pipeline, "run_execution_precheck", return_value=None), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "retrieve_context", side_effect=AssertionError("retrieval should not run without current docs")), \
             patch.object(research_pipeline, "build_report", return_value=("md", "html")), \
             patch.object(research_pipeline, "save_outputs"), \
             patch.object(research_pipeline, "run_inference", side_effect=AssertionError("inference should not run without current context")):
            response = await research_pipeline.run_pipeline_async(request)

        self.assertEqual(response.status, "partial")
        self.assertIn("No usable current-run documents", response.error_metadata)

    async def test_retrieval_filters_out_stale_qdrant_docs(self):
        request = AnalysisRequest(
            ticker="MSFT",
            question="Is Microsoft a good investment?",
            sources=["news"],
            lookback_days=14,
            top_k=1,
        )
        current_doc = _news_doc("current-doc")
        outcome = collector.CollectionOutcome(
            documents=[current_doc],
            source_results=[collector.SourceCollectionResult("news", "ok", 1, 1.0, "news ok")],
            degraded=False,
            summary_detail="",
            current_doc_ids=["current-doc"],
        )
        retrieved = [
            RetrievalItem(
                source="Yahoo Finance",
                title="Old article",
                date="2026-04-01T00:00:00",
                chunk="Old Microsoft context",
                score=0.99,
                metadata={"doc_id": "old-doc", "ticker": "MSFT"},
            ),
            RetrievalItem(
                source="Yahoo Finance",
                title="Current article",
                date="2026-04-20T00:00:00",
                chunk="Current Microsoft context",
                score=0.75,
                metadata={"doc_id": "current-doc", "ticker": "MSFT"},
            ),
        ]
        raw_output = {
            "summary": "Microsoft current-run context only.",
            "bull_points": ["Current-run driver"],
            "bear_points": [],
            "sentiment": "Positive",
            "confidence": 0.8,
            "uncertainty": "",
            "cited_doc_ids": ["current-doc"],
            "_meta": {"primary_model": "mistral:7b", "producing_model": "mistral:7b"},
        }

        # Default retrieval strategy is ``multi_query``; the orchestrator now
        # routes through ``retrieve_context_multi`` instead of the legacy
        # single-query ``retrieve_context`` path. We patch both so the test is
        # stable regardless of the active strategy in settings.
        with patch.object(research_pipeline, "run_execution_precheck", return_value=None), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "ingest_documents"), \
             patch.object(research_pipeline, "retrieve_context", return_value=retrieved) as retrieve_mock, \
             patch.object(research_pipeline, "retrieve_context_multi", return_value=retrieved) as retrieve_multi_mock, \
             patch.object(research_pipeline, "run_inference", return_value=raw_output) as inference_mock, \
             patch.object(research_pipeline, "build_report", return_value=("md", "html")), \
             patch.object(research_pipeline, "save_outputs"):
            response = await research_pipeline.run_pipeline_async(request)

        total_calls = retrieve_mock.call_count + retrieve_multi_mock.call_count
        self.assertEqual(total_calls, 1, "Exactly one retrieval strategy should have fired.")
        active_mock = retrieve_multi_mock if retrieve_multi_mock.call_count else retrieve_mock
        self.assertEqual(active_mock.call_args.args[2], 25)
        inference_context = inference_mock.call_args.args[2]
        self.assertEqual(len(inference_context), 1)
        self.assertEqual(inference_context[0].metadata["doc_id"], "current-doc")
        self.assertEqual(len(response.raw_context), 1)
        self.assertEqual(response.raw_context[0].metadata["doc_id"], "current-doc")

    async def test_collected_current_docs_backfill_when_retrieval_misses_current_run(self):
        request = AnalysisRequest(
            ticker="MSFT",
            question="Is Microsoft a good investment?",
            sources=["news"],
            lookback_days=14,
            top_k=1,
        )
        current_doc = _news_doc("current-doc")
        outcome = collector.CollectionOutcome(
            documents=[current_doc],
            source_results=[collector.SourceCollectionResult("news", "ok", 1, 1.0, "news ok")],
            degraded=False,
            summary_detail="",
            current_doc_ids=["current-doc"],
        )
        retrieved = [
            RetrievalItem(
                source="Yahoo Finance",
                title="Old article",
                date="2026-04-01T00:00:00",
                chunk="Old Microsoft context",
                score=0.99,
                metadata={"doc_id": "old-doc", "ticker": "MSFT"},
            )
        ]
        raw_output = {
            "summary": "Microsoft current-run collection fallback.",
            "bull_points": ["Current-run collected driver"],
            "bear_points": [],
            "sentiment": "Positive",
            "confidence": 0.8,
            "uncertainty": "",
            "cited_doc_ids": ["current-doc"],
            "_meta": {"primary_model": "mistral:7b", "producing_model": "mistral:7b"},
        }

        with patch.object(research_pipeline, "run_execution_precheck", return_value=None), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "ingest_documents"), \
             patch.object(research_pipeline, "retrieve_context", return_value=retrieved), \
             patch.object(research_pipeline, "retrieve_context_multi", return_value=retrieved), \
             patch.object(research_pipeline, "run_inference", return_value=raw_output) as inference_mock, \
             patch.object(research_pipeline, "build_report", return_value=("md", "html")), \
             patch.object(research_pipeline, "save_outputs"):
            response = await research_pipeline.run_pipeline_async(request)

        inference_context = inference_mock.call_args.args[2]
        self.assertEqual(len(inference_context), 1)
        self.assertEqual(inference_context[0].metadata["doc_id"], "current-doc")
        self.assertEqual(inference_context[0].metadata["retrieval_mode"], "current_run_priority")
        self.assertEqual(response.raw_context[0].metadata["doc_id"], "current-doc")

    async def test_ingest_failure_continues_with_existing_indexed_context(self):
        request = AnalysisRequest(
            ticker="QQQ",
            question="Macro backdrop?",
            sources=["news"],
            lookback_days=14,
            top_k=5,
        )
        current_doc = _news_doc("current-doc")
        current_doc["ticker"] = "QQQ"
        current_doc["symbol"] = "QQQ"
        outcome = collector.CollectionOutcome(
            documents=[current_doc],
            source_results=[collector.SourceCollectionResult("news", "ok", 1, 1.0, "news ok")],
            degraded=False,
            summary_detail="",
            current_doc_ids=["current-doc"],
        )
        retrieved = [
            RetrievalItem(
                source="Yahoo Finance",
                title="Current article",
                date="2026-04-20T00:00:00",
                chunk="Current QQQ macro context",
                score=0.75,
                metadata={"doc_id": "current-doc", "ticker": "QQQ"},
            )
        ]
        raw_output = {
            "summary": "QQQ current-run context.",
            "bull_points": ["Current-run driver"],
            "bear_points": [],
            "sentiment": "Positive",
            "confidence": 0.8,
            "uncertainty": "",
            "cited_doc_ids": ["current-doc"],
            "_meta": {"primary_model": "mistral:7b", "producing_model": "mistral:7b"},
        }

        with patch.object(research_pipeline, "run_execution_precheck", return_value=None), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "ingest_documents", side_effect=RuntimeError("legacy sparse mismatch")), \
             patch.object(research_pipeline, "retrieve_context", return_value=retrieved), \
             patch.object(research_pipeline, "retrieve_context_multi", return_value=retrieved), \
             patch.object(research_pipeline, "run_inference", return_value=raw_output) as inference_mock, \
             patch.object(research_pipeline, "build_report", return_value=("md", "html")), \
             patch.object(research_pipeline, "save_outputs"):
            response = await research_pipeline.run_pipeline_async(request)

        self.assertEqual(response.status, "partial")
        self.assertIn("Qdrant ingest failed", response.error_metadata)
        inference_mock.assert_called_once()
        self.assertEqual(len(response.raw_context), 1)


if __name__ == "__main__":
    unittest.main()
