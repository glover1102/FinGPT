from __future__ import annotations

from core.schemas.forecast import SignalConfig, SignalQuality
from pipelines.forecast.signal_generator import signal_to_position


def evaluate_signal_quality(oos_predictions: list[dict], signal_config: SignalConfig) -> SignalQuality:
    signals: list[str] = []
    returns: list[float] = []
    for item in oos_predictions:
        pred = float(item.get("predicted_return") or item.get("prediction") or 0.0)
        prob = 0.55 if pred > 0 else 0.45
        confidence = min(0.85, max(0.35, abs(pred) * 10 + 0.45))
        if pred >= signal_config.bullish_threshold and prob >= 0.55 and confidence >= signal_config.confidence_threshold:
            signal = "moderate_bullish"
        elif pred <= signal_config.bearish_threshold:
            signal = "moderate_bearish"
        else:
            signal = "neutral"
        signals.append(signal)
        returns.append(float(item.get("actual_forward_return") or 0.0))
    if not signals:
        return SignalQuality()
    bullish = [ret for sig, ret in zip(signals, returns) if "bullish" in sig]
    bearish = [ret for sig, ret in zip(signals, returns) if "bearish" in sig]
    hit_values = []
    for sig, ret in zip(signals, returns):
        if "bullish" in sig:
            hit_values.append(ret > 0)
        elif "bearish" in sig:
            hit_values.append(ret < 0)
    positions = [signal_to_position(sig, signal_config) for sig in signals]
    turnover = sum(abs(positions[idx] - positions[idx - 1]) for idx in range(1, len(positions)))
    changes = sum(1 for idx in range(1, len(signals)) if signals[idx] != signals[idx - 1])
    false_positive = sum(1 for sig, ret in zip(signals, returns) if "bullish" in sig and ret <= 0)
    return SignalQuality(
        signal_count=len(signals),
        bullish_count=len(bullish),
        bearish_count=len(bearish),
        neutral_count=sum(1 for sig in signals if sig == "neutral"),
        hit_rate=round(sum(hit_values) / len(hit_values), 6) if hit_values else None,
        average_forward_return_after_bullish=round(sum(bullish) / len(bullish), 6) if bullish else None,
        average_forward_return_after_bearish=round(sum(bearish) / len(bearish), 6) if bearish else None,
        precision_bullish=round(sum(1 for ret in bullish if ret > 0) / len(bullish), 6) if bullish else None,
        precision_bearish=round(sum(1 for ret in bearish if ret < 0) / len(bearish), 6) if bearish else None,
        false_positive_rate=round(false_positive / max(len(bullish), 1), 6) if bullish else None,
        false_negative_rate=None,
        average_holding_period=round(len(signals) / max(changes + 1, 1), 6),
        turnover=round(turnover, 6),
        signal_stability=round(1.0 - changes / max(len(signals) - 1, 1), 6),
        recent_signal_performance=round(sum(returns[-20:]) / min(len(returns), 20), 6) if returns else None,
        signal_decay_by_horizon={},
    )
