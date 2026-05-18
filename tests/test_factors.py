from __future__ import annotations

import math

from pipelines.factors.core import (
    correlation_matrix,
    drawdown_series,
    momentum_return,
    rate_sensitivity,
    realized_volatility,
    simple_returns,
)


def test_price_factors_are_deterministic_and_skip_bad_values() -> None:
    prices = [100, 110, None, "bad", 121, 108.9]

    assert all(math.isclose(left, right) for left, right in zip(simple_returns(prices), [0.1, 0.1, -0.1]))
    assert round(momentum_return(prices, lookback=2) or 0, 6) == -0.01
    assert drawdown_series([100, 120, 90, 150]) == [0.0, 0.0, -0.25, 0.0]
    assert realized_volatility([100, 101, 102, 103, 104], lookback=4) is not None


def test_correlation_matrix_and_rate_sensitivity() -> None:
    matrix = correlation_matrix(
        {
            "SPY": [0.01, 0.02, -0.01, 0.03],
            "QQQ": [0.02, 0.04, -0.02, 0.06],
            "GLD": [-0.01, 0.0, 0.01, -0.02],
        }
    )

    assert math.isclose(matrix["SPY"]["SPY"], 1.0)
    assert math.isclose(matrix["SPY"]["QQQ"], 1.0)
    assert matrix["SPY"]["GLD"] < 0
    assert rate_sensitivity([0.01, -0.02, 0.03, -0.01], [0.1, 0.2, -0.1, 0.0]) < 0
