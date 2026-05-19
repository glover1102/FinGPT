from __future__ import annotations

from typing import Any

from pipelines.forecast.common import finite_float, now_iso


PROMOTION_POLICY_VERSION = "forecast_model_promotion_policy_v1"


def evaluate_promotion_policy(
    *,
    registry_item: dict[str, Any],
    experiment_payload: dict[str, Any] | None,
    artifact_integrity: dict[str, Any],
    drift_result: dict[str, Any],
) -> dict[str, Any]:
    payload = experiment_payload or {}
    hard_failures: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}
    thresholds = {
        "minimum_confidence": 0.25,
        "recommended_confidence": 0.55,
        "maximum_turnover": 25.0,
        "recommended_maximum_turnover": 10.0,
        "minimum_oos_folds": 1,
        "recommended_minimum_oos_folds": 2,
    }

    checks["registry_item_present"] = bool(registry_item)
    if not registry_item:
        hard_failures.append("registry_item_missing")

    checks["experiment_payload_present"] = bool(payload)
    if not payload:
        hard_failures.append("experiment_payload_missing")

    checks["artifact_integrity"] = artifact_integrity.get("status") == "success"
    if artifact_integrity.get("status") != "success":
        hard_failures.append("artifact_integrity_failed")

    leakage_status = str((payload.get("leakage_check") or {}).get("status") or "").lower()
    checks["leakage_status"] = leakage_status or "unknown"
    if leakage_status == "fail":
        hard_failures.append("leakage_check_failed")
    elif leakage_status != "pass":
        warnings.append(f"leakage_check_not_pass:{leakage_status or 'unknown'}")

    data_quality = (payload.get("forecast_result") or {}).get("data_quality") or (payload.get("experiment") or {}).get("data_quality") or {}
    data_quality_status = str(data_quality.get("status") or "").lower()
    checks["data_quality_status"] = data_quality_status or "unknown"
    if data_quality_status in {"unavailable", "insufficient"}:
        hard_failures.append(f"data_quality_{data_quality_status}")
    elif data_quality_status not in {"ok", "partial", "stale"}:
        warnings.append(f"data_quality_unknown:{data_quality_status or 'unknown'}")

    confidence = finite_float(((payload.get("forecast_result") or {}).get("model_confidence") or {}).get("score"))
    checks["confidence"] = confidence
    if confidence is None:
        warnings.append("model_confidence_missing")
    elif confidence < thresholds["minimum_confidence"]:
        hard_failures.append("model_confidence_below_minimum")
    elif confidence < thresholds["recommended_confidence"]:
        warnings.append("model_confidence_below_recommended")

    stability = (payload.get("model_evaluation") or {}).get("stability_metrics") or (payload.get("training_result") or {}).get("stability_metrics") or {}
    fold_count = int(finite_float(stability.get("fold_count"), 0.0) or 0)
    if not fold_count:
        fold_count = len((payload.get("training_result") or {}).get("folds") or [])
    checks["oos_fold_count"] = fold_count
    if fold_count < thresholds["minimum_oos_folds"]:
        hard_failures.append("insufficient_oos_folds")
    elif fold_count < thresholds["recommended_minimum_oos_folds"]:
        warnings.append("oos_fold_count_below_recommended")

    signal_quality = payload.get("signal_quality") or (payload.get("experiment") or {}).get("signal_metrics") or registry_item.get("signal_metrics") or {}
    turnover = finite_float(signal_quality.get("turnover"))
    checks["turnover"] = turnover
    if turnover is not None and turnover > thresholds["maximum_turnover"]:
        hard_failures.append("turnover_above_maximum")
    elif turnover is not None and turnover > thresholds["recommended_maximum_turnover"]:
        warnings.append("turnover_above_recommended")

    drift_status = str(drift_result.get("drift_status") or drift_result.get("status") or "").lower()
    checks["drift_status"] = drift_status or "unknown"
    if drift_status == "fail":
        hard_failures.append("drift_check_failed")
    elif drift_status in {"warning", "partial", "insufficient_oos_history"}:
        warnings.append(f"drift_check_not_clean:{drift_status}")
    elif drift_result.get("status") == "failed":
        hard_failures.append("drift_check_unavailable")

    eligible = not hard_failures
    return {
        "status": "pass" if eligible and not warnings else "warning" if eligible else "fail",
        "eligible": eligible,
        "policy_version": PROMOTION_POLICY_VERSION,
        "thresholds": thresholds,
        "checks": checks,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "evaluated_at": now_iso(),
    }
