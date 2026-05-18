from __future__ import annotations

from typing import Any


def build_portfolio_advisory_signal(forecast_payload: dict[str, Any]) -> dict[str, Any]:
    forecast = forecast_payload.get("forecast_result") or {}
    signal = forecast_payload.get("signal_result") or {}
    quality = forecast_payload.get("signal_quality") or {}
    return {
        "status": "success" if forecast and signal else "unavailable",
        "ticker": forecast.get("ticker", ""),
        "signal": signal.get("signal", "unavailable"),
        "expected_return": forecast.get("expected_return"),
        "probability_up": forecast.get("probability_up"),
        "confidence": (forecast.get("model_confidence") or {}).get("score"),
        "signal_quality": {
            "hit_rate": quality.get("hit_rate"),
            "turnover": quality.get("turnover"),
        },
        "portfolio_usage": {
            "allowed": bool(forecast and signal and signal.get("signal") != "unavailable"),
            "usage_type": "advisory_signal",
            "suggested_action": "review_weight_context",
            "auto_rebalance": False,
        },
        "warnings": ["advisory_only_no_auto_rebalance"],
    }
