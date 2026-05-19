from __future__ import annotations

from typing import Any

from core.schemas.response import ConfidenceRationale


def _clamp(value: float | int | None) -> float:
    try:
        parsed = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        parsed = 0.0
    return max(0.0, min(1.0, parsed))


def apply_confidence_caps(
    raw_confidence: float,
    *,
    evidence_count: int = 0,
    low_quality_only: bool = False,
    numeric_grounding_rate: float = 0.0,
    claim_support_rate: float = 0.0,
    stale_context_rate: float = 0.0,
    required_bucket_coverage: float = 0.0,
    official_support: bool = False,
    evidence_quality_average: float = 0.0,
    freshness_coverage: float = 0.0,
) -> ConfidenceRationale:
    final = _clamp(raw_confidence)
    caps: list[str] = []
    positives: list[str] = []
    negatives: list[str] = []

    if evidence_count <= 0:
        final = min(final, 0.20)
        caps.append("no evidence available: confidence capped at 0.20")
        negatives.append("근거 문서가 없어 투자 판단 신뢰도를 제한했습니다.")
    if low_quality_only:
        final = min(final, 0.55)
        caps.append("only low-quality news/RSS evidence: confidence capped at 0.55")
        negatives.append("근거가 저품질 뉴스/RSS 중심입니다.")
    if numeric_grounding_rate < 0.70:
        final = min(final, 0.60)
        caps.append("numeric grounding below 70%: confidence capped at 0.60")
        negatives.append("일부 정량 지표의 기준일/출처/계산 근거가 부족합니다.")
    if claim_support_rate < 0.50:
        final = min(final, 0.50)
        caps.append("claim support below 50%: confidence capped at 0.50")
        negatives.append("주요 주장 중 근거 doc_id가 부족한 항목이 많습니다.")
    if stale_context_rate > 0.30:
        final = min(final, 0.55)
        caps.append("stale context above 30%: confidence capped at 0.55")
        negatives.append("오래된 근거 비중이 높습니다.")
    if required_bucket_coverage and required_bucket_coverage < 0.50:
        final = min(final, 0.60)
        caps.append("required bucket coverage below 50%: confidence capped at 0.60")
        negatives.append("필수 근거 버킷이 충분히 채워지지 않았습니다.")

    if official_support:
        positives.append("공식/제공자/결정론적 데이터가 포함되어 있습니다.")
    if evidence_quality_average >= 0.75:
        positives.append("근거 품질 평균이 양호합니다.")
    if freshness_coverage >= 0.70:
        positives.append("최근성 기준을 충족하는 근거 비중이 높습니다.")
    if numeric_grounding_rate >= 0.85:
        positives.append("정량 지표 대부분이 기준일/출처/근거를 갖췄습니다.")

    return ConfidenceRationale(
        raw_confidence=_clamp(raw_confidence),
        final_confidence=round(final, 4),
        positive_factors=positives,
        negative_factors=negatives,
        caps_applied=caps,
        evidence_coverage=_clamp(claim_support_rate),
        numeric_grounding_rate=_clamp(numeric_grounding_rate),
        evidence_quality_average=_clamp(evidence_quality_average),
    )


def calibration_to_extras(rationale: ConfidenceRationale) -> dict[str, Any]:
    return {
        "raw_confidence": rationale.raw_confidence,
        "final_confidence": rationale.final_confidence,
        "caps_applied": list(rationale.caps_applied),
        "positive_factors": list(rationale.positive_factors),
        "negative_factors": list(rationale.negative_factors),
        "evidence_coverage": rationale.evidence_coverage,
        "numeric_grounding_rate": rationale.numeric_grounding_rate,
        "evidence_quality_average": rationale.evidence_quality_average,
    }
