from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.schemas.retrieval import RetrievalItem
from core.schemas.topic import TopicRequest
from pipelines.collect.models import CollectionOutcome, SourceCollectionResult
from pipelines.infer.topic_prompt import EvidenceBucket, EvidencePack, TopicInferencePhaseResult, TOPIC_PLAYBOOKS
from pipelines.orchestration.research_pipeline import (
    _align_evidence_ids,
    _fill_missing_claim_evidence_ids,
    _normalize_doc_id_list,
)
from pipelines.orchestration import topic_pipeline


def _context_item(doc_id: str, text: str) -> RetrievalItem:
    return RetrievalItem(
        source="FRED:DGS30",
        title="30Y Treasury yield",
        date="2026-04-20",
        chunk=text,
        score=0.9,
        metadata={"doc_id": doc_id, "parent_doc_id": doc_id},
    )


def _payload(doc_id: str, *, scenarios: int = 3, execution: int = 2, metrics: int = 3) -> dict:
    return {
        "executive_summary": "장기금리 안정 여부가 핵심입니다.",
        "core_thesis": "중장기 기대값은 유효하지만 단기 변동성은 남아 있습니다.",
        "asset_overview": [
            {
                "title": "자산 개요",
                "bullets": ["TLT는 장기 미국 국채 ETF입니다."],
                "conclusion": "듀레이션 민감도가 큽니다.",
                "evidence_doc_ids": [doc_id],
            }
        ],
        "macro_regime": [
            {
                "title": "거시 환경",
                "bullets": ["성장 둔화와 디스인플레이션이 동시에 진행 중입니다."],
                "conclusion": "완화 기대가 채권에 우호적일 수 있습니다.",
                "evidence_doc_ids": [doc_id],
            }
        ],
        "rate_structure": [
            {
                "title": "금리 구조",
                "bullets": ["장기금리와 실질금리가 아직 높습니다."],
                "conclusion": "반등 여력과 추가 조정 리스크가 공존합니다.",
                "evidence_doc_ids": [doc_id],
            }
        ],
        "investment_judgment": [
            {
                "title": "판단",
                "bullets": ["중장기 기대값은 양호합니다."],
                "conclusion": "분할 접근이 적절합니다.",
                "evidence_doc_ids": [doc_id],
            }
        ],
        "scenario_analysis": [
            {
                "scenario": f"시나리오 {idx + 1}",
                "probability": "중간",
                "expected_outcome": "금리 변화",
                "asset_implication": "TLT 영향",
                "decision_read": "판단",
                "evidence_doc_ids": [doc_id],
            }
            for idx in range(scenarios)
        ],
        "execution_strategy": [
            {
                "strategy": f"전략 {idx + 1}",
                "trigger": "금리 안정",
                "rationale": "타이밍 리스크 완화",
                "risk_control": "추격 매수 자제",
                "evidence_doc_ids": [doc_id],
            }
            for idx in range(execution)
        ],
        "key_drivers": [
            {"text": "디스인플레이션 진전", "direction": "supporting", "evidence_doc_ids": [doc_id]},
            {"text": "경기 둔화 압력", "direction": "supporting", "evidence_doc_ids": [doc_id]},
        ],
        "key_risks": [
            {"text": "인플레이션 재가속", "direction": "opposing", "evidence_doc_ids": [doc_id]},
            {"text": "국채 공급 증가", "direction": "opposing", "evidence_doc_ids": [doc_id]},
        ],
        "related_tickers": [{"ticker": "TLT", "role": "proxy", "rationale": "장기채 ETF"}],
        "key_metrics": [
            {"name": f"지표 {idx + 1}", "value": f"{idx + 1}", "context": "macro", "evidence_doc_ids": [doc_id]}
            for idx in range(metrics)
        ],
        "catalyst_timeline": {"near_term": ["CPI"], "mid_term": ["FOMC"], "long_term": []},
        "open_questions": ["실질금리가 얼마나 빨리 내려올까?"],
        "uncertainty": "",
        "cited_doc_ids": [doc_id],
    }


