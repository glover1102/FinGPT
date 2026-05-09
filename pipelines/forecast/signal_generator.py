from __future__ import annotations

from typing import Any

from core.schemas.forecast import DataQualityResult, ForecastResult, LeakageCheckResult, SignalConfig, SignalResult


def generate_signal(
    forecast: ForecastResult,
    config: SignalConfig,
    *,
    leakage_check: LeakageCheckResult | None = None,
    data_quality: DataQualityResult | None = None,
    context: dict[str, Any] | None = None,
) -> SignalResult:
    data_quality = data_quality or forecast.data_quality
    expected = forecast.expected_return
    probability_up = forecast.probability_up
    probability_down = forecast.probability_down
    confidence = forecast.model_confidence.score
    volatility = forecast.forecast_volatility
    filters: dict[str, Any] = {}
    warnings: list[str] = []
    reason_codes: list[str] = []

    if leakage_check and leakage_check.status == "fail":
        return _unavailable(forecast, "leakage_check_failed", config)
    if data_quality.status == "unavailable":
        return _unavailable(forecast, "data_quality_unavailable", config)
    if expected is None:
        return _unavailable(forecast, "forecast_unavailable", config)

    filters["confidence"] = confidence >= config.confidence_threshold
    filters["data_quality"] = data_quality.status in {"ok", "partial", "stale"}
    if not filters["confidence"]:
        warnings.append("confidence_below_threshold")
    if not filters["data_quality"]:
        warnings.append("data_quality_not_decision_grade")

    signal = "neutral"
    if (
        expected >= config.strong_bullish_threshold
        and (probability_up or 0.0) >= max(0.60, config.probability_threshold)
        and confidence >= max(0.70, config.confidence_threshold)
    ):
        signal = "strong_bullish"
    elif expected >= config.bullish_threshold and (probability_up or 0.0) >= config.probability_threshold and confidence >= config.confidence_threshold:
        signal = "moderate_bullish"
    elif (
        expected <= config.strong_bearish_threshold
        and (probability_down or 0.0) >= max(0.60, config.probability_threshold)
        and confidence >= max(0.70, config.confidence_threshold)
    ):
        signal = "strong_bearish"
    elif expected <= config.bearish_threshold and (probability_down or 0.0) >= config.probability_threshold and confidence >= config.confidence_threshold:
        signal = "moderate_bearish"

    if not filters["confidence"] and signal != "unavailable":
        signal = "neutral"
        reason_codes.append("confidence_filter_reduced_signal")

    filters["volatility"] = True
    max_vol = config.volatility_max if config.volatility_max is not None else config.max_forecast_volatility
    if config.volatility_filter_enabled and volatility is not None and volatility > max_vol:
        filters["volatility"] = False
        warnings.append("forecast_volatility_above_threshold")
        if signal.startswith("strong"):
            signal = signal.replace("strong", "moderate")
            reason_codes.append("volatility_filter_capped_strong_signal")

    if config.trend_filter_enabled:
        trend_ok = bool((context or {}).get("trend_ok", True))
        filters["trend"] = trend_ok
        if not trend_ok and signal == "strong_bullish":
            signal = "moderate_bullish"
            reason_codes.append("trend_filter_capped_bullish_signal")

    if config.regime_filter_enabled and (context or {}).get("macro_conflict"):
        filters["regime"] = False
        warnings.append("macro_regime_conflict")
        reason_codes.append("macro_context_warning_no_signal_flip")
    elif config.regime_filter_enabled:
        filters["regime"] = True

    filters["smoothing_window"] = int(config.smoothing_window or 1)
    filters["cooldown_period"] = int(config.cooldown_period or 0)

    score = _score(expected, probability_up, confidence)
    position = _position(signal, config)
    reason_codes.extend(_base_reason_codes(signal, expected, probability_up, confidence))
    return SignalResult(
        ticker=forecast.ticker,
        as_of=forecast.as_of,
        horizon=forecast.horizon,
        raw_forecast=forecast.model_dump(mode="json"),
        signal=signal,  # type: ignore[arg-type]
        signal_score=round(score, 6),
        confidence=confidence,
        position_target=round(position, 6),
        filters_applied=list(filters.keys()),
        filter_results=filters,
        reason_codes=reason_codes,
        advisory_only=True,
        warnings=warnings,
    )


def signal_to_position(signal: str, config: SignalConfig) -> float:
    return _position(signal, config)


def _unavailable(forecast: ForecastResult, reason: str, config: SignalConfig) -> SignalResult:
    return SignalResult(
        ticker=forecast.ticker,
        as_of=forecast.as_of,
        horizon=forecast.horizon,
        raw_forecast=forecast.model_dump(mode="json"),
        signal="unavailable",
        signal_score=0.0,
        confidence=forecast.model_confidence.score,
        position_target=0.0,
        filters_applied=["availability"],
        filter_results={"availability": False},
        reason_codes=[reason],
        advisory_only=True,
        warnings=[reason],
    )


def _position(signal: str, config: SignalConfig) -> float:
    max_size = float(config.max_position_size)
    if signal == "strong_bullish":
        return max_size
    if signal == "moderate_bullish":
        return 0.5 * max_size
    if signal in {"moderate_bearish", "strong_bearish"} and config.allow_short and not config.long_only:
        return -0.5 * max_size if signal == "moderate_bearish" else -max_size
    return 0.0


def _score(expected: float, probability_up: float | None, confidence: float) -> float:
    return max(-1.0, min(1.0, expected * 10.0 + ((probability_up or 0.5) - 0.5) + confidence * 0.25))


def _base_reason_codes(signal: str, expected: float, probability_up: float | None, confidence: float) -> list[str]:
    return [
        f"expected_return:{expected:.4f}",
        f"probability_up:{(probability_up if probability_up is not None else 0.0):.4f}",
        f"confidence:{confidence:.4f}",
        f"signal:{signal}",
        "advisory_only_no_order_execution",
    ]
