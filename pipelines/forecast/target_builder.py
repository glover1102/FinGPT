from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from core.schemas.forecast import TargetConfig


def build_target(
    price_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]] | None,
    config: TargetConfig,
) -> dict[str, Any]:
    df = _price_frame(price_rows)
    benchmark = _price_frame(benchmark_rows or [])
    if df.empty:
        return {
            "status": "empty",
            "rows": [],
            "target_name": "",
            "summary": {"complete_rows": 0, "dropped_tail_rows": config.horizon},
            "warnings": ["price_frame_empty"],
        }
    price = df["price"]
    horizon = int(config.horizon)
    forward_return = price.shift(-horizon) / price - 1.0
    target_type = str(config.target_type or "forward_return").lower()
    target_name = f"{target_type}_{horizon}d"
    if target_type == "direction":
        values = (forward_return > float(config.threshold)).astype(float)
        values[forward_return.isna()] = np.nan
    elif target_type == "volatility":
        values = _future_realized_volatility(price, horizon=horizon, window=min(config.volatility_window, horizon))
    elif target_type == "excess_return" and not benchmark.empty:
        bench = benchmark["price"].reindex(df.index).ffill()
        values = forward_return - (bench.shift(-horizon) / bench - 1.0)
    elif target_type == "quantile_return":
        values = _quantile_labels(forward_return, buckets=5)
    elif target_type in {"triple_barrier_label", "triple_barrier"}:
        target_type = "triple_barrier_label"
        target_name = f"triple_barrier_label_{horizon}d"
        values = _triple_barrier_labels(df, config, horizon=horizon, forward_return=forward_return)
    else:
        target_type = "forward_return"
        target_name = f"forward_return_{horizon}d"
        values = forward_return
    rows = []
    for date, value in values.items():
        parsed = _json_float(value)
        rows.append(
            {
                "date": str(date.date()),
                "target": parsed,
                "forward_return": _json_float(forward_return.loc[date]),
                "is_trainable": parsed is not None,
            }
        )
    complete = [row for row in rows if row["is_trainable"]]
    warnings: list[str] = []
    if len(complete) < 40:
        warnings.append("insufficient_target_history")
    if target_type == "triple_barrier_label" and not {"high", "low"}.issubset(df.columns):
        warnings.append("triple_barrier_used_close_proxy_for_missing_high_low")
    return {
        "status": "success" if complete else "empty",
        "rows": rows,
        "target_name": target_name,
        "summary": {
            "target_type": target_type,
            "horizon": horizon,
            "complete_rows": len(complete),
            "dropped_tail_rows": min(horizon, len(rows)),
            "positive_rate": _positive_rate(complete),
        },
        "warnings": warnings,
    }


def align_feature_target(feature_payload: dict[str, Any], target_payload: dict[str, Any]) -> list[dict[str, Any]]:
    target_by_date = {row["date"]: row for row in target_payload.get("rows") or []}
    aligned: list[dict[str, Any]] = []
    for feature_row in feature_payload.get("rows") or []:
        target_row = target_by_date.get(feature_row.get("date"))
        if not target_row:
            continue
        features = dict(feature_row.get("features") or {})
        if not features:
            continue
        aligned.append(
            {
                "date": str(feature_row.get("date") or ""),
                "features": features,
                "target": target_row.get("target"),
                "forward_return": target_row.get("forward_return"),
                "is_trainable": bool(target_row.get("is_trainable")) and all(value is not None for value in features.values()),
            }
        )
    return aligned


def latest_feature_row(feature_payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = [row for row in feature_payload.get("rows") or [] if row.get("features")]
    complete = [row for row in rows if all(value is not None for value in (row.get("features") or {}).values())]
    return complete[-1] if complete else (rows[-1] if rows else None)


def _price_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame["price"] = pd.to_numeric(frame.get("price"), errors="coerce")
    for column in ("high", "low", "close", "adjusted_close"):
        if column in frame:
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame = frame.dropna(subset=["date", "price"]).sort_values("date").drop_duplicates("date", keep="last")
    if "high" not in frame:
        frame["high"] = frame["price"]
    if "low" not in frame:
        frame["low"] = frame["price"]
    return frame.set_index("date")


def _future_realized_volatility(price: pd.Series, *, horizon: int, window: int) -> pd.Series:
    returns = price.pct_change()
    values: list[float | None] = []
    dates = list(price.index)
    for idx in range(len(dates)):
        future_returns = returns.iloc[idx + 1: idx + horizon + 1].dropna()
        if len(future_returns) < max(2, min(window, horizon)):
            values.append(np.nan)
        else:
            values.append(float(future_returns.tail(window).std() * np.sqrt(252)))
    return pd.Series(values, index=price.index)


def _quantile_labels(forward_return: pd.Series, *, buckets: int) -> pd.Series:
    valid = forward_return.dropna()
    labels = pd.Series(np.nan, index=forward_return.index, dtype=float)
    if valid.empty:
        return labels
    try:
        quantiles = pd.qcut(valid.rank(method="first"), q=buckets, labels=False, duplicates="drop")
    except ValueError:
        return labels
    labels.loc[quantiles.index] = quantiles.astype(float)
    return labels


def _triple_barrier_labels(
    frame: pd.DataFrame,
    config: TargetConfig,
    *,
    horizon: int,
    forward_return: pd.Series,
) -> pd.Series:
    take_profit = float(config.triple_barrier_take_profit or max(abs(config.threshold), 0.03))
    stop_loss = float(config.triple_barrier_stop_loss or take_profit)
    max_holding = int(config.triple_barrier_max_holding or horizon)
    max_holding = max(1, min(max_holding, horizon))
    labels: list[float] = []
    prices = frame["price"].tolist()
    highs = frame["high"].fillna(frame["price"]).tolist()
    lows = frame["low"].fillna(frame["price"]).tolist()
    for idx, entry in enumerate(prices):
        if idx + max_holding >= len(prices) or not np.isfinite(entry) or entry <= 0:
            labels.append(np.nan)
            continue
        outcome: float | None = None
        for step in range(1, max_holding + 1):
            up_move = highs[idx + step] / entry - 1.0
            down_move = lows[idx + step] / entry - 1.0
            if up_move >= take_profit:
                outcome = 1.0
                break
            if down_move <= -stop_loss:
                outcome = -1.0
                break
        if outcome is None:
            fwd = forward_return.iloc[idx]
            if not np.isfinite(fwd):
                labels.append(np.nan)
            elif fwd > float(config.threshold):
                labels.append(1.0)
            elif fwd < -float(config.threshold):
                labels.append(-1.0)
            else:
                labels.append(0.0)
        else:
            labels.append(outcome)
    return pd.Series(labels, index=frame.index)


def _json_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _positive_rate(rows: list[dict[str, Any]]) -> float | None:
    values = [row.get("target") for row in rows if row.get("target") is not None]
    if not values:
        return None
    return round(sum(1 for value in values if float(value) > 0) / len(values), 6)
