from __future__ import annotations

import math

from pipelines.portfolio.optimizer import optimize_portfolio


def test_equal_weight_optimizer_sums_to_one() -> None:
    result = optimize_portfolio({"SPY": [0.01, 0.02], "TLT": [0.0, 0.01], "GLD": [0.02, -0.01]})

    assert result["status"] == "success"
    assert math.isclose(result["sum_weights"], 1.0)
    assert set(result["weights"]) == {"SPY", "TLT", "GLD"}


def test_inverse_volatility_allocates_more_to_lower_vol_asset() -> None:
    result = optimize_portfolio(
        {
            "LOW": [0.001, 0.002, 0.001, 0.002],
            "HIGH": [0.05, -0.04, 0.03, -0.02],
        },
        method="inverse_volatility",
    )

    assert result["weights"]["LOW"] > result["weights"]["HIGH"]
    assert math.isclose(sum(result["weights"].values()), 1.0)


def test_infeasible_max_weight_is_reported_and_adjusted() -> None:
    result = optimize_portfolio(
        {"A": [0.01, 0.02], "B": [0.01, 0.02]},
        max_weight=0.4,
    )

    assert result["warnings"]
    assert result["max_weight"] == 0.5
    assert all(weight <= result["max_weight"] for weight in result["weights"].values())


def test_momentum_tilt_prefers_positive_cumulative_return() -> None:
    result = optimize_portfolio(
        {"UP": [0.01, 0.02, 0.01], "DOWN": [-0.01, -0.02, 0.0]},
        method="momentum_tilt",
        max_weight=0.8,
    )

    assert result["status"] == "success"
    assert result["weights"]["UP"] > result["weights"]["DOWN"]


def test_minimum_volatility_alias_is_supported() -> None:
    result = optimize_portfolio(
        {
            "LOW": [0.001, 0.002, 0.001, 0.002],
            "HIGH": [0.05, -0.04, 0.03, -0.02],
        },
        method="minimum_volatility",
    )

    assert result["status"] == "success"
    assert result["weights"]["LOW"] > result["weights"]["HIGH"]


def test_covariance_optimizer_reports_portfolio_metrics() -> None:
    result = optimize_portfolio(
        {
            "LOW": [0.001, 0.002, 0.001, 0.002, 0.001],
            "HIGH": [0.05, -0.04, 0.03, -0.02, 0.01],
        },
        method="minimum_volatility",
    )

    assert result["diagnostics"]["uses_covariance"] is True
    assert result["diagnostics"]["sample_count"] == 5
    assert result["portfolio_metrics"]["annualized_volatility"] >= 0
    assert math.isclose(sum(result["risk_contributions"].values()), 1.0, rel_tol=1e-5)


def test_risk_parity_uses_covariance_and_keeps_weights_normalized() -> None:
    result = optimize_portfolio(
        {
            "A": [0.01, 0.02, -0.01, 0.01, 0.0],
            "B": [0.005, 0.004, 0.006, 0.005, 0.004],
            "C": [-0.01, 0.01, 0.0, -0.005, 0.002],
        },
        method="risk_parity",
        max_weight=0.7,
    )

    assert result["diagnostics"]["uses_covariance"] is True
    assert math.isclose(sum(result["weights"].values()), 1.0)
    assert all(weight <= 0.7 for weight in result["weights"].values())