def _phase_result(
    doc_id: str,
    *,
    gate_ok: bool,
    final_gate_ok: bool,
    missing_buckets: list[str] | None = None,
    scenarios: int = 3,
    execution: int = 2,
    metrics: int = 3,
) -> TopicInferencePhaseResult:
    plan = TOPIC_PLAYBOOKS["rates_bonds"]
    payload = _payload(doc_id, scenarios=scenarios, execution=execution, metrics=metrics)
    payload["_meta"] = {
        "primary_model": "qwen2.5:7b",
        "producing_model": "qwen2.5:7b",
        "retry_count": 0,
        "total_latency_s": 12.5,
        "prompt_char_count": 2048,
        "chunks_used": 1,
        "asset_class": plan.asset_class,
        "evidence_bucket_counts": {
            "macro": 1,
            "asset_specific": 1,
            "market_structure": 1,
            "latest_catalyst": 1 if not missing_buckets else 0,
        },
        "missing_evidence_buckets": missing_buckets or [],
        "coverage_notes": [],
        "missing_evidence_reasons": [],
    }
    empty_bucket = EvidenceBucket("macro", "Macro")
    empty_bucket.add(_context_item(doc_id, "Long-end yields remain elevated."))
    evidence_pack = EvidencePack(
        asset_class=plan.asset_class,
        buckets={
            "macro": empty_bucket,
            "asset_specific": EvidenceBucket("asset_specific", "Asset-specific", items=[_context_item(doc_id, "TLT is duration-sensitive.")]),
            "market_structure": EvidenceBucket("market_structure", "Market structure", items=[_context_item(doc_id, "Real yields remain high.")]),
            "latest_catalyst": EvidenceBucket("latest_catalyst", "Latest catalyst", items=[] if missing_buckets else [_context_item(doc_id, "Fed communication matters.")]),
        },
        metrics=[],
        cited_doc_ids=[doc_id],
        missing_buckets=missing_buckets or [],
        coverage_notes=[],
    )
    return TopicInferencePhaseResult(
        payload=payload,
        topic_plan=plan,
        evidence_pack=evidence_pack,
        latency_s=12.5,
        retry_count=0,
        prompt_char_count=2048,
        gate={"ok": gate_ok},
        final_gate={"ok": final_gate_ok},
        selected_fields=[],
    )


class EvidenceIdNormalizationTests(unittest.TestCase):
    def test_mutated_doc_id_prefix_maps_to_current_context_parent(self) -> None:
        context = [
            RetrievalItem(
                source="yahoo_finance_history",
                title="TLT price snapshot",
                date="2026-04-23",
                chunk="Price fell over the lookback window.",
                score=0.9,
                metadata={
                    "doc_id": "tlt_macro_60d815fb0d4d4d6e__c00",
                    "parent_doc_id": "tlt_macro_60d815fb0d4d4d6e",
                },
            )
        ]

        normalized = _normalize_doc_id_list(["tlt_price_snapshot_60d815fb0d4d4d6e"], context)
        aligned = _align_evidence_ids([["tlt_price_snapshot_60d815fb0d4d4d6e"]], ["하방 리스크"], context)

        self.assertEqual(normalized, ["tlt_macro_60d815fb0d4d4d6e"])
        self.assertEqual(aligned, [["tlt_macro_60d815fb0d4d4d6e"]])

    def test_unrecoverable_model_doc_id_is_replaced_by_auditable_current_doc(self) -> None:
        context = [
            RetrievalItem(
                source="Yahoo Finance",
                title="MSFT current run",
                date="2026-05-01",
                chunk="Current run evidence.",
                score=0.8,
                metadata={"doc_id": "msft_news_good__c00", "parent_doc_id": "msft_news_good"},
            )
        ]

        normalized = _normalize_doc_id_list(["msft_news_typo"], context)
        aligned = _align_evidence_ids([["msft_news_typo"]], ["risk point"], context)
        filled = _fill_missing_claim_evidence_ids(aligned, ["risk point"], context)

        self.assertEqual(normalized, [])
        self.assertEqual(aligned, [[]])
        self.assertEqual(filled, [["msft_news_good"]])


class TopicPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self._structured_context_patchers = [
            patch.object(topic_pipeline, "build_structured_context", return_value={}),
            patch.object(topic_pipeline, "structured_context_to_retrieval_item", return_value=None),
            patch.object(topic_pipeline, "structured_context_metrics", return_value=[]),
        ]
        for patcher in self._structured_context_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_topic_pipeline_emits_partial_result_and_skips_deep_pass_when_fast_gate_is_enough(self):
        request = TopicRequest(
            question="거시경제와 금리 구조를 감안할 때 지금 TLT가 매력적인지 분석해줘.",
            theme="미국 장기채와 TLT",
            related_tickers=["TLT"],
            top_k=3,
        )
        doc_id = "tlt_macro_1"
        outcome = CollectionOutcome(
            documents=[
                {
                    "doc_id": doc_id,
                    "ticker": "TLT",
                    "symbol": "TLT",
                    "doc_type": "macro",
                    "source": "FRED:DGS30",
                    "published_at": "2026-04-20",
                    "title": "30Y Treasury yield",
                    "text": "30Y Treasury yield remains elevated.",
                }
            ],
            source_results=[SourceCollectionResult("topic_asset:TLT", "ok", 1, 0.1, "ok")],
            current_doc_ids=[doc_id],
            cache_hit=True,
            cache_age_s=12.0,
        )
        fast_context = [_context_item(doc_id, "30Y Treasury yield remains elevated.")]
        fast_phase = _phase_result(doc_id, gate_ok=True, final_gate_ok=True)
        events: list[dict] = []

        with patch.object(topic_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko")), \
             patch.object(topic_pipeline, "collect_topic_bundle", return_value=outcome), \
             patch.object(topic_pipeline, "rank_topic_context_fast", return_value=fast_context), \
             patch.object(topic_pipeline, "run_topic_fast_inference", return_value=fast_phase), \
             patch.object(topic_pipeline, "run_topic_deep_inference") as deep_infer, \
             patch.object(topic_pipeline, "build_topic_report", return_value=("# report", "<html></html>")), \
             patch.object(topic_pipeline, "save_outputs"):
            response = await topic_pipeline.run_topic_pipeline_async(request, mode="sector_macro", event_sink=events.append)

        deep_infer.assert_not_called()
        self.assertEqual(response.status, "success")
        self.assertTrue(response.key_metrics)
        self.assertTrue(all(metric.as_of == "2026-04-20" for metric in response.key_metrics))
        self.assertTrue(response.execution_meta.extras["deep_pass_skipped"])
        self.assertEqual(response.execution_meta.extras["retrieval_mode"], "fast_current_documents")
        self.assertTrue(any(event["event"] == "partial_result" for event in events))
        self.assertFalse(any(event.get("stage") == "ingest" for event in events))

    async def test_credit_topic_uses_deterministic_fast_path(self):
        request = TopicRequest(
            question="현재 드러나는 신용 리스크에는 어떤 것이 있나요?",
            theme="현재 시장 신용 리스크",
            related_tickers=["HYG", "LQD", "SPY", "TLT"],
            top_k=6,
        )
        docs = [
            {
                "doc_id": "credit_spread_1",
                "ticker": "HYG",
                "symbol": "HYG",
                "doc_type": "macro",
                "source": "FRED:BAMLH0A0HYM2",
                "published_at": "2026-04-24",
                "title": "US high yield spread",
                "text": "High yield spread is 3.1% as of 2026-04-24.",
            },
            {
                "doc_id": "hyg_price_1",
                "ticker": "HYG",
                "symbol": "HYG",
                "doc_type": "price",
                "source": "yahoo_finance_history",
                "published_at": "2026-04-24",
                "title": "HYG price snapshot",
                "text": "HYG closed at 80.47 as of 2026-04-24, a +0.13% move over the last 20 trading days",
            },
            {
                "doc_id": "lqd_price_1",
                "ticker": "LQD",
                "symbol": "LQD",
                "doc_type": "price",
                "source": "yahoo_finance_history",
                "published_at": "2026-04-24",
                "title": "LQD price snapshot",
                "text": "LQD closed at 109.64 as of 2026-04-24, a -0.36% move over the last 20 trading days",
            },
        ]
        outcome = CollectionOutcome(
            documents=docs,
            source_results=[SourceCollectionResult("topic_asset:HYG", "ok", 3, 0.1, "ok")],
            current_doc_ids=[item["doc_id"] for item in docs],
            cache_hit=True,
            cache_age_s=5.0,
        )
        fast_context = [
            RetrievalItem(
                source=str(item["source"]),
                title=str(item["title"]),
                date=str(item["published_at"]),
                chunk=str(item["text"]),
                score=0.9,
                metadata={"doc_id": item["doc_id"], "parent_doc_id": item["doc_id"], "ticker": item["ticker"]},
            )
            for item in docs
        ]
        events: list[dict] = []

        with patch.object(topic_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko")), \
             patch.object(topic_pipeline, "collect_topic_bundle", return_value=outcome), \
             patch.object(topic_pipeline, "rank_topic_context_fast", return_value=fast_context), \
             patch.object(topic_pipeline, "run_topic_fast_inference") as fast_infer, \
             patch.object(topic_pipeline, "run_topic_deep_inference") as deep_infer, \
             patch.object(topic_pipeline, "build_topic_report", return_value=("# report", "<html></html>")), \
             patch.object(topic_pipeline, "save_outputs"):
            response = await topic_pipeline.run_topic_pipeline_async(request, mode="sector_macro", event_sink=events.append)

        fast_infer.assert_not_called()
        deep_infer.assert_not_called()
        self.assertEqual(response.status, "success")
        self.assertEqual(response.execution_meta.extras["asset_class"], "credit")
        self.assertEqual(response.execution_meta.extras["llm_skipped_reason"], "deterministic_credit_fast_path")
        self.assertEqual(response.execution_meta.extras["warning_evidence_buckets"], ["latest_catalyst"])
        self.assertEqual(response.execution_meta.extras["blocking_evidence_buckets"], [])
        self.assertTrue(response.execution_meta.extras["deep_pass_skipped"])
        self.assertGreaterEqual(len(response.scenario_analysis), 3)
        self.assertGreaterEqual(len(response.execution_strategy), 2)
        self.assertGreaterEqual(len(response.key_metrics), 2)
        self.assertTrue(any(event["event"] == "partial_result" for event in events))

    async def test_rates_topic_uses_quant_deterministic_fast_path(self):
        request = TopicRequest(
            question="TLT 금리와 장기채 가격 매력도를 분석해주세요.",
            theme="TLT 장기채 매력도",
            related_tickers=["TLT"],
            top_k=6,
        )
        docs = [
            {
                "doc_id": "dgs10_doc",
                "ticker": "TLT",
                "symbol": "DGS10",
                "source": "FRED:DGS10",
                "published_at": "2026-04-24",
                "title": "DGS10 Treasury yield",
                "text": "US 10Y Treasury yield is 4.31% as of 2026-04-24.",
            },
            {
                "doc_id": "dgs2_doc",
                "ticker": "TLT",
                "symbol": "DGS2",
                "source": "FRED:DGS2",
                "published_at": "2026-04-24",
                "title": "DGS2 Treasury yield",
                "text": "US 2Y Treasury yield is 3.85% as of 2026-04-24.",
            },
            {
                "doc_id": "dgs30_doc",
                "ticker": "TLT",
                "symbol": "DGS30",
                "source": "FRED:DGS30",
                "published_at": "2026-04-24",
                "title": "DGS30 Treasury yield",
                "text": "US 30Y Treasury yield is 4.78% as of 2026-04-24.",
            },
            {
                "doc_id": "dfii10_doc",
                "ticker": "TLT",
                "symbol": "DFII10",
                "source": "FRED:DFII10",
                "published_at": "2026-04-24",
                "title": "DFII10 real yield",
                "text": "US 10Y real yield proxy is 2.15% as of 2026-04-24.",
            },
            {
                "doc_id": "tlt_price_doc",
                "ticker": "TLT",
                "symbol": "TLT",
                "source": "yahoo_finance_history",
                "published_at": "2026-04-24",
                "title": "TLT price snapshot",
                "text": "TLT closed at 86.70 as of 2026-04-24, a -0.43% move over the last 20 trading days",
            },
        ]
        outcome = CollectionOutcome(
            documents=docs,
            source_results=[SourceCollectionResult("topic_asset:TLT", "ok", len(docs), 0.1, "ok")],
            current_doc_ids=[item["doc_id"] for item in docs],
            cache_hit=True,
            cache_age_s=3.0,
        )
        fast_context = [
            RetrievalItem(
                source=str(item["source"]),
                title=str(item["title"]),
                date=str(item["published_at"]),
                chunk=str(item["text"]),
                score=0.9,
                metadata={"doc_id": item["doc_id"], "parent_doc_id": item["doc_id"], "ticker": item["ticker"]},
            )
            for item in docs
        ]
        events: list[dict] = []

        with patch.object(topic_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko")), \
             patch.object(topic_pipeline, "collect_topic_bundle", return_value=outcome), \
             patch.object(topic_pipeline, "rank_topic_context_fast", return_value=fast_context), \
             patch.object(topic_pipeline, "run_topic_fast_inference") as fast_infer, \
             patch.object(topic_pipeline, "run_topic_deep_inference") as deep_infer, \
             patch.object(topic_pipeline, "build_topic_report", return_value=("# report", "<html></html>")), \
             patch.object(topic_pipeline, "save_outputs"):
            response = await topic_pipeline.run_topic_pipeline_async(request, mode="sector_macro", event_sink=events.append)

        fast_infer.assert_not_called()
        deep_infer.assert_not_called()
        self.assertEqual(response.status, "success")
        self.assertEqual(response.execution_meta.extras["asset_class"], "rates_bonds")
        self.assertEqual(response.execution_meta.extras["llm_skipped_reason"], "deterministic_rates_bonds_fast_path")
        self.assertEqual(response.execution_meta.extras["retrieval_mode"], "fast_current_documents")
        self.assertTrue(response.execution_meta.extras["deep_pass_skipped"])
        self.assertGreaterEqual(len(response.scenario_analysis), 3)
        self.assertGreaterEqual(len(response.execution_strategy), 2)
        self.assertGreaterEqual(len(response.key_metrics), 5)
        self.assertTrue(all(metric.as_of for metric in response.key_metrics))
        self.assertTrue(any(event["event"] == "partial_result" for event in events))

    async def test_topic_pipeline_uses_deep_pass_when_fast_gate_or_evidence_is_missing(self):
        request = TopicRequest(
            question="거시경제와 금리 구조를 감안할 때 지금 TLT가 매력적인지 분석해줘.",
            theme="미국 장기채와 TLT",
            related_tickers=["TLT"],
            top_k=3,
        )
        doc_id = "tlt_macro_1"
        outcome = CollectionOutcome(
            documents=[
                {
                    "doc_id": doc_id,
                    "ticker": "TLT",
                    "symbol": "TLT",
                    "doc_type": "macro",
                    "source": "FRED:DGS30",
                    "published_at": "2026-04-20",
                    "title": "30Y Treasury yield",
                    "text": "30Y Treasury yield remains elevated.",
                }
            ],
            source_results=[SourceCollectionResult("topic_asset:TLT", "ok", 1, 0.1, "ok")],
            current_doc_ids=[doc_id],
        )
        fast_context = [_context_item(doc_id, "30Y Treasury yield remains elevated.")]
        deep_context = [_context_item(doc_id, "Fed communication and supply dynamics add more context.")]
        fast_phase = _phase_result(doc_id, gate_ok=False, final_gate_ok=False, missing_buckets=["latest_catalyst"], scenarios=2, execution=1, metrics=2)
        deep_phase = _phase_result(doc_id, gate_ok=True, final_gate_ok=True, missing_buckets=[])
        events: list[dict] = []

        with patch.object(topic_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko")), \
             patch.object(topic_pipeline, "collect_topic_bundle", return_value=outcome), \
             patch.object(topic_pipeline, "rank_topic_context_fast", return_value=fast_context), \
             patch.object(topic_pipeline, "run_topic_fast_inference", return_value=fast_phase), \
             patch.object(topic_pipeline, "ingest_documents", return_value={"skipped_docs": 1}), \
             patch.object(topic_pipeline, "retrieve_topic_context", return_value=deep_context), \
             patch.object(topic_pipeline, "run_topic_deep_inference", return_value=deep_phase) as deep_infer, \
             patch.object(topic_pipeline, "build_topic_report", return_value=("# report", "<html></html>")), \
             patch.object(topic_pipeline, "save_outputs"):
            response = await topic_pipeline.run_topic_pipeline_async(request, mode="sector_macro", event_sink=events.append)

        deep_infer.assert_called_once()
        self.assertEqual(response.status, "success")
        self.assertFalse(response.execution_meta.extras["deep_pass_skipped"])
        self.assertEqual(response.execution_meta.extras["retrieval_mode"], "deep_qdrant")
        self.assertEqual(response.execution_meta.extras["ingest_skipped_docs"], 1)
        self.assertIn("fast_gate", response.execution_meta.extras["deep_pass_reason"])
        self.assertIn("missing_evidence_buckets", response.execution_meta.extras["deep_pass_reason"])
        self.assertTrue(any(event["event"] == "partial_result" for event in events))
        self.assertTrue(any(event.get("stage") == "ingest" for event in events))

    async def test_topic_pipeline_repairs_valid_but_incomplete_final_payload(self):
        request = TopicRequest(
            question="거시경제와 금리 구조를 감안할 때 지금 TLT가 매력적인지 분석해줘.",
            theme="미국 장기채와 TLT",
            related_tickers=["TLT"],
            top_k=3,
        )
        doc_id = "tlt_doc_1"
        outcome = CollectionOutcome(
            documents=[
                {
                    "doc_id": doc_id,
                    "ticker": "TLT",
                    "symbol": "TLT",
                    "doc_type": "macro",
                    "source": "FRED:DGS30",
                    "published_at": "2026-04-20",
                    "title": "30Y Treasury yield",
                    "text": "30Y Treasury yield remains elevated.",
                }
            ],
            source_results=[SourceCollectionResult("topic_asset:TLT", "ok", 1, 0.1, "ok")],
            current_doc_ids=[doc_id],
        )
        fast_context = [_context_item(doc_id, "30Y Treasury yield remains elevated.")]
        deep_context = [
            _context_item(doc_id, "Fed path and Treasury yield remain important."),
            _context_item("tlt_market_1", "TLT price curve premium and duration sensitivity affect valuation."),
        ]
        fast_phase = _phase_result(doc_id, gate_ok=False, final_gate_ok=False, missing_buckets=["latest_catalyst"], scenarios=2, execution=1, metrics=2)
        deep_phase = _phase_result(doc_id, gate_ok=True, final_gate_ok=False, missing_buckets=["latest_catalyst"], scenarios=3, execution=0, metrics=3)

        with patch.object(topic_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko")), \
             patch.object(topic_pipeline, "collect_topic_bundle", return_value=outcome), \
             patch.object(topic_pipeline, "rank_topic_context_fast", return_value=fast_context), \
             patch.object(topic_pipeline, "run_topic_fast_inference", return_value=fast_phase), \
             patch.object(topic_pipeline, "ingest_documents", return_value={"skipped_docs": 1}), \
             patch.object(topic_pipeline, "retrieve_topic_context", return_value=deep_context), \
             patch.object(topic_pipeline, "run_topic_deep_inference", return_value=deep_phase), \
             patch.object(topic_pipeline, "build_topic_report", return_value=("# report", "<html></html>")), \
             patch.object(topic_pipeline, "save_outputs"):
            response = await topic_pipeline.run_topic_pipeline_async(request, mode="sector_macro")

        self.assertEqual(response.status, "success")
        self.assertIsNone(response.error_metadata)
        self.assertGreaterEqual(len(response.execution_strategy), 2)
        self.assertIn("최종 섹션 누락", response.execution_meta.extras["recovered_errors"][0])

    async def test_topic_pipeline_returns_decision_fallback_when_fast_json_is_truncated(self):
        request = TopicRequest(
            question="거시경제를 다방면으로 분석해봤을 때 지금의 금리 수준과 채권의 가격이 매력적인지 분석",
            theme="TLT",
            related_tickers=["TLT"],
            top_k=3,
        )
        doc_id = "tlt_macro_1"
        outcome = CollectionOutcome(
            documents=[
                {
                    "doc_id": doc_id,
                    "ticker": "TLT",
                    "symbol": "TLT",
                    "doc_type": "macro",
                    "source": "FRED:DGS30",
                    "published_at": "2026-04-20",
                    "title": "30Y Treasury yield",
                    "text": "30Y Treasury yield remains elevated and Fed path is important.",
                }
            ],
            source_results=[SourceCollectionResult("topic_asset:TLT", "ok", 1, 0.1, "ok")],
            current_doc_ids=[doc_id],
        )
        fast_context = [
            _context_item(doc_id, "30Y Treasury yield remains elevated and real yields matter."),
            _context_item("tlt_market_1", "TLT price curve premium and duration sensitivity affect valuation."),
        ]
        events: list[dict] = []

        with patch.object(topic_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko")), \
             patch.object(topic_pipeline, "collect_topic_bundle", return_value=outcome), \
             patch.object(topic_pipeline, "rank_topic_context_fast", return_value=fast_context), \
             patch.object(topic_pipeline, "run_topic_fast_inference", side_effect=ValueError("[Topic] JSON truncated or unclosed.")), \
             patch.object(topic_pipeline, "run_topic_deep_inference") as deep_infer, \
             patch.object(topic_pipeline, "save_outputs"):
            response = await topic_pipeline.run_topic_pipeline_async(request, mode="sector_macro", event_sink=events.append)

        deep_infer.assert_not_called()
        self.assertEqual(response.status, "success")
        self.assertIsNone(response.error_metadata)
        self.assertIn("LLM 구조화 출력 실패", response.execution_meta.extras["recovered_errors"][0])
        self.assertEqual(response.execution_meta.extras["warning_evidence_buckets"], ["latest_catalyst"])
        self.assertGreaterEqual(len(response.asset_overview), 1)
        self.assertGreaterEqual(len(response.macro_regime) + len(response.rate_structure) + len(response.investment_judgment), 3)
        self.assertGreaterEqual(len(response.scenario_analysis), 3)
        self.assertGreaterEqual(len(response.execution_strategy), 2)
        self.assertGreaterEqual(len(response.key_drivers), 2)
        self.assertGreaterEqual(len(response.key_risks), 2)
        self.assertGreaterEqual(len(response.key_metrics), 3)
        self.assertTrue(response.executive_summary)
        self.assertTrue(any(event["event"] == "partial_result" for event in events))

    async def test_topic_pipeline_returns_decision_fallback_when_deep_json_is_truncated(self):
        request = TopicRequest(
            question="거시경제를 다방면으로 분석해봤을 때 지금의 금리 수준과 채권의 가격이 매력적인지 분석",
            theme="TLT",
            related_tickers=["TLT"],
            top_k=3,
        )
        doc_id = "tlt_macro_1"
        outcome = CollectionOutcome(
            documents=[
                {
                    "doc_id": doc_id,
                    "ticker": "TLT",
                    "symbol": "TLT",
                    "doc_type": "macro",
                    "source": "FRED:DGS30",
                    "published_at": "2026-04-20",
                    "title": "30Y Treasury yield",
                    "text": "30Y Treasury yield remains elevated.",
                }
            ],
            source_results=[SourceCollectionResult("topic_asset:TLT", "ok", 1, 0.1, "ok")],
            current_doc_ids=[doc_id],
        )
        fast_context = [_context_item(doc_id, "30Y Treasury yield remains elevated.")]
        deep_context = [
            _context_item(doc_id, "Fed communication and Treasury supply dynamics add context."),
            _context_item("tlt_market_1", "TLT price curve premium and duration sensitivity affect valuation."),
        ]
        fast_phase = _phase_result(doc_id, gate_ok=False, final_gate_ok=False, missing_buckets=["latest_catalyst"], scenarios=2, execution=1, metrics=2)
        events: list[dict] = []

        with patch.object(topic_pipeline, "load_settings", return_value=SimpleNamespace(output_language="ko")), \
             patch.object(topic_pipeline, "collect_topic_bundle", return_value=outcome), \
             patch.object(topic_pipeline, "rank_topic_context_fast", return_value=fast_context), \
             patch.object(topic_pipeline, "run_topic_fast_inference", return_value=fast_phase), \
             patch.object(topic_pipeline, "ingest_documents", return_value={"skipped_docs": 1}), \
             patch.object(topic_pipeline, "retrieve_topic_context", return_value=deep_context), \
             patch.object(topic_pipeline, "run_topic_deep_inference", side_effect=ValueError("[Topic] JSON truncated or unclosed.")), \
             patch.object(topic_pipeline, "build_topic_report", return_value=("# report", "<html></html>")), \
             patch.object(topic_pipeline, "save_outputs"):
            response = await topic_pipeline.run_topic_pipeline_async(request, mode="sector_macro", event_sink=events.append)

        self.assertEqual(response.status, "success")
        self.assertIsNone(response.error_metadata)
        self.assertIn("LLM 심화 보강 출력 실패", response.execution_meta.extras["recovered_errors"][0])
        self.assertEqual(response.execution_meta.extras["warning_evidence_buckets"], ["latest_catalyst"])
        self.assertFalse(response.execution_meta.extras["deep_pass_skipped"])
        self.assertGreaterEqual(len(response.scenario_analysis), 3)
        self.assertGreaterEqual(len(response.execution_strategy), 2)
        self.assertGreaterEqual(len(response.key_drivers), 2)
        self.assertGreaterEqual(len(response.key_risks), 2)
        self.assertGreaterEqual(len(response.key_metrics), 3)
        self.assertTrue(any(event.get("phase") == "deep" and event.get("status") == "degraded" for event in events))


if __name__ == "__main__":
    unittest.main()
