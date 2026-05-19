from __future__ import annotations

import unittest

from core.utils.validation_metrics import (
    claim_evidence_date_coverage,
    citation_count,
    decision_richness,
    detect_mode,
    duplicate_paragraph_ratio,
    evidence_bucket_policy,
    evidence_count,
    has_warning_only_partial,
    language_ok,
    metric_as_of_coverage,
    partial_reason_is_actionable,
    quant_snapshot_present,
    topic_bucket_coverage,
    topic_fast_gate,
    topic_final_gate,
)


def _topic_payload() -> dict:
    return {
        "mode": "sector_macro",
        "theme": "미국 장기채 TLT",
        "executive_summary": "장기금리 안정 여부가 TLT 판단의 핵심입니다.",
        "core_thesis": "중장기 관점에서는 금리 하락 선택지가 있지만 단기 변동성은 남아 있습니다.",
        "asset_overview": [
            {
                "title": "대상 자산 개요",
                "bullets": ["TLT는 만기 20년 이상 미국 국채에 노출됩니다."],
                "conclusion": "듀레이션 민감도가 높습니다.",
            }
        ],
        "macro_regime": [
            {
                "title": "거시 환경",
                "bullets": ["성장은 둔화되고 인플레이션은 완만히 내려오고 있습니다."],
                "conclusion": "정책 전환 기대가 장기채에 우호적일 수 있습니다.",
            }
        ],
        "rate_structure": [
            {
                "title": "금리 구조",
                "bullets": ["실질금리와 장기금리 수준이 가격 매력도의 핵심 변수입니다."],
                "conclusion": "장기채 가격에는 반등 여력과 추가 조정 리스크가 함께 있습니다.",
            }
        ],
        "investment_judgment": [
            {
                "title": "판단",
                "bullets": ["중장기 기대값은 양호하지만 단기 타이밍은 불확실합니다."],
                "conclusion": "분할 진입이 합리적입니다.",
            }
        ],
        "scenario_analysis": [
            {
                "scenario": "경기 둔화와 금리 인하",
                "expected_outcome": "장기금리 하락",
                "asset_implication": "TLT 상승",
                "decision_read": "우호적",
            },
            {
                "scenario": "연착륙과 금리 횡보",
                "expected_outcome": "박스권",
                "asset_implication": "쿠폰 중심 수익",
                "decision_read": "중립",
            },
            {
                "scenario": "인플레이션 재가속",
                "expected_outcome": "장기금리 재상승",
                "asset_implication": "TLT 조정",
                "decision_read": "비우호적",
            },
        ],
        "execution_strategy": [
            {"strategy": "분할 매수", "trigger": "장기금리 안정", "rationale": "타이밍 리스크 완화"},
            {"strategy": "확인 후 추가", "trigger": "실질금리 하락 전환", "rationale": "추세 확인"},
        ],
        "key_drivers": [
            {"text": "디스인플레이션이 이어지면 장기채에 우호적입니다."},
            {"text": "성장 둔화는 안전자산 수요를 자극할 수 있습니다."},
        ],
        "key_risks": [
            {"text": "인플레이션 재가속은 장기금리 재상승 리스크입니다."},
            {"text": "국채 공급 부담은 term premium 상승으로 이어질 수 있습니다."},
        ],
        "key_metrics": [
            {"name": "30Y yield", "value": "4.6%", "as_of": "2026-04-20", "context": "장기채 할인율"},
            {"name": "Real yield", "value": "2.1%", "as_of": "2026-04-20", "context": "긴축 강도"},
            {"name": "Duration", "value": "16.8", "as_of": "2026-04-20", "context": "가격 민감도"},
        ],
        "citations": [{"source": "FRED", "title": "UST curve", "date": "2026-04-24", "doc_id": "doc-1"}],
        "raw_context": [{"date": "2026-04-20", "metadata": {"doc_id": "doc-1", "parent_doc_id": "doc-1"}, "chunk": "long-end yields remain elevated"}],
    }


