from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.schemas.retrieval import RetrievalItem
from pipelines.infer import topic_prompt


def _ollama_response(payload: str, done_reason: str = "stop"):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"response": payload, "done_reason": done_reason}
    return response


def _context() -> list[RetrievalItem]:
    return [
        RetrievalItem(
            source="FRED:DGS30",
            title="30Y Treasury yield",
            date="2026-04-20",
            chunk="30Y Treasury yield rose from 4.20% to 4.55% while real yields stayed high.",
            score=0.9,
            metadata={"doc_id": "doc-1", "parent_doc_id": "doc-1"},
        ),
        RetrievalItem(
            source="Google News",
            title="Fed communication",
            date="2026-04-21",
            chunk="Fed officials signaled caution on rate cuts.",
            score=0.8,
            metadata={"doc_id": "doc-2", "parent_doc_id": "doc-2"},
        ),
    ]


def _topic_payload(*, language: str = "ko", scenarios: int = 2, execution: int = 1, metrics: int = 2) -> str:
    is_korean = language == "ko"
    executive_summary = "장기금리 안정 여부가 TLT 판단의 핵심입니다." if is_korean else "Long-end yield stabilization is the key driver for TLT."
    core_thesis = "중장기 기대값은 유효하지만 단기 변동성은 남아 있습니다." if is_korean else "Medium-term asymmetry is favorable but short-term volatility remains."
    driver_1 = "디스인플레이션이 이어지면 장기채에 우호적입니다." if is_korean else "Disinflation would support long duration."
    driver_2 = "성장 둔화는 안전자산 수요를 자극할 수 있습니다." if is_korean else "Growth slowdown can lift safe-haven demand."
    risk_1 = "인플레이션 재가속은 장기금리 재상승 리스크입니다." if is_korean else "Inflation reacceleration is the key risk."
    risk_2 = "국채 공급 확대는 term premium 상승으로 이어질 수 있습니다." if is_korean else "Treasury supply can lift term premium."
    scenario_name = "시나리오" if is_korean else "Scenario"
    probability = "중간" if is_korean else "medium"
    expected = "장기금리 하락" if is_korean else "Long-end yields decline"
    implication = "TLT 반등" if is_korean else "TLT rebounds"
    decision = "분할 접근" if is_korean else "Use staged entry"
    strategy = "분할 매수" if is_korean else "Staged entry"
    trigger = "장기금리 안정" if is_korean else "Long-end stabilization"
    rationale = "타이밍 리스크 완화" if is_korean else "Reduces timing risk"
    metric_name = "30년 금리" if is_korean else "30Y yield"

    payload = {
        "executive_summary": executive_summary,
        "core_thesis": core_thesis,
        "asset_overview": [{"title": "자산 개요" if is_korean else "Asset overview", "bullets": ["TLT는 장기 미국 국채 ETF입니다." if is_korean else "TLT is a long-duration Treasury ETF."], "conclusion": "듀레이션 민감도가 큽니다." if is_korean else "Duration sensitivity is high.", "evidence_doc_ids": ["doc-1"]}],
        "macro_regime": [{"title": "거시 환경" if is_korean else "Macro regime", "bullets": ["성장 둔화와 디스인플레이션이 공존합니다." if is_korean else "Growth is slowing while disinflation continues."], "conclusion": "완화 기대가 채권에 우호적입니다." if is_korean else "Policy easing expectations are supportive.", "evidence_doc_ids": ["doc-1"]}],
        "rate_structure": [{"title": "금리 구조" if is_korean else "Rate structure", "bullets": ["장기금리와 실질금리가 높습니다." if is_korean else "Long-end and real yields remain high."], "conclusion": "가격 반등과 추가 조정 리스크가 공존합니다." if is_korean else "Upside and downside both remain.", "evidence_doc_ids": ["doc-1"]}],
        "scenario_analysis": [
            {
                "scenario": f"{scenario_name} {idx + 1}",
                "probability": probability,
                "expected_outcome": expected,
                "asset_implication": implication,
                "decision_read": decision,
                "evidence_doc_ids": ["doc-1"],
            }
            for idx in range(scenarios)
        ],
        "investment_judgment": [{"title": "판단" if is_korean else "Judgment", "bullets": ["중장기 기대값은 양호합니다." if is_korean else "Medium-term expected value is favorable."], "conclusion": "분할 진입이 적절합니다." if is_korean else "Staged entry is appropriate.", "evidence_doc_ids": ["doc-1"]}],
        "execution_strategy": [
            {
                "strategy": strategy,
                "trigger": trigger,
                "rationale": rationale,
                "risk_control": "추격 자제" if is_korean else "Avoid chasing",
                "evidence_doc_ids": ["doc-1"],
            }
            for _ in range(execution)
        ],
        "key_drivers": [
            {"text": driver_1, "direction": "supporting", "evidence_doc_ids": ["doc-1"]},
            {"text": driver_2, "direction": "supporting", "evidence_doc_ids": ["doc-1"]},
        ],
        "key_risks": [
            {"text": risk_1, "direction": "opposing", "evidence_doc_ids": ["doc-1"]},
            {"text": risk_2, "direction": "opposing", "evidence_doc_ids": ["doc-1"]},
        ],
        "related_tickers": [{"ticker": "TLT", "role": "proxy", "rationale": "장기채 ETF" if is_korean else "Long-duration Treasury ETF"}],
        "key_metrics": [
            {"name": f"{metric_name} {idx + 1}", "value": f"{4.5 + idx:.1f}%", "context": "장기금리" if is_korean else "long-end yield", "evidence_doc_ids": ["doc-1"]}
            for idx in range(metrics)
        ],
        "catalyst_timeline": {"near_term": ["CPI"], "mid_term": ["FOMC"], "long_term": []},
        "open_questions": ["실질금리가 언제 내려올까?" if is_korean else "When will real yields ease?"],
        "uncertainty": "장기금리 경로가 불확실합니다." if is_korean else "The path of long-end yields remains uncertain.",
        "cited_doc_ids": ["doc-1"],
    }
    return json.dumps(payload, ensure_ascii=False)


