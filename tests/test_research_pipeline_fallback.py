from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.schemas.request import AnalysisRequest
from core.schemas.retrieval import RetrievalItem
from pipelines.collect.models import CollectionOutcome, SourceCollectionResult
from pipelines.orchestration import research_pipeline


def _metric_context(doc_id: str = "uone_price_1") -> RetrievalItem:
    return RetrievalItem(
        source="yfinance:technical",
        title="UONE technical snapshot",
        date="2026-04-24",
        chunk=(
            "Technical indicator snapshot for UONE.\n"
            'TECH_METRICS_JSON: ['
            '{"name":"UONE latest close","value":"2.15","unit":"price","as_of":"2026-04-24",'
            '"context":"기준 가격","source":"yfinance:technical","freshness_status":"fresh","evidence_doc_ids":["uone_price_1"]},'
            '{"name":"UONE 1M price momentum","value":"+8.30%","unit":"%","as_of":"2026-04-24",'
            '"context":"최근 20거래일 가격 모멘텀","source":"yfinance:technical","freshness_status":"fresh","evidence_doc_ids":["uone_price_1"]},'
            '{"name":"UONE RSI(14)","value":"72.4","unit":"index","as_of":"2026-04-24",'
            '"context":"과열 여부","source":"yfinance:technical","freshness_status":"fresh","evidence_doc_ids":["uone_price_1"]}'
            "]"
        ),
        score=0.95,
        metadata={"doc_id": doc_id, "parent_doc_id": doc_id, "ticker": "UONE"},
    )


class ResearchPipelineFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_ticker_model_json_failure_returns_partial_deterministic_fallback(self) -> None:
        request = AnalysisRequest(
            ticker="UONE",
            question="부채와 매출 관점에서 리스크를 분석해주세요.",
            sources=["news", "macro"],
            top_k=3,
            model="qwen",
        )
        outcome = CollectionOutcome(
            documents=[
                {
                    "doc_id": "uone_price_1",
                    "ticker": "UONE",
                    "doc_type": "technical",
                    "source": "yfinance:technical",
                    "published_at": "2026-04-24",
                    "title": "UONE technical snapshot",
                    "text": "TECH_METRICS_JSON deterministic technical metrics.",
                }
            ],
            source_results=[SourceCollectionResult("news", "ok", 1, 0.1, "ok")],
            current_doc_ids=["uone_price_1"],
        )
        events: list[dict] = []

        with patch.object(research_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko", fundamentals_card_enabled=False, retrieval_strategy="single")), \
             patch.object(research_pipeline, "collect_data", return_value=outcome), \
             patch.object(research_pipeline, "ingest_documents", return_value=None), \
             patch.object(research_pipeline, "retrieve_context", return_value=[_metric_context()]), \
             patch.object(research_pipeline, "run_inference", side_effect=ValueError("[Ollama] JSON truncated or unclosed.")), \
             patch.object(research_pipeline, "build_report", return_value=("# report", "<html></html>")), \
             patch.object(research_pipeline, "save_outputs"):
            response = await research_pipeline.run_pipeline_async(request, event_sink=events.append)

        self.assertEqual(response.status, "partial")
        self.assertIn("deterministic fallback", response.error_metadata or "")
        self.assertEqual(response.execution_meta.producing_model, "local-deterministic-fallback")
        self.assertEqual(response.execution_meta.extras["error_type"], "model_json_error")
        self.assertGreaterEqual(len(response.bull_points), 2)
        self.assertGreaterEqual(len(response.bear_points), 2)
        self.assertGreaterEqual(len(response.key_metrics), 3)
        self.assertTrue(all(metric.as_of for metric in response.key_metrics))
        self.assertTrue(any(event.get("stage") == "infer" and event.get("status") == "degraded" for event in events))


if __name__ == "__main__":
    unittest.main()
