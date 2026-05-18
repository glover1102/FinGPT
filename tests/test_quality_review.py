from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import quality_review
from core.schemas.response import AnalysisResponse, Citation, ExecutionMeta, KeyMetric
from core.schemas.topic import DecisionSection, ExecutionStrategy, KeyDriver, ScenarioAnalysis, TopicResponse


class QualityReviewTests(unittest.TestCase):
    def test_run_quality_review_supports_latency_measurement_for_topic_suite(self) -> None:
        analysis_case = {
            "suite": "analysis",
            "category": "A",
            "desc": "analysis case",
            "ticker": "MSFT",
            "question": "질문",
            "lookback_days": 14,
            "min_citations": 1,
        }
        topic_case = {
            "suite": "topic",
            "category": "T",
            "desc": "topic case",
            "runner": "topic",
            "theme": "미국 장기채와 TLT",
            "question": "지금 TLT가 매력적인지 분석해줘.",
            "related_tickers": ["TLT"],
            "lookback_days": 30,
            "top_k": 8,
            "min_citations": 1,
            "min_scenarios": 3,
            "min_execution": 2,
            "min_metrics": 3,
        }

        analysis_response = AnalysisResponse(
            ticker="MSFT",
            question="질문",
            status="success",
            summary="한국어 요약입니다.",
            bull_points=["상승 요인 1", "상승 요인 2"],
            bear_points=["리스크 1", "리스크 2"],
            sentiment="Neutral",
            conclusion="한국어 결론입니다.",
            citations=[Citation(source="news", title="기사", date="2026-04-24", doc_id="doc1")],
            raw_context=[{"source": "news", "title": "기사", "date": "2026-04-24", "chunk": "본문", "score": 0.9, "metadata": {"doc_id": "doc1"}}],
        )
        topic_response = TopicResponse(
            question="질문",
            theme="미국 장기채와 TLT",
            mode="sector_macro",
            status="success",
            executive_summary="한국어 요약입니다.",
            core_thesis="중장기 기대값은 유효합니다.",
            asset_overview=[DecisionSection(title="개요", bullets=["장기채 ETF"], conclusion="듀레이션 민감도 큼", evidence_doc_ids=["doc1"])],
            macro_regime=[DecisionSection(title="거시", bullets=["성장 둔화"], conclusion="완화 기대", evidence_doc_ids=["doc1"])],
            rate_structure=[DecisionSection(title="금리", bullets=["실질금리 높음"], conclusion="변동성 큼", evidence_doc_ids=["doc1"])],
            scenario_analysis=[
                ScenarioAnalysis(scenario="시나리오 1", probability="중간", expected_outcome="금리 하락", asset_implication="우호적", decision_read="매수 준비", evidence_doc_ids=["doc1"]),
                ScenarioAnalysis(scenario="시나리오 2", probability="중간", expected_outcome="금리 횡보", asset_implication="중립", decision_read="분할 접근", evidence_doc_ids=["doc1"]),
                ScenarioAnalysis(scenario="시나리오 3", probability="낮음", expected_outcome="금리 재상승", asset_implication="비우호적", decision_read="보수 대응", evidence_doc_ids=["doc1"]),
            ],
            investment_judgment=[DecisionSection(title="판단", bullets=["분할 접근"], conclusion="중립 이상", evidence_doc_ids=["doc1"])],
            execution_strategy=[
                ExecutionStrategy(strategy="분할 매수", trigger="금리 안정", rationale="타이밍 리스크 완화", risk_control="추격 자제", evidence_doc_ids=["doc1"]),
                ExecutionStrategy(strategy="확인 후 확대", trigger="연준 완화 신호", rationale="추세 확인", risk_control="비중 제한", evidence_doc_ids=["doc1"]),
            ],
            key_drivers=[
                KeyDriver(text="디스인플레이션 진전", direction="supporting", evidence_doc_ids=["doc1"]),
                KeyDriver(text="성장 둔화", direction="supporting", evidence_doc_ids=["doc1"]),
            ],
            key_risks=[
                KeyDriver(text="인플레이션 재가속", direction="opposing", evidence_doc_ids=["doc1"]),
                KeyDriver(text="국채 공급 확대", direction="opposing", evidence_doc_ids=["doc1"]),
            ],
            key_metrics=[
                KeyMetric(name="30년 금리", value="4.6%", context="장기 할인율", evidence_doc_ids=["doc1"]),
                KeyMetric(name="실질금리", value="2.1%", context="긴축 강도", evidence_doc_ids=["doc1"]),
                KeyMetric(name="듀레이션", value="17", context="가격 민감도", evidence_doc_ids=["doc1"]),
            ],
            citations=[Citation(source="news", title="기사", date="2026-04-24", doc_id="doc1")],
            raw_context=[{"source": "news", "title": "기사", "date": "2026-04-24", "chunk": "본문", "score": 0.9, "metadata": {"doc_id": "doc1"}}],
            execution_meta=ExecutionMeta(
                extras={
                    "phase": "final",
                    "stage_timings": {"collect": 1.0, "retrieve_fast": 0.4, "infer_fast": 12.0, "infer_deep": 18.0},
                    "cache_hit": True,
                    "retrieval_mode": "deep_qdrant",
                    "deep_pass_reason": ["fast_gate"],
                    "deep_pass_skipped": False,
                    "fast_gate": {"ok": True},
                    "final_gate": {"ok": True},
                    "evidence_bucket_counts": {"macro": 1, "asset_specific": 1, "market_structure": 1, "latest_catalyst": 1},
                    "missing_evidence_buckets": [],
                }
            ),
        )

        async def fake_analysis(_request):
            return analysis_response

        async def fake_topic(_request, mode="concept", event_sink=None):
            if event_sink is not None:
                event_sink({"event": "partial_result", "payload": {"status": "partial"}})
                event_sink({"event": "pipeline_completed", "elapsed_s": 31.2})
            return topic_response

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "quality_review_results.json"
            with patch.object(quality_review, "ANALYSIS_CASES", [analysis_case]), \
                 patch.object(quality_review, "TOPIC_CASES", [topic_case]), \
                 patch.object(quality_review, "run_preflight", return_value={"passed": True, "checks": []}), \
                 patch.object(quality_review, "run_pipeline_async", side_effect=fake_analysis), \
                 patch.object(quality_review, "run_topic_pipeline_async", side_effect=fake_topic):
                report = asyncio.run(
                    quality_review.run_quality_review(
                        suite="all",
                        output_path=str(output_path),
                        measure_latency=True,
                    )
                )

            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(report["suite"], "all")
        self.assertTrue(report["measure_latency"])
        self.assertEqual(report["summary"]["total"], 2)
        self.assertTrue(report["summary"]["gate_passed"])
        self.assertIn("latency", report["summary"])
        self.assertEqual(len(payload["cases"]), 2)
        topic_case_payload = next(case for case in payload["cases"] if case["suite"] == "topic")
        self.assertEqual(topic_case_payload["latency"]["retrieval_mode"], "deep_qdrant")
        self.assertFalse(topic_case_payload["latency"]["deep_pass_skipped"])
        self.assertIsNotNone(topic_case_payload["latency"]["partial_result_s"])

    def test_run_quality_review_supports_case_window_and_resume(self) -> None:
        cases = [
            {"suite": "analysis", "category": "A", "desc": "case 1", "ticker": "MSFT", "question": "q1"},
            {"suite": "analysis", "category": "A", "desc": "case 2", "ticker": "AAPL", "question": "q2"},
        ]

        async def fake_result(case):
            return {
                "suite": case["suite"],
                "category": case["category"],
                "desc": case["desc"],
                "ticker": case["ticker"],
                "question": case["question"],
                "mode": "single_ticker",
                "status": "success",
                "language_ok": True,
                "model_used": "test",
                "elapsed_s": 0.01,
                "gate_pass": True,
                "gate_reason": "ok",
            }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "quality_review_results.json"
            with patch.object(quality_review, "ANALYSIS_CASES", cases), \
                 patch.object(quality_review, "TOPIC_CASES", []), \
                 patch.object(quality_review, "run_preflight", return_value={"passed": True, "checks": []}), \
                 patch.object(quality_review, "_run_analysis_case", side_effect=fake_result) as runner:
                report = asyncio.run(
                    quality_review.run_quality_review(
                        suite="analysis",
                        output_path=str(output_path),
                        case_offset=1,
                        case_limit=1,
                    )
                )

            self.assertEqual(runner.call_count, 1)
            self.assertEqual(report["summary"]["selected_case_count"], 1)
            self.assertEqual(report["cases"][0]["desc"], "case 2")
            self.assertTrue(json.loads(output_path.read_text(encoding="utf-8"))["summary"]["gate_passed"])

            resume_path = Path(tmp) / "resume.json"
            resume_path.write_text(json.dumps({"cases": [report["cases"][0]]}), encoding="utf-8")
            resumed_output = Path(tmp) / "resumed.json"
            with patch.object(quality_review, "ANALYSIS_CASES", cases), \
                 patch.object(quality_review, "TOPIC_CASES", []), \
                 patch.object(quality_review, "run_preflight", return_value={"passed": True, "checks": []}), \
                 patch.object(quality_review, "_run_analysis_case", side_effect=fake_result) as resumed_runner:
                resumed = asyncio.run(
                    quality_review.run_quality_review(
                        suite="analysis",
                        output_path=str(resumed_output),
                        resume_from=str(resume_path),
                    )
                )

            self.assertEqual(resumed_runner.call_count, 1)
            self.assertEqual(resumed["summary"]["skipped_resume"], 1)
            self.assertEqual(len(resumed["cases"]), 2)


if __name__ == "__main__":
    unittest.main()
