from __future__ import annotations

from typing import Any


def build_forecast_research_context(forecast_payload: dict[str, Any]) -> dict[str, Any]:
    forecast = forecast_payload.get("forecast_result") or {}
    signal = forecast_payload.get("signal_result") or {}
    evaluation = forecast_payload.get("model_evaluation") or {}
    leakage = forecast_payload.get("leakage_check") or {}
    return {
        "status": "success" if forecast else "unavailable",
        "ticker": forecast.get("ticker", ""),
        "source": "ml_forecast_lab",
        "numeric_authority": "structured_ml_output_only",
        "forecast_summary": {
            "as_of": forecast.get("as_of"),
            "horizon": forecast.get("horizon"),
            "expected_return": forecast.get("expected_return"),
            "probability_up": forecast.get("probability_up"),
            "confidence": forecast.get("model_confidence"),
        },
        "signal": {
            "value": signal.get("signal", "unavailable"),
            "score": signal.get("signal_score"),
            "advisory_only": True,
        },
        "validation": {
            "leakage_status": leakage.get("status"),
            "stability": evaluation.get("stability_metrics"),
            "oos_only": True,
        },
        "policy": {
            "do_not_invent_numbers": True,
            "no_direct_trade_orders": True,
            "portfolio_usage": "advisory_context_only",
        },
    }
