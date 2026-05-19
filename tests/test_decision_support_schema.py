from core.schemas.response import AnalysisResponse, ExecutionMeta, KeyMetric
from core.schemas.retrieval import RetrievalItem
from core.utils.decision_support import enrich_research_response
from core.utils.query_planner import plan_query


def test_minimal_legacy_response_still_validates_with_new_defaults():
    response = AnalysisResponse(
        ticker="MSFT",
        question="risk",
        summary="summary",
        sentiment="Neutral",
        conclusion="conclusion",
    )
    assert response.decision_view.rating == "neutral"
    assert response.scenario_analysis.base_case.probability == 0.0
    assert response.quality_metrics.numeric_grounding_rate == 0.0


def test_enrichment_adds_decision_fields_and_quality_metrics():
    response = AnalysisResponse(
        ticker="TLT",
        question="금리와 채권 매력도",
        summary="장기채 판단은 금리 경로에 좌우됩니다.",
        sentiment="Neutral",
        confidence=0.8,
        conclusion="중립적 관찰이 필요합니다.",
        bull_points=["금리 하락 시 듀레이션 효과가 긍정적입니다."],
        bear_points=["인플레이션 재가속은 장기금리 상승 리스크입니다."],
        bull_evidence_ids=[["doc_1"]],
        bear_evidence_ids=[["doc_1"]],
        key_metrics=[
            KeyMetric(
                name="10Y Treasury Yield",
                value="4.35",
                unit="%",
                as_of="2026-05-01",
                source="FRED",
                evidence_doc_ids=["doc_1"],
            )
        ],
        raw_context=[
            RetrievalItem(
                source="FRED",
                title="10Y Treasury Yield",
                date="2026-05-01",
                chunk="TLT 10Y Treasury Yield 4.35% as of 2026-05-01",
                score=0.9,
                metadata={"doc_id": "doc_1", "bucket": "treasury_yields"},
            )
        ],
        execution_meta=ExecutionMeta(),
    )
    enriched = enrich_research_response(response, retrieval_plan=plan_query("TLT", response.question))
    assert enriched.decision_view.rating in {"neutral", "bullish", "watchlist"}
    assert enriched.scenario_analysis.base_case.evidence_doc_ids
    assert enriched.quality_metrics.numeric_grounding_rate == 1.0
    assert "retrieval_plan" in enriched.execution_meta.extras
    assert enriched.evidence_quality["doc_1"].overall_score > 0.70
