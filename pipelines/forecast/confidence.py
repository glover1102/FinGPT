from __future__ import annotations

from core.schemas.forecast import ConfidenceResult, DataQualityResult, LeakageCheckResult, SignalQuality


def calculate_model_confidence(
    *,
    aggregate_metrics: dict,
    baseline_metrics: dict,
    stability_metrics: dict,
    signal_quality: SignalQuality,
    leakage_check: LeakageCheckResult,
    data_quality: DataQualityResult,
    overfitting: dict,
) -> ConfidenceResult:
    directional = float(aggregate_metrics.get("directional_accuracy") or aggregate_metrics.get("accuracy") or 0.0)
    baseline_directional = float(baseline_metrics.get("directional_accuracy") or 0.5)
    improvement = max(0.0, min(1.0, directional - baseline_directional + 0.5))
    stability = max(0.0, min(1.0, 1.0 - float(stability_metrics.get("directional_accuracy_dispersion") or 0.0)))
    signal_component = float(signal_quality.hit_rate if signal_quality.hit_rate is not None else directional)
    data_component = {"ok": 1.0, "partial": 0.72, "stale": 0.55, "insufficient": 0.35, "unavailable": 0.0}.get(data_quality.status, 0.4)
    components = {
        "validation_performance": round(directional, 6),
        "baseline_improvement": round(improvement, 6),
        "walk_forward_stability": round(stability, 6),
        "signal_quality": round(max(0.0, min(1.0, signal_component)), 6),
        "data_quality": round(data_component, 6),
    }
    base = (
        components["validation_performance"] * 0.30
        + components["baseline_improvement"] * 0.20
        + components["walk_forward_stability"] * 0.18
        + components["signal_quality"] * 0.17
        + components["data_quality"] * 0.15
    )
    penalties: dict[str, float] = {}
    if leakage_check.status == "fail":
        penalties["leakage_fail"] = 0.65
    elif leakage_check.status == "warning":
        penalties["leakage_warning"] = 0.15
    if data_quality.status in {"insufficient", "unavailable"}:
        penalties["data_quality"] = 0.25
    if float(overfitting.get("gap") or 0.0) > 0.15:
        penalties["overfitting"] = min(0.25, float(overfitting.get("gap") or 0.0))
    if signal_quality.turnover > 5:
        penalties["turnover"] = 0.10
    score = max(0.0, min(1.0, base - sum(penalties.values())))
    level = "high" if score >= 0.80 else ("medium" if score >= 0.60 else ("low" if score >= 0.40 else "very_low"))
    return ConfidenceResult(
        score=round(score, 6),
        level=level,
        components=components,
        penalties={key: round(value, 6) for key, value in penalties.items()},
        explanation=f"Confidence is {level}; score is based on walk-forward validation, baseline comparison, signal quality, data quality, and penalties.",
    )