class ValidationMetricsTests(unittest.TestCase):
    def test_detect_mode_for_analysis_and_topic(self) -> None:
        self.assertEqual(detect_mode({"ticker": "MSFT", "summary": "요약"}), "single_ticker")
        self.assertEqual(detect_mode({"theme": "AI semis", "core_thesis": "투자 판단", "mode": "sector_macro"}), "sector_macro")
        self.assertEqual(detect_mode({"core_thesis": "투자 판단", "scenario_analysis": []}), "concept")

    def test_language_ok_prefers_korean_dominance(self) -> None:
        self.assertTrue(
            language_ok(
                {
                    "summary": "요약은 한국어입니다.",
                    "conclusion": "결론도 한국어입니다.",
                    "bull_points": ["상승 요인 하나", "상승 요인 둘"],
                    "bear_points": ["리스크 하나", "리스크 둘"],
                }
            )
        )
        self.assertFalse(
            language_ok(
                {
                    "summary": "This summary is mostly English.",
                    "conclusion": "Conclusion is also English.",
                    "bull_points": ["Catalyst"],
                    "bear_points": ["Risk"],
                }
            )
        )

    def test_language_ok_ignores_english_citation_titles(self) -> None:
        korean_claim = "\uae08\ub9ac \ud558\ub77d \uac00\ub2a5\uc131\uc774 \uc7a5\uae30\ucc44 \uac00\uaca9\uc5d0 \uc911\uc694\ud55c \uc0c1\uc2b9 \ub3d9\uc778\uc785\ub2c8\ub2e4."
        payload = {
            "summary": korean_claim + " (FRED DGS30: Market Yield on U.S. Treasury Securities at 30-Year Constant Maturity)",
            "conclusion": "\ud604\uc7ac \ud310\ub2e8\uc740 \uc911\ub9bd\uc774\uc9c0\ub9cc \uc2e4\uc9c8\uae08\ub9ac\uc640 \ub4c0\ub808\uc774\uc158 \ubbfc\uac10\ub3c4\ub97c \ud568\uaed8 \ubd10\uc57c \ud569\ub2c8\ub2e4.",
            "bull_points": [korean_claim, "\ubd84\ud560 \uc9c4\uc785\uc740 \ub2e8\uae30 \uae08\ub9ac \ubcc0\ub3d9\uc131\uc744 \uc904\uc785\ub2c8\ub2e4."],
            "bear_points": [
                "\uc778\ud50c\ub808\uc774\uc158 \uc7ac\uac00\uc18d\uc740 \uc7a5\uae30\uae08\ub9ac \uc0c1\uc2b9\uc73c\ub85c \uc5f0\uacb0\ub420 \uc218 \uc788\uc2b5\ub2c8\ub2e4. (SCHQ vs. TLT: Same Treasury DNA, Very Different Cost and Duration)",
                "\uc7ac\uc815\uc801\uc790\uc640 \uad6d\ucc44 \uacf5\uae09\uc740 \uae30\uac04 \ud504\ub9ac\ubbf8\uc5c4\uc744 \uc790\uadf9\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.",
            ],
        }

        self.assertTrue(language_ok(payload))

    def test_language_ok_ignores_bracketed_english_citation_titles(self) -> None:
        payload = {
            "summary": "JPM은 실적 성장과 주가 강세를 바탕으로 긍정적인 투자 기회를 제공하지만 거시 불확실성도 함께 봐야 합니다.",
            "conclusion": "현재 판단은 균형적이며, 이익 성장 지속성과 신용 사이클 악화 여부가 핵심 변수입니다.",
            "bull_points": [
                "Q1 실적 성장과 주가 강세는 긍정적인 투자 근거입니다. [JPMorgan Chase Stock Opinions on Q1 Earnings Beat - Quiver Quantitative]",
                "자본 여력과 비용 통제는 경기 둔화 구간에서도 방어력을 제공합니다.",
            ],
            "bear_points": [
                "지정학적 불안정성은 투자은행 수익과 신용비용에 부정적으로 작용할 수 있습니다. [Is JPM a Buy Before Q1 Earnings in a Volatile Geopolitical Backdrop? - Yahoo Finance]",
                "금리 경로가 흔들리면 순이자마진과 밸류에이션에 압박이 생길 수 있습니다.",
            ],
        }

        self.assertTrue(language_ok(payload))

    def test_decision_richness_for_analysis(self) -> None:
        rich = decision_richness(
            {
                "summary": "요약",
                "conclusion": "결론",
                "bull_points": ["강점 1", "강점 2"],
                "bear_points": ["약점 1", "약점 2"],
            }
        )
        self.assertTrue(rich["ok"])
        self.assertEqual(rich["checks"]["bull_points"], 2)

    def test_topic_gates(self) -> None:
        payload = _topic_payload()
        fast_gate = topic_fast_gate(payload)
        final_gate = topic_final_gate(payload, minimums={"scenario_analysis": 3, "execution_strategy": 2, "key_metrics": 3})
        self.assertTrue(fast_gate["ok"])
        self.assertTrue(final_gate["ok"])
        self.assertEqual(final_gate["completeness"]["counts"]["decision_sections"], 4)

    def test_evidence_bucket_policy_treats_rates_latest_catalyst_as_warning(self) -> None:
        policy = evidence_bucket_policy(
            "rates_bonds",
            {"macro": 2, "asset_specific": 1, "market_structure": 1, "latest_catalyst": 0},
            reported_missing=["latest_catalyst"],
        )

        self.assertEqual(policy["blocking_missing"], [])
        self.assertEqual(policy["warning_missing"], ["latest_catalyst"])

    def test_evidence_bucket_policy_allows_quant_substitution(self) -> None:
        policy = evidence_bucket_policy(
            "rates_bonds",
            {"macro": 2, "asset_specific": 1, "market_structure": 0, "latest_catalyst": 0},
            reported_missing=["market_structure", "latest_catalyst"],
            substituted_buckets=["market_structure"],
        )

        self.assertEqual(policy["blocking_missing"], [])
        self.assertEqual(policy["warning_missing"], ["latest_catalyst"])

    def test_evidence_bucket_policy_rates_asset_specific_is_warning_only(self) -> None:
        policy = evidence_bucket_policy(
            "rates_bonds",
            {"macro": 2, "asset_specific": 0, "market_structure": 0, "latest_catalyst": 0},
            reported_missing=["asset_specific", "market_structure", "latest_catalyst"],
            substituted_buckets=["market_structure"],
        )

        self.assertEqual(policy["blocking_missing"], [])
        self.assertEqual(policy["warning_missing"], ["asset_specific", "latest_catalyst"])

    def test_evidence_bucket_policy_credit_latest_catalyst_is_warning_only(self) -> None:
        policy = evidence_bucket_policy(
            "credit",
            {"macro": 2, "asset_specific": 0, "market_structure": 0, "latest_catalyst": 0},
            reported_missing=["asset_specific", "market_structure", "latest_catalyst"],
            substituted_buckets=["asset_specific", "market_structure"],
        )

        self.assertEqual(policy["blocking_missing"], [])
        self.assertEqual(policy["warning_missing"], ["latest_catalyst"])

    def test_traceability_metrics_cover_as_of_and_claim_dates(self) -> None:
        payload = _topic_payload()
        payload["key_drivers"][0]["evidence_doc_ids"] = ["doc-1"]
        payload["execution_meta"] = {
            "extras": {
                "quant_snapshot": {"metrics": [{"name": "10Y", "value": "4.5%"}]},
                "evidence_bucket_counts": {"macro": 1, "asset_specific": 1, "market_structure": 0, "latest_catalyst": 0},
                "substituted_buckets": ["market_structure"],
                "warning_evidence_buckets": ["latest_catalyst"],
            }
        }

        self.assertTrue(metric_as_of_coverage(payload)["ok"])
        self.assertTrue(claim_evidence_date_coverage(payload)["ok"])
        self.assertTrue(quant_snapshot_present(payload))
        self.assertIn("market_structure", topic_bucket_coverage(payload)["substituted"])
        self.assertTrue(partial_reason_is_actionable({**payload, "status": "partial", "uncertainty": "근거 bucket 누락: latest_catalyst"}))

    def test_claim_date_coverage_ignores_unknown_evidence_sentinel(self) -> None:
        payload = {
            "summary": "\uc694\uc57d",
            "conclusion": "\uacb0\ub860",
            "bull_points": ["\uadfc\uac70 \uc788\ub294 \uc8fc\uc7a5", "\uadfc\uac70 \uc5c6\ub294 \uc8fc\uc7a5"],
            "bear_points": ["\ub9ac\uc2a4\ud06c \uc8fc\uc7a5"],
            "bull_evidence_ids": [["doc-1"], ["unknown"]],
            "bear_evidence_ids": [["unknown"]],
            "raw_context": [{"date": "2026-04-24", "metadata": {"doc_id": "doc-1"}}],
        }

        coverage = claim_evidence_date_coverage(payload)
        self.assertTrue(coverage["ok"])
        self.assertEqual(coverage["total"], 1)

    def test_evidence_bucket_policy_blocks_sector_missing_latest_catalyst(self) -> None:
        policy = evidence_bucket_policy(
            "sector_theme",
            {"macro": 2, "asset_specific": 1, "market_structure": 1, "latest_catalyst": 0},
            reported_missing=["latest_catalyst"],
        )

        self.assertEqual(policy["blocking_missing"], ["latest_catalyst"])
        self.assertEqual(policy["warning_missing"], [])

    def test_warning_only_partial_detection_and_counts(self) -> None:
        payload = {
            "status": "partial",
            "summary": "근거 부족으로 일부 결과만 제공합니다.",
            "uncertainty": "증거 부족",
            "citations": [{"source": "news", "title": "x", "date": "2026-01-01"}],
            "raw_context": [{"chunk": "x"}],
        }
        self.assertTrue(has_warning_only_partial(payload))
        self.assertEqual(citation_count(payload), 1)
        self.assertEqual(evidence_count(payload), 1)

    def test_duplicate_paragraph_ratio_detects_repeated_memo_text(self) -> None:
        repeated = "같은 문장이 여러 섹션에 반복되면 리서치 메모의 정보 밀도가 낮아집니다."
        payload = {
            "summary": repeated,
            "conclusion": repeated,
            "bull_points": [repeated, "다른 근거 문장은 정상적으로 허용됩니다."],
            "bear_points": ["하방 리스크는 별도 문장으로 제시됩니다.", "또 다른 리스크 문장입니다."],
        }

        ratio = duplicate_paragraph_ratio(payload)

        self.assertFalse(ratio["ok"])
        self.assertGreater(ratio["duplicates"], 0)

    def test_duplicate_paragraph_ratio_allows_distinct_dense_sections(self) -> None:
        payload = {
            "summary": "요약은 시장 방향성과 핵심 판단을 짧게 제시합니다.",
            "conclusion": "결론은 포지션 크기와 무효화 기준을 별도로 제시합니다.",
            "bull_points": ["상방 근거는 매출 성장률과 가격 모멘텀의 결합입니다.", "두 번째 상방 근거는 마진 개선입니다."],
            "bear_points": ["하방 리스크는 금리 상승과 밸류에이션 압축입니다.", "두 번째 하방 리스크는 수요 둔화입니다."],
        }

        self.assertTrue(duplicate_paragraph_ratio(payload)["ok"])


if __name__ == "__main__":
    unittest.main()
