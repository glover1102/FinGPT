from __future__ import annotations

from typing import Any

from core.schemas.forecast import BacktestConfig, SignalConfig
from pipelines.backtest.metrics import performance_metrics
from pipelines.factors.core import drawdown_series
from pipelines.forecast.signal_generator import signal_to_position


def run_forecast_backtest(
    price_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    oos_predictions: list[dict[str, Any]],
    *,
    signal_config: SignalConfig,
    backtest_config: BacktestConfig,
) -> dict[str, Any]:
    if int(backtest_config.execution_delay_bars or 0) < 1:
        return {"status": "failed", "errors": ["execution_delay_bars_must_be_at_least_1"]}
    prices = {str(row.get("date") or ""): float(row.get("price")) for row in price_rows if row.get("price") is not None}
    benchmark_prices = {str(row.get("date") or ""): float(row.get("price")) for row in benchmark_rows if row.get("price") is not None}
    predictions = sorted(oos_predictions, key=lambda item: str(item.get("date") or ""))
    dates = [str(item.get("date") or "") for item in predictions if str(item.get("date") or "") in prices]
    if len(dates) < 2:
        return {"status": "partial", "errors": ["insufficient_oos_predictions_for_backtest"], "equity_curve": [], "metrics": performance_metrics([])}
    cost_rate = (backtest_config.commission_bps + backtest_config.slippage_bps + backtest_config.spread_bps) / 10000.0
    signal_by_date: dict[str, str] = {}
    signal_history: list[dict[str, Any]] = []
    raw_returns: list[float] = []
    last_signal = "neutral"
    last_change_idx = -10_000
    for idx, item in enumerate(predictions):
        date = str(item.get("date") or "")
        pred = float(item.get("predicted_return") or 0.0)
        raw_returns.append(pred)
        smoothed_pred = _smoothed_prediction(raw_returns, signal_config.smoothing_window)
        confidence = min(0.85, max(0.35, abs(smoothed_pred) * 10 + 0.45))
        signal = _forecast_signal(smoothed_pred, confidence, signal_config)
        cooldown_active = False
        if signal != last_signal and idx - last_change_idx <= int(signal_config.cooldown_period or 0):
            signal = last_signal
            cooldown_active = True
        elif signal != last_signal:
            last_change_idx = idx
            last_signal = signal
        signal_by_date[date] = signal
        signal_history.append(
            {
                "date": date,
                "signal": signal,
                "predicted_return": round(pred, 8),
                "smoothed_predicted_return": round(smoothed_pred, 8),
                "actual_forward_return": item.get("actual_forward_return"),
                "fold_id": item.get("fold_id"),
                "smoothing_window": int(signal_config.smoothing_window or 1),
                "cooldown_active": cooldown_active,
            }
        )

    equity = [float(backtest_config.initial_capital)]
    benchmark_curve = [float(backtest_config.initial_capital)]
    position_history = [{"date": dates[0], "position": 0.0}]
    trades: list[dict[str, Any]] = []
    prev_position = 0.0
    delay = int(backtest_config.execution_delay_bars)
    for idx in range(1, len(dates)):
        date = dates[idx]
        prev_date = dates[idx - 1]
        signal_idx = max(0, idx - delay)
        signal_date = dates[signal_idx]
        signal = signal_by_date.get(signal_date, "neutral")
        position = signal_to_position(signal, signal_config)
        turnover = abs(position - prev_position)
        asset_return = prices[date] / prices[prev_date] - 1.0 if prices.get(prev_date) else 0.0
        cost = turnover * cost_rate
        if turnover > 0:
            trades.append(
                {
                    "signal_date": signal_date,
                    "execution_date": date,
                    "ticker": price_rows[-1].get("ticker") if price_rows else "",
                    "previous_position": round(prev_position, 6),
                    "target_position": round(position, 6),
                    "turnover": round(turnover, 6),
                    "price": prices[date],
                    "cost": round(equity[-1] * cost, 8),
                    "commission_bps": backtest_config.commission_bps,
                    "slippage_bps": backtest_config.slippage_bps,
                    "spread_bps": backtest_config.spread_bps,
                    "reason": "forecast_signal_change",
                }
            )
        equity.append(equity[-1] * (1.0 + position * asset_return - cost))
        prev_position = position
        position_history.append({"date": date, "position": round(position, 6)})
        if date in benchmark_prices and prev_date in benchmark_prices and benchmark_prices[prev_date]:
            bench_return = benchmark_prices[date] / benchmark_prices[prev_date] - 1.0
        else:
            bench_return = asset_return
        benchmark_curve.append(benchmark_curve[-1] * (1.0 + bench_return))

    metrics = performance_metrics(equity)
    benchmark_metrics = performance_metrics(benchmark_curve)
    total_cost = sum(float(trade.get("cost") or 0.0) for trade in trades)
    metrics.update(
        {
            "turnover": round(sum(float(trade.get("turnover") or 0.0) for trade in trades), 6),
            "transaction_cost_impact": round(total_cost / max(float(backtest_config.initial_capital), 1e-12), 8),
            "benchmark_return": benchmark_metrics.get("total_return", 0.0),
            "excess_return": round(metrics.get("total_return", 0.0) - benchmark_metrics.get("total_return", 0.0), 6),
            "trade_count": len(trades),
        }
    )
    drawdowns = drawdown_series(equity)
    benchmark_drawdowns = drawdown_series(benchmark_curve)
    return {
        "status": "success",
        "assumptions": {
            "oos_predictions_only": True,
            "execution_delay_bars": delay,
            "transaction_cost_reflected": True,
            "commission_bps": backtest_config.commission_bps,
            "slippage_bps": backtest_config.slippage_bps,
            "spread_bps": backtest_config.spread_bps,
            "benchmark": backtest_config.benchmark,
        },
        "equity_curve": [{"date": date, "equity": round(value, 8)} for date, value in zip(dates, equity)],
        "benchmark_curve": [{"date": date, "equity": round(value, 8)} for date, value in zip(dates, benchmark_curve)],
        "signal_history": signal_history,
        "position_history": position_history,
        "trades": trades,
        "metrics": metrics,
        "benchmark_metrics": benchmark_metrics,
        "cost_impact": {"total_cost": round(total_cost, 8), "cost_rate": round(cost_rate, 8)},
        "drawdown_series": [{"date": date, "drawdown": round(value, 8)} for date, value in zip(dates, drawdowns)],
        "benchmark_drawdown_series": [{"date": date, "drawdown": round(value, 8)} for date, value in zip(dates, benchmark_drawdowns)],
        "rolling_metrics": _rolling_metrics(dates, equity),
    }


def _rolling_metrics(dates: list[str], equity: list[float], window: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if len(equity) < window + 1:
        return out
    for idx in range(window, len(equity)):
        window_curve = equity[idx - window: idx + 1]
        metrics = performance_metrics(window_curve)
        out.append(
            {
                "date": dates[idx],
                "rolling_sharpe": metrics.get("sharpe", 0.0),
                "rolling_volatility": metrics.get("volatility", 0.0),
            }
        )
    return out


def _smoothed_prediction(values: list[float], window: int) -> float:
    size = max(1, int(window or 1))
    tail = values[-size:]
    return sum(tail) / len(tail) if tail else 0.0


def _forecast_signal(pred: float, confidence: float, config: SignalConfig) -> str:
    if pred >= config.strong_bullish_threshold and confidence >= 0.70:
        return "strong_bullish"
    if pred >= config.bullish_threshold and confidence >= config.confidence_threshold:
        return "moderate_bullish"
    if pred <= config.strong_bearish_threshold and confidence >= 0.70:
        return "strong_bearish"
    if pred <= config.bearish_threshold and confidence >= config.confidence_threshold:
        return "moderate_bearish"
    return "neutral"
