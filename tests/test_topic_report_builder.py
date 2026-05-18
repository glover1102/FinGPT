import unittest

from core.schemas.response import Citation, ExecutionMeta, KeyMetric
from core.schemas.retrieval import RetrievalItem
from core.schemas.topic import (
    DecisionSection,
    ExecutionStrategy,
    ScenarioAnalysis,
    TickerTouchpoint,
    TopicResponse,
)
from pipelines.analyze.topic_report_builder import build_topic_report


class TopicReportBuilderTests(unittest.TestCase):
    def test_topic_report_renders_decision_grade_memo_sections(self):
        response = TopicResponse(
            question="TLT의 금리/채권 가격 매력도를 분석",
            theme="TLT 금리와 채권 가격 매력도",
            mode="sector_macro",
            executive_summary="TLT는 단기 변동성은 크지만 중장기 금리 하락 시 보상이 커질 수 있습니다.",
            core_thesis="장기금리가 안정되거나 하락하면 TLT의 듀레이션 노출은 비대칭 보상을 만들 수 있습니다.",
            asset_overview=[
                DecisionSection(
                    title="iShares 20+ Year Treasury Bond ETF",
                    bullets=["만기 20년 이상 미국 국채에 투자합니다.", "높은 듀레이션 때문에 금리 변화에 민감합니다."],
                    conclusion="금리 방향성이 투자 성과의 핵심입니다.",
                    evidence_doc_ids=["doc-1"],
                )
            ],
            macro_regime=[
                DecisionSection(
                    title="성장/물가/Fed",
                    bullets=["성장은 둔화됐지만 침체 확정은 아닙니다.", "물가 둔화 여부가 금리 인하 시점을 좌우합니다."],
                    conclusion="완화 전환 기대는 있으나 확인이 필요합니다.",
                    evidence_doc_ids=["doc-2"],
                )
            ],
            rate_structure=[
                DecisionSection(
                    title="장기금리",
                    bullets=["장기금리 수준이 높아 캐리 매력은 개선됐습니다."],
                    conclusion="추가 상승 시 가격 하락 위험도 큽니다.",
                    evidence_doc_ids=["doc-2"],
                )
            ],
            scenario_analysis=[
                ScenarioAnalysis(
                    scenario="경기 둔화 + 금리 하락",
                    probability="중간 이상",
                    expected_outcome="장기금리 하락",
                    asset_implication="TLT 가격 상승",
                    decision_read="분할 매수에 우호적",
                    evidence_doc_ids=["doc-2"],
                )
            ],
            investment_judgment=[
                DecisionSection(
                    title="최종 판단",
                    bullets=["단기 트레이딩은 위험합니다.", "중장기 포지션은 조건부로 유효합니다."],
                    conclusion="확실한 저점은 아니지만 매력 구간에 진입했습니다.",
                    evidence_doc_ids=["doc-1", "doc-2"],
                )
            ],
            execution_strategy=[
                ExecutionStrategy(
                    strategy="분할 매수",
                    trigger="장기금리 안정 확인",
                    rationale="듀레이션 자산은 진입 시점 위험을 나눠야 합니다.",
                    risk_control="금리 재상승 시 비중 확대를 중단합니다.",
                    evidence_doc_ids=["doc-2"],
                )
            ],
            related_tickers=[TickerTouchpoint(ticker="TLT", role="proxy", rationale="장기 국채 ETF")],
            key_metrics=[KeyMetric(name="듀레이션", value="높음", as_of="2026-04-20", context="금리 민감도", evidence_doc_ids=["doc-1"])],
            citations=[Citation(source="FRED", title="30Y Treasury", date="2026-04-20", doc_id="doc-2")],
            raw_context=[
                RetrievalItem(
                    source="issuer:iShares",
                    title="TLT profile",
                    date="2026-04-20",
                    chunk="TLT profile",
                    score=0.9,
                    metadata={"doc_id": "doc-1"},
                )
            ],
        )

        markdown, html = build_topic_report(response, language="ko")

        self.assertIn("## Decision Summary", markdown)
        self.assertIn("## Quant Snapshot", markdown)
        self.assertIn("## Evidence-backed Core Analysis", markdown)
        self.assertIn("### (1) 대상/주제 개요", markdown)
        self.assertIn("### (4) Scenario Table", markdown)
        self.assertIn("## Synthesis", markdown)
        self.assertIn("## Decision Edge", markdown)
        self.assertIn("분할 매수", markdown)
        self.assertIn("기준일: 2026-04-20", markdown)
        self.assertIn("확실한 저점은 아니지만", markdown)
        self.assertIn("Evidence-backed Core Analysis", html)
        self.assertIn("경기 둔화 + 금리 하락", html)

    def test_topic_report_uses_asset_class_specific_labels(self):
        response = TopicResponse(
            question="TLT 금리 민감도",
            theme="TLT",
            mode="sector_macro",
            executive_summary="TLT는 장기금리 변화에 민감합니다.",
            core_thesis="듀레이션과 금리 경로가 핵심입니다.",
            execution_meta=ExecutionMeta(extras={"asset_class": "rates_bonds"}),
        )

        markdown, _ = build_topic_report(response, language="ko")

        self.assertIn("자산 개요 / 듀레이션 특성", markdown)
        self.assertIn("금리 곡선 / 실질금리 / 기간 프리미엄", markdown)


if __name__ == "__main__":
    unittest.main()
