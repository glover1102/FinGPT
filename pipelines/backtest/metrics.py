from __future__ import annotations

import math
from typing import Iterable

from pipelines.factors.core import drawdown_series


def performance_metrics(equity_curve: Iterable[float], *, periods_per_year: int = 252) -> dict[str, float]:
    curve = [float(x) for x in equity_curve if x is not None]
    if len(curve) < 2 or curve[0] <= 0:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
        }
    returns = [curve[idx] / curve[idx - 1] - 1.0 for idx in range(1, len(curve)) if curve[idx - 1] != 0]
    total_return = curve[-1] / curve[0] - 1.0
    years = max((len(curve) - 1) / periods_per_year, 1 / periods_per_year)
    cagr = (curve[-1] / curve[0]) ** (1 / years) - 1.0
    vol = _stdev(returns) * math.sqrt(periods_per_year) if returns else 0.0
    downside = [ret for ret in returns if ret < 0]
    downside_vol = _stdev(downside) * math.sqrt(periods_per_year) if len(downside) > 1 else 0.0
    sharpe = cagr / vol if vol else 0.0
    sortino = cagr / downside_vol if downside_vol else 0.0
    max_dd = min(drawdown_series(curve), default=0.0)
    calmar = cagr / abs(max_dd) if max_dd else 0.0
    return {
        "total_return": round(total_return, 6),
        "cagr": round(cagr, 6),
        "volatility": round(vol, 6),
        "sharpe": round(sharpe, 6),
        "sortino": round(sortino, 6),
        "max_drawdown": round(max_dd, 6),
        "calmar": round(calmar, 6),
    }


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