class TopicPromptTests(unittest.TestCase):
    def test_topic_prompt_includes_cross_asset_playbook_and_required_sections(self):
        context = _context()
        plan = topic_prompt.TOPIC_PLAYBOOKS["commodity"]
        evidence_pack = topic_prompt.build_evidence_pack("원자재가 매력적인지", "oil market", context, ["USO"], plan)
        self.assertEqual(evidence_pack.metrics[0].as_of, "2026-04-20")

        prompt, chunks = topic_prompt.build_topic_prompt(
            "원자재가 매력적인지",
            "oil market",
            context,
            ["USO"],
            language="ko",
            topic_plan=plan,
            evidence_pack=evidence_pack,
            phase="fast",
        )

        self.assertEqual(chunks, len(context))
        self.assertIn("Domain-specific decision playbook", prompt)
        self.assertIn("Commodities / energy / metals", prompt)
        self.assertIn("Required sections", prompt)
        self.assertIn("Latest catalyst / news", prompt)
        self.assertIn("as_of=2026-04-20", prompt)

    def test_clean_korean_now_phrase_is_not_misclassified_as_gold(self):
        plan = topic_prompt.build_topic_plan(
            "지금 시장이 무시하고 있는 리스크는 어떤 것이 있는지 분석 부탁드립니다",
            "지금 시장이 무시하고 있는 리스크",
            [],
            [],
        )

        self.assertNotEqual(plan.asset_class, "commodity")

    def test_credit_proxy_basket_uses_credit_playbook(self):
        plan = topic_prompt.build_topic_plan(
            "지금 시장이 무시하고 있는 리스크는 어떤 것이 있는지 분석 부탁드립니다",
            "broad market risk",
            ["SPY", "QQQ", "HYG", "LQD", "TLT"],
            [],
        )

        self.assertEqual(plan.asset_class, "credit")

    def test_clean_korean_gold_phrase_still_uses_commodity_playbook(self):
        plan = topic_prompt.build_topic_plan(
            "금 가격과 달러를 기준으로 원자재 매력도를 분석",
            "금 가격",
            [],
            [],
        )

        self.assertEqual(plan.asset_class, "commodity")

    def test_topic_fast_inference_retries_when_korean_requested_but_english_is_returned(self):
        settings = SimpleNamespace(ollama_base_url="http://localhost:11434", output_language="ko")
        english = _topic_payload(language="en")
        korean = _topic_payload(language="ko")

        with patch.object(topic_prompt, "load_settings", return_value=settings), \
             patch.object(topic_prompt, "resolve_model_name", return_value="qwen2.5:7b"), \
             patch.object(topic_prompt.httpx, "post", side_effect=[_ollama_response(english), _ollama_response(korean)]):
            result = topic_prompt.run_topic_fast_inference(
                "지금 TLT가 매력적인지 분석해줘",
                "미국 장기채와 TLT",
                _context(),
                "qwen",
                ["TLT"],
            )

        self.assertEqual(result.retry_count, 1)
        self.assertTrue(result.gate["ok"])
        self.assertIn("TLT", json.dumps(result.payload, ensure_ascii=False))
        self.assertTrue(result.payload["core_thesis"].startswith("중장기"))

    def test_topic_fast_inference_attempts_bounded_repair_for_truncated_json(self):
        settings = SimpleNamespace(ollama_base_url="http://localhost:11434", output_language="ko")

        with patch.object(topic_prompt, "load_settings", return_value=settings), \
             patch.object(topic_prompt, "resolve_model_name", return_value="qwen2.5:7b"), \
             patch.object(topic_prompt.httpx, "post", return_value=_ollama_response('{"executive_summary": "잘린 출력"', done_reason="length")) as post_mock:
            with self.assertRaises(topic_prompt.StructuredOutputError):
                topic_prompt.run_topic_fast_inference(
                    "지금 TLT가 매력적인지 분석해줘",
                    "미국 장기채와 TLT",
                    _context(),
                    "qwen",
                    ["TLT"],
                )

        self.assertEqual(post_mock.call_count, 2)

    def test_topic_deep_inference_skips_llm_when_output_is_already_complete(self):
        settings = SimpleNamespace(ollama_base_url="http://localhost:11434", output_language="ko")
        context = _context()
        plan = topic_prompt.TOPIC_PLAYBOOKS["rates_bonds"]
        existing_output = json.loads(_topic_payload(language="ko", scenarios=3, execution=2, metrics=3))

        with patch.object(topic_prompt, "load_settings", return_value=settings), \
             patch.object(topic_prompt, "resolve_model_name", return_value="qwen2.5:7b"), \
             patch.object(topic_prompt, "determine_deep_fields", return_value=[]), \
             patch.object(topic_prompt.httpx, "post") as post_mock:
            result = topic_prompt.run_topic_deep_inference(
                "지금 TLT가 매력적인지 분석해줘",
                "미국 장기채와 TLT",
                context,
                "qwen",
                ["TLT"],
                existing_output=existing_output,
                topic_plan=plan,
                deep_reason="quality completion",
            )

        post_mock.assert_not_called()
        self.assertEqual(result.selected_fields, [])
        self.assertTrue(result.final_gate["ok"])
        self.assertEqual(result.payload["_meta"]["phase"], "final")


if __name__ == "__main__":
    unittest.main()
