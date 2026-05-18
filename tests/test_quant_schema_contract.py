from __future__ import annotations

from core.schemas.quant import (
    QuantBacktestRequest,
    QuantFeaturePreviewRequest,
    QuantSignalGenerateRequest,
)


def test_quant_feature_request_cleans_tickers_and_defaults_features() -> None:
    request = QuantFeaturePreviewRequest(tickers="spy, qqq SPY", benchmark=" spy ")

    assert request.tickers == ["SPY", "QQQ"]
    assert request.benchmark == "SPY"
    assert request.features == []


def test_quant_signal_request_keeps_research_score_explicitly_optional() -> None:
    request = QuantSignalGenerateRequest(tickers=["SPY"], template=" Research_Confirmed_Momentum ")

    assert request.template == "research_confirmed_momentum"
    assert request.use_research_score is False
    assert request.research_max_age_days == 7


def test_quant_backtest_request_preserves_no_lookahead_cost_inputs() -> None:
    request = QuantBacktestRequest(
        tickers=["spy", "tlt"],
        template="momentum_ranking",
        transaction_cost_bps=3,
        slippage_bps=1,
    )

    assert request.tickers == ["SPY", "TLT"]
    assert request.transaction_cost_bps == 3
    assert request.slippage_bps == 1
    assert request.lookback >= 2
    assert request.require_fresh_prices is False
    assert request.max_market_calendar_lag_days == 3


def test_quant_feature_request_supports_strict_freshness_policy() -> None:
    request = QuantFeaturePreviewRequest(tickers=["SPY"], require_fresh_prices=True, max_market_calendar_lag_days=1)

    assert request.require_fresh_prices is True
    assert request.max_market_calendar_lag_days == 1


def test_quant_feature_request_supports_named_freshness_profiles() -> None:
    request = QuantFeaturePreviewRequest(tickers=["SPY"], freshness_profile=" Decision_Review ")

    assert request.freshness_profile == "decision_review"
