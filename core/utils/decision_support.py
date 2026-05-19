from __future__ import annotations

from typing import Any, Iterable

from core.schemas.response import (
    AnalysisResponse,
    DecisionView,
    ExecutionMeta,
    MonitoringPlan,
    QualityMetrics,
    RiskManagement,
    ScenarioAnalysisBundle,
    ScenarioCase,
)
from core.schemas.topic import TopicResponse
from core.utils.confidence_calibration import apply_confidence_caps, calibration_to_extras
from core.utils.evidence_quality import (
    average_evidence_quality,
    evidence_doc_id,
    freshness_coverage,
    score_evidence_items,
    source_diversity,
)
from core.utils.numeric_grounding import validate_key_metrics
from core.utils.query_planner import RetrievalPlan, plan_to_dict


def _ensure_meta(response: Any) -> ExecutionMeta:
    if getattr(response, "execution_meta", None) is None:
        response.execution_meta = ExecutionMeta()
    if response.execution_meta.extras is None:
        response.execution_meta.extras = {}
    return response.execution_meta


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _first(values: Iterable[Any], default: str = "") -> str:
    for value in values or []:
        text = _clean(value)
        if text:
            return text
    return default


def _flatten_ids(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for value in values or []:
        if isinstance(value, (list, tuple, set)):
            out.extend(str(item) for item in value if item)
        elif value:
            out.append(str(value))
    return list(dict.fromkeys(out))


def _context_doc_ids(response: Any) -> list[str]:
    ids: list[str] = []
    for index, item in enumerate(getattr(response, "raw_context", []) or []):
        ids.append(evidence_doc_id(item, f"doc_{index + 1}"))
    return list(dict.fromkeys(ids))


def _required_bucket_coverage(response: Any, retrieval_plan: RetrievalPlan | dict[str, Any] | None) -> float:
    plan = plan_to_dict(retrieval_plan)
    required = [str(x).lower() for x in plan.get("required_evidence_buckets", []) if x]
    if not required:
        return 0.0
    present: set[str] = set()
    extras = getattr(getattr(response, "execution_meta", None), "extras", {}) or {}
    bucket_counts = extras.get("bucket_counts") or extras.get("topic_bucket_counts") or {}
    if isinstance(bucket_counts, dict):
        present.update(str(key).lower() for key, value in bucket_counts.items() if value)
    for item in getattr(response, "raw_context", []) or []:
        metadata = getattr(item, "metadata", None) or {}
        if isinstance(metadata, dict):
            bucket = metadata.get("bucket") or metadata.get("evidence_bucket")
            if bucket:
                present.add(str(bucket).lower())
    matched = sum(1 for bucket in required if bucket.lower() in present)
    return round(matched / len(required), 4)


def _quality_metrics(
    response: Any,
    *,
    numeric_rate: float,
    evidence_quality_average: float,
    freshness: float,
    diversity: int,
    required_bucket_coverage: float,
) -> QualityMetrics:
    claim_total = 0
    claim_supported = 0

    if isinstance(response, AnalysisResponse):
        for ids in list(response.bull_evidence_ids or []) + list(response.bear_evidence_ids or []):
            claim_total += 1
            if ids:
                claim_supported += 1
        for metric in response.key_metrics:
            claim_total += 1
            if metric.evidence_doc_ids or metric.source or metric.calculation_method or metric.is_deterministic:
                claim_supported += 1
    else:
        for item in list(getattr(response, "key_drivers", []) or []) + list(getattr(response, "key_risks", []) or []):
            claim_total += 1
            if getattr(item, "evidence_doc_ids", None):
                claim_supported += 1
        for item in getattr(response, "scenario_analysis", []) or []:
            claim_total += 1
            if getattr(item, "evidence_doc_ids", None):
                claim_supported += 1
        for metric in getattr(response, "key_metrics", []) or []:
            claim_total += 1
            if metric.evidence_doc_ids or metric.source or metric.calculation_method or metric.is_deterministic:
                claim_supported += 1

    claim_rate = round(claim_supported / claim_total, 4) if claim_total else 0.0
    stale_rate = round(1.0 - freshness, 4) if freshness else 0.0
    return QualityMetrics(
        claim_support_rate=claim_rate,
        numeric_grounding_rate=round(numeric_rate, 4),
        evidence_quality_average=round(evidence_quality_average, 4),
        freshness_coverage=round(freshness, 4),
        stale_context_rate=stale_rate,
        source_diversity=diversity,
        required_bucket_coverage=required_bucket_coverage,
    )


def _analysis_decision(response: AnalysisResponse, final_confidence: float) -> DecisionView:
    sentiment = _clean(response.sentiment).lower()
    if response.status == "failed":
        rating = "watchlist"
    elif "negative" in sentiment or "bear" in sentiment:
        rating = "bearish"
    elif "positive" in sentiment or "bull" in sentiment:
        rating = "bullish"
    elif final_confidence < 0.35:
        rating = "watchlist"
    else:
        rating = "neutral"
    summary = _first([response.conclusion, response.summary], "근거 기반 판단을 생성하려면 추가 데이터 확인이 필요합니다.")
    thesis = _first(response.bull_points, summary)
    view_changes = [*_flatten_ids([])]
    view_changes = [
        _clean(item)
        for item in [
            _first(response.bear_points, ""),
            _first(response.open_questions, ""),
            response.uncertainty,
        ]
        if _clean(item)
    ][:4]
    if not view_changes:
        view_changes = ["핵심 근거 버킷 또는 정량 지표가 악화되면 현재 판단을 재검토해야 합니다."]
    return DecisionView(
        rating=rating,
        time_horizon="medium_term",
        confidence=round(final_confidence, 4),
        decision_summary=summary,
        primary_thesis=thesis,
        what_would_change_my_view=view_changes,
    )


def _topic_decision(response: TopicResponse, final_confidence: float) -> DecisionView:
    positive = [item.text for item in response.key_drivers if getattr(item, "direction", "") == "supporting"]
    negative = [item.text for item in response.key_risks if getattr(item, "direction", "") == "opposing"]
    if response.status == "failed":
        rating = "watchlist"
    elif len(positive) >= len(negative) + 2 and final_confidence >= 0.55:
        rating = "bullish"
    elif len(negative) > len(positive) and final_confidence >= 0.45:
        rating = "bearish"
    else:
        rating = "neutral"
    return DecisionView(
        rating=rating,
        time_horizon="medium_term",
        confidence=round(final_confidence, 4),
        decision_summary=_first([response.executive_summary, response.core_thesis], "근거 기반 판단이 제한적입니다."),
        primary_thesis=_first([response.core_thesis, response.executive_summary], "핵심 논지는 근거 보강 후 확정해야 합니다."),
        what_would_change_my_view=[_clean(x) for x in negative[:3]] or ["누락된 근거 버킷이 채워지면 판단을 재검토합니다."],
    )


def _analysis_scenarios(response: AnalysisResponse, doc_ids: list[str]) -> ScenarioAnalysisBundle:
    bull_ids = _flatten_ids(response.bull_evidence_ids) or doc_ids[:2]
    bear_ids = _flatten_ids(response.bear_evidence_ids) or doc_ids[:2]
    base_ids = doc_ids[:3]
    summary = _first([response.summary, response.conclusion], "현재 근거 기준의 중립 시나리오입니다.")
    return ScenarioAnalysisBundle(
        base_case=ScenarioCase(
            probability=0.50,
            thesis=summary,
            drivers=[_first(response.bull_points, "기존 추세와 확인된 근거가 유지됩니다.")],
            risks=[_first(response.bear_points, "핵심 리스크가 현실화될 수 있습니다.")],
            evidence_doc_ids=base_ids,
        ),
        bull_case=ScenarioCase(
            probability=0.25,
            thesis=_first(response.bull_points, "상방 촉매가 확인되면 우호적 시나리오가 강화됩니다."),
            drivers=[x for x in response.bull_points[:3] if _clean(x)],
            risks=[_first(response.bear_points, "밸류에이션 또는 이벤트 리스크")],
            evidence_doc_ids=bull_ids[:4],
        ),
        bear_case=ScenarioCase(
            probability=0.25,
            thesis=_first(response.bear_points, "하방 리스크가 확인되면 방어적 판단이 필요합니다."),
            drivers=[x for x in response.bear_points[:3] if _clean(x)],
            risks=[_first(response.open_questions, "추가 근거 부족")],
            evidence_doc_ids=bear_ids[:4],
        ),
    )


def _analysis_monitoring(response: AnalysisResponse) -> MonitoringPlan:
    metrics = [metric.name for metric in response.key_metrics[:5] if _clean(metric.name)]
    next_events = (
        list(response.catalyst_timeline.near_term[:3])
        + list(response.catalyst_timeline.mid_term[:2])
        + list(response.open_questions[:2])
    )
    risks = response.bear_points[:3] or ["근거 품질, 가격 추세, 이벤트 리스크를 계속 확인합니다."]
    return MonitoringPlan(
        next_events=[_clean(x) for x in next_events if _clean(x)][:6],
        key_indicators=metrics or ["가격 추세", "거래량", "실적/가이던스", "금리/유동성"],
        alert_conditions=[_clean(x) for x in risks if _clean(x)][:5],
        review_cadence="weekly or after major earnings/macro events",
    )


def _risk_management(response: Any) -> RiskManagement:
    if isinstance(response, AnalysisResponse):
        risks = [_clean(x) for x in response.bear_points if _clean(x)][:5]
        invalidating = [_clean(x) for x in response.open_questions if _clean(x)][:3]
    else:
        risks = [_clean(getattr(x, "text", "")) for x in getattr(response, "key_risks", []) if _clean(getattr(x, "text", ""))][:5]
        invalidating = [_clean(getattr(x, "risk_control", "")) for x in getattr(response, "execution_strategy", []) if _clean(getattr(x, "risk_control", ""))][:3]
    if not risks:
        risks = ["근거 부족으로 리스크를 낮게 평가하지 말고 추가 확인이 필요합니다."]
    risk_level = "high" if len(risks) >= 4 else "medium" if len(risks) >= 2 else "unknown"
    return RiskManagement(
        main_risks=risks,
        invalidating_conditions=invalidating or risks[:2],
        position_sizing_comment="근거 품질과 변동성에 맞춰 포지션 크기를 보수적으로 조정해야 합니다.",
        risk_level=risk_level,
    )


def enrich_research_response(
    response: AnalysisResponse | TopicResponse,
    *,
    retrieval_plan: RetrievalPlan | dict[str, Any] | None = None,
) -> AnalysisResponse | TopicResponse:
    """Add decision-grade diagnostics without changing existing public fields."""

    meta = _ensure_meta(response)
    plan_dict = plan_to_dict(retrieval_plan) if retrieval_plan else meta.extras.get("retrieval_plan", {})
    if plan_dict:
        meta.extras["retrieval_plan"] = plan_dict

    evidence_quality = score_evidence_items(
        getattr(response, "raw_context", []) or [],
        ticker=getattr(response, "ticker", getattr(response, "theme", "")),
        question=getattr(response, "question", ""),
    )
    response.evidence_quality = evidence_quality

    validated_metrics, numeric_summary, numeric_warnings = validate_key_metrics(getattr(response, "key_metrics", []) or [])
    response.key_metrics = validated_metrics

    eq_avg = average_evidence_quality(evidence_quality)
    fresh_cov = freshness_coverage(evidence_quality)
    diversity = source_diversity(evidence_quality)
    bucket_cov = _required_bucket_coverage(response, retrieval_plan or plan_dict)
    q_metrics = _quality_metrics(
        response,
        numeric_rate=float(numeric_summary["numeric_grounding_rate"]),
        evidence_quality_average=eq_avg,
        freshness=fresh_cov,
        diversity=diversity,
        required_bucket_coverage=bucket_cov,
    )
    response.quality_metrics = q_metrics

    low_quality_only = bool(evidence_quality) and all(item.overall_score < 0.60 for item in evidence_quality.values())
    official_support = any(item.source_type in {"sec_filing", "fred", "provider_data", "earnings_transcript"} for item in evidence_quality.values())
    raw_confidence = getattr(response, "confidence", None)
    if raw_confidence is None:
        raw_confidence = 0.65 if getattr(response, "status", "") == "success" else 0.45
    confidence = apply_confidence_caps(
        float(raw_confidence or 0.0),
        evidence_count=len(evidence_quality),
        low_quality_only=low_quality_only,
        numeric_grounding_rate=q_metrics.numeric_grounding_rate,
        claim_support_rate=q_metrics.claim_support_rate,
        stale_context_rate=q_metrics.stale_context_rate,
        required_bucket_coverage=q_metrics.required_bucket_coverage,
        official_support=official_support,
        evidence_quality_average=q_metrics.evidence_quality_average,
        freshness_coverage=q_metrics.freshness_coverage,
    )
    response.confidence_rationale = confidence
    if isinstance(response, AnalysisResponse):
        response.confidence = confidence.final_confidence
        response.decision_view = _analysis_decision(response, confidence.final_confidence)
        response.scenario_analysis = _analysis_scenarios(response, _context_doc_ids(response))
        response.monitoring_plan = _analysis_monitoring(response)
    else:
        response.decision_view = _topic_decision(response, confidence.final_confidence)
        if not response.monitoring_plan.key_indicators:
            response.monitoring_plan = MonitoringPlan(
                next_events=[_clean(x.strategy) for x in response.execution_strategy[:3] if _clean(x.strategy)],
                key_indicators=[metric.name for metric in response.key_metrics[:5] if _clean(metric.name)] or ["가격 추세", "금리", "유동성", "뉴스 촉매"],
                alert_conditions=[_clean(x.text) for x in response.key_risks[:4] if _clean(x.text)],
                review_cadence="weekly or after major macro/market events",
            )
    response.risk_management = _risk_management(response)

    warnings = list(getattr(response, "warnings", []) or [])
    warnings.extend(numeric_warnings)
    if not evidence_quality:
        warnings.append("No current-run evidence was available; confidence is capped.")
    if q_metrics.required_bucket_coverage and q_metrics.required_bucket_coverage < 0.50:
        warnings.append("Required evidence bucket coverage is below 50%.")
    response.warnings = list(dict.fromkeys(warnings))

    meta.extras["numeric_grounding_warnings"] = list(dict.fromkeys(numeric_warnings))
    meta.extras["numeric_grounding_summary"] = numeric_summary
    meta.extras["quality_metrics"] = q_metrics.model_dump(mode="json")
    meta.extras["evidence_quality_average"] = q_metrics.evidence_quality_average
    meta.extras["confidence_caps"] = list(confidence.caps_applied)
    meta.extras["confidence_rationale"] = calibration_to_extras(confidence)
    return response
