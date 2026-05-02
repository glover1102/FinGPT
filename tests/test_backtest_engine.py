from __future__ import annotations

from pipelines.backtest.engine import BacktestConfig, run_backtest, run_momentum_ranking_backtest


def _rows(prices: list[float], prefix: str = "2026-01") -> list[dict[str, object]]:
    return [
        {"date": f"{prefix}-{idx + 1:02d}", "adjusted_close": price, "close": price}
        for idx, price in enumerate(prices)
    ]


def test_buy_and_hold_metrics_include_cost_assumptions() -> None:
    result = run_backtest(
        _rows([100, 110, 121]),
        BacktestConfig(strategy="buy_and_hold", transaction_cost_bps=0, slippage_bps=0),
    )

    assert result["status"] == "success"
    assert result["equity_curve"][-1]["equity"] == 1.21
    assert result["assumptions"]["lookahead_policy"]
    assert result["metrics"]["max_drawdown"] == 0.0
    assert result["metrics"]["turnover"] == 1.0


def test_moving_average_signal_is_applied_one_bar_later() -> None:
    result = run_backtest(
        _rows([100, 90, 110]),
        BacktestConfig(strategy="moving_average", short_window=1, long_window=2, transaction_cost_bps=0, slippage_bps=0),
    )

    assert result["status"] == "success"
    assert result["equity_curve"][-1]["equity"] == 1.0
    assert result["trades"] == []


def test_momentum_ranking_uses_prior_history_and_records_turnover() -> None:
    result = run_momentum_ranking_backtest(
        {
            "AAA": _rows([100, 101, 103, 108, 112, 118]),
            "BBB": _rows([100, 99, 98, 98, 97, 96]),
        },
        lookback=2,
        top_n=1,
        rebalance_every=1,
        config=BacktestConfig(transaction_cost_bps=0, slippage_bps=0),
    )

    assert result["status"] == "success"
    assert result["selected_history"]
    assert result["selected_history"][0]["selected"] == ["AAA"]
    assert result["metrics"]["trade_count"] >= 1
    assert result["assumptions"]["lookahead_policy"]
