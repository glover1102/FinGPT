from __future__ import annotations

import math
from typing import Iterable


def _clean(values: Iterable[float | int | None]) -> list[float]:
    out: list[float] = []
    for value in values:
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(val):
            out.append(val)
    return out


def simple_returns(prices: Iterable[float | int | None]) -> list[float]:
    values = _clean(prices)
    returns: list[float] = []
    for idx in range(1, len(values)):
        prev = values[idx - 1]
        if prev == 0:
            continue
        returns.append(values[idx] / prev - 1.0)
    return returns


def momentum_return(prices: Iterable[float | int | None], lookback: int = 21) -> float | None:
    values = _clean(prices)
    if len(values) <= lookback:
        return None
    previous = values[-lookback - 1]
    if previous == 0:
        return None
    return values[-1] / previous - 1.0


def realized_volatility(prices: Iterable[float | int | None], lookback: int = 20, annualization: int = 252) -> float | None:
    returns = simple_returns(_clean(prices)[-(lookback + 1):])
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((ret - mean) ** 2 for ret in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(annualization)


def drawdown_series(prices: Iterable[float | int | None]) -> list[float]:
    values = _clean(prices)
    peak: float | None = None
    out: list[float] = []
    for value in values:
        peak = value if peak is None else max(peak, value)
        out.append(value / peak - 1.0 if peak else 0.0)
    return out


def correlation_matrix(returns_by_asset: dict[str, Iterable[float | int | None]]) -> dict[str, dict[str, float]]:
    cleaned = {asset: _clean(values) for asset, values in returns_by_asset.items()}
    assets = list(cleaned)
    matrix: dict[str, dict[str, float]] = {asset: {} for asset in assets}
    for left in assets:
        for right in assets:
            matrix[left][right] = _correlation(cleaned[left], cleaned[right])
    return matrix


def rate_sensitivity(asset_returns: Iterable[float | int | None], rate_changes: Iterable[float | int | None]) -> float | None:
    returns = _clean(asset_returns)
    rates = _clean(rate_changes)
    n = min(len(returns), len(rates))
    if n < 3:
        return None
    x = rates[-n:]
    y = returns[-n:]
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    var_x = sum((value - mean_x) ** 2 for value in x)
    if var_x == 0:
        return None
    cov = sum((xv - mean_x) * (yv - mean_y) for xv, yv in zip(x, y))
    return cov / var_x


def _correlation(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n < 2:
        return 0.0
    a = left[-n:]
    b = right[-n:]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    var_a = sum((value - mean_a) ** 2 for value in a)
    var_b = sum((value - mean_b) ** 2 for value in b)
    if var_a == 0 or var_b == 0:
        return 0.0
    cov = sum((av - mean_a) * (bv - mean_b) for av, bv in zip(a, b))
    return cov / math.sqrt(var_a * var_b)
