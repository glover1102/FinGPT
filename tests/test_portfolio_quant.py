from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.server import app
from core.schemas.portfolio import PortfolioPosition, PortfolioRiskRequest
from pipelines.analyze.portfolio_quant import analyze_portfolio_risk


def test_portfolio_risk_computes_concentration_and_exposure() -> None:
    response = analyze_portfolio_risk(
        PortfolioRiskRequest(
            positions=[
                PortfolioPosition(ticker="MSFT", weight=0.40),
                PortfolioPosition(ticker="TLT", weight=0.30),
                PortfolioPosition(ticker="GLD", weight=0.20),
                PortfolioPosition(ticker="BTC-USD", weight=0.10),
            ]
        )
    )

    assert response.status == "success"
    assert response.total_weight == 1.0
    assert response.concentration_level == "high"
    assert response.factor_exposures["equity"] == 0.4
    assert response.factor_exposures["rates_bonds"] == 0.3
    assert any(position.ticker == "TLT" and position.duration_proxy for position in response.positions)


def test_portfolio_risk_rate_shock_uses_duration_proxy() -> None:
    response = analyze_portfolio_risk(
        PortfolioRiskRequest(
            positions=[
                PortfolioPosition(ticker="TLT", weight=0.50),
                PortfolioPosition(ticker="SPY", weight=0.50),
            ]
        )
    )

    rate_row = next(row for row in response.stress_table if row.scenario == "rates_up_100bp")
    assert rate_row.portfolio_impact_pct < -9.0
    assert rate_row.position_impacts["TLT"] < -8.0
    assert rate_row.largest_loss_ticker == "TLT"


def test_portfolio_risk_unknown_assets_are_actionable_partial() -> None:
    response = analyze_portfolio_risk(
        PortfolioRiskRequest(
            positions=[
                PortfolioPosition(ticker="PRIVATE", weight=0.50, asset_class="private_credit"),
                PortfolioPosition(ticker="SPY", weight=0.50),
            ]
        )
    )

    assert response.status == "partial"
    assert response.warnings
    assert "private_credit" in response.warnings[0]


def test_portfolio_risk_api_endpoint() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/research/portfolio/risk",
        json={
            "positions": [
                {"ticker": "SPY", "weight": 0.6},
                {"ticker": "TLT", "weight": 0.4},
            ]
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "success"
    assert payload["factor_exposures"]["equity"] == 0.6
    assert payload["stress_table"]
