from __future__ import annotations

from typing import Any

from pipelines.forecast.common import finite_float, mean


def build_forecast_context(
    forecast: dict[str, Any],
    feature_payload: dict[str, Any],
    macro_context: dict[str, Any],
    macro_regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    macro = evaluate_macro_alignment(forecast, macro_context)
    return {
        "macro_conflict": bool(macro.get("macro_conflict")),
        "macro_alignment": macro,
        "macro_regime": macro_regime or {},
        "trend_ok": trend_filter_state(feature_payload),
        "macro_context": macro_context,
    }


def trend_filter_state(feature_payload: dict[str, Any]) -> bool:
    rows = [row for row in feature_payload.get("rows") or [] if row.get("features")]
    if not rows:
        return True
    features = rows[-1].get("features") or {}
    value = features.get("price_above_ma200")
    if value is None:
        return True
    return bool(float(value) > 0)


def evaluate_macro_alignment(forecast: dict[str, Any], macro_context: dict[str, Any]) -> dict[str, Any]:
    if macro_context.get("status") != "success":
        return {"status": "unavailable", "macro_conflict": False, "reason": macro_context.get("reason", "macro_context_unavailable")}
    context = macro_context.get("context") or {}
    regime = context.get("regime") or {}
    risk_level = str(regime.get("risk_level") or "unknown").lower()
    regime_name = str(regime.get("name") or "unknown").lower()
    signals = {str(item.get("name") or ""): str(item.get("value") or "unknown") for item in context.get("signals") or []}
    expected = finite_float(forecast.get("expected_return"), 0.0) or 0.0
    probability_up = finite_float(forecast.get("probability_up"), 0.5) or 0.5
    probability_down = finite_float(forecast.get("probability_down"), 1.0 - probability_up) or (1.0 - probability_up)
    bullish = expected > 0 or probability_up >= 0.55
    bearish = expected < 0 or probability_down >= 0.55
    conflict_reasons: list[str] = []
    if bullish and (risk_level in {"high", "elevated"} or regime_name in {"recession_risk", "stagflation"}):
        conflict_reasons.append(f"bullish_forecast_vs_macro_{regime_name}_{risk_level}")
    if bullish and signals.get("credit_signal") == "stress":
        conflict_reasons.append("bullish_forecast_vs_credit_stress")
    if bullish and signals.get("policy_signal") == "restrictive" and signals.get("inflation_signal") in {"rising", "reaccelerating", "sticky"}:
        conflict_reasons.append("bullish_forecast_vs_restrictive_policy_inflation")
    if bearish and regime_name in {"goldilocks", "recovery"} and risk_level in {"low", "moderate"}:
        conflict_reasons.append(f"bearish_forecast_vs_constructive_macro_{regime_name}")
    return {
        "status": "success",
        "macro_conflict": bool(conflict_reasons),
        "regime": regime_name,
        "risk_level": risk_level,
        "signals": signals,
        "reasons": conflict_reasons,
        "policy": "macro_filter_warns_only_no_signal_flip",
    }


def drift_check_from_payload(payload: dict[str, Any], *, recent_window: int = 63) -> dict[str, Any]:
    training = payload.get("training_result") or {}
    oos = [row for row in training.get("oos_predictions") or [] if row.get("actual_forward_return") is not None]
    if len(oos) < max(40, recent_window):
        return {
            "status": "partial",
            "drift_status": "insufficient_oos_history",
            "recent_window": recent_window,
            "oos_count": len(oos),
            "warnings": ["insufficient_oos_history_for_drift_check"],
        }
    recent = oos[-recent_window:]
    historical = oos[: -recent_window] or oos
    recent_acc = _directional_accuracy(recent)
    historical_acc = _directional_accuracy(historical)
    recent_abs_error = _mae(recent)
    historical_abs_error = _mae(historical)
    accuracy_drop = historical_acc - recent_acc
    error_increase = recent_abs_error - historical_abs_error
    warnings: list[str] = []
    drift_status = "pass"
    if accuracy_drop > 0.12:
        warnings.append("recent_directional_accuracy_degraded")
        drift_status = "warning"
    if historical_abs_error and error_increase / historical_abs_error > 0.35:
        warnings.append("recent_prediction_error_increased")
        drift_status = "warning"
    if accuracy_drop > 0.25 or (historical_abs_error and error_increase / historical_abs_error > 0.75):
        drift_status = "fail"
    return {
        "status": "success",
        "drift_status": drift_status,
        "recent_window": recent_window,
        "oos_count": len(oos),
        "metrics": {
            "historical_directional_accuracy": round(historical_acc, 6),
            "recent_directional_accuracy": round(recent_acc, 6),
            "accuracy_drop": round(accuracy_drop, 6),
            "historical_mae": round(historical_abs_error, 8),
            "recent_mae": round(recent_abs_error, 8),
            "mae_increase": round(error_increase, 8),
        },
        "warnings": warnings,
    }


def model_comparison_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        experiment = payload.get("experiment") or {}
        forecast = payload.get("forecast_result") or {}
        evaluation = payload.get("model_evaluation") or {}
        signal_quality = payload.get("signal_quality") or {}
        backtest = payload.get("backtest_result") or {}
        confidence = forecast.get("model_confidence") or {}
        rows.append(
            {
                "experiment_id": experiment.get("experiment_id") or forecast.get("experiment_id"),
                "model_id": forecast.get("model_id"),
                "ticker": forecast.get("ticker"),
                "target": forecast.get("prediction_type"),
                "horizon": forecast.get("horizon"),
                "confidence": confidence.get("score"),
                "confidence_level": confidence.get("level"),
                "validation": evaluation.get("regression_metrics") or evaluation.get("classification_metrics") or {},
                "signal_quality": {
                    "hit_rate": signal_quality.get("hit_rate"),
                    "turnover": signal_quality.get("turnover"),
                    "signal_count": signal_quality.get("signal_count"),
                },
                "backtest": {
                    "total_return": (backtest.get("metrics") or {}).get("total_return"),
                    "sharpe": (backtest.get("metrics") or {}).get("sharpe"),
                    "max_drawdown": (backtest.get("metrics") or {}).get("max_drawdown"),
                },
                "created_at": experiment.get("created_at") or payload.get("generated_at"),
            }
        )
    return sorted(rows, key=lambda item: (finite_float(item.get("confidence"), 0.0) or 0.0), reverse=True)


def _directional_accuracy(rows: list[dict[str, Any]]) -> float:
    pairs = [
        (finite_float(row.get("predicted_return")), finite_float(row.get("actual_forward_return")))
        for row in rows
    ]
    clean = [(pred, actual) for pred, actual in pairs if pred is not None and actual is not None]
    if not clean:
        return 0.0
    return sum(1 for pred, actual in clean if (pred > 0) == (actual > 0)) / len(clean)


def _mae(rows: list[dict[str, Any]]) -> float:
    errors = [
        abs(float(row["predicted_return"]) - float(row["actual_forward_return"]))
        for row in rows
        if row.get("predicted_return") is not None and row.get("actual_forward_return") is not None
    ]
    return float(mean(errors) or 0.0)
