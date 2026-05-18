from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from core.schemas.portfolio import (
    PortfolioPosition,
    PortfolioPositionRisk,
    PortfolioRiskRequest,
    PortfolioRiskResponse,
    PortfolioStressRow,
)


_ASSET_CLASS_ALIASES = {
    "equity": "equity",
    "stock": "equity",
    "single_ticker": "equity",
    "equity_index": "equity",
    "index": "equity",
    "rates": "rates_bonds",
    "rates_bonds": "rates_bonds",
    "bond": "rates_bonds",
    "bond_etf": "rates_bonds",
    "credit": "credit",
    "commodity": "commodity",
    "commodity_etf": "commodity",
    "fx": "fx",
    "forex": "fx",
    "crypto": "crypto",
}

_RATES_DURATION_PROXY = {
    "TLT": 16.8,
    "IEF": 7.2,
    "SHY": 1.9,
    "AGG": 6.0,
    "BND": 6.1,
    "LQD": 8.4,
    "HYG": 3.7,
}

_KNOWN_CLASS_BY_TICKER = {
    "SPY": "equity",
    "QQQ": "equity",
    "IWM": "equity",
    "DIA": "equity",
    "TLT": "rates_bonds",
    "IEF": "rates_bonds",
    "SHY": "rates_bonds",
    "AGG": "rates_bonds",
    "BND": "rates_bonds",
    "HYG": "credit",
    "LQD": "credit",
    "JNK": "credit",
    "GLD": "commodity",
    "SLV": "commodity",
    "USO": "commodity",
    "CL=F": "commodity",
    "GC=F": "commodity",
    "DX-Y.NYB": "fx",
    "DXY": "fx",
    "EURUSD=X": "fx",
    "JPY=X": "fx",
    "BTC-USD": "crypto",
    "ETH-USD": "crypto",
}

_DEFAULT_SCENARIOS: dict[str, dict[str, float]] = {
    "equity_down_10": {
        "equity": -0.10,
        "credit": -0.04,
        "rates_bonds": 0.03,
        "commodity": -0.03,
        "fx": 0.00,
        "crypto": -0.15,
    },
    "rates_up_100bp": {
        "equity": -0.04,
        "credit": -0.03,
        "rates_bonds": -0.07,
        "commodity": -0.05,
        "fx": 0.01,
        "crypto": -0.08,
    },
    "usd_liquidity_shock": {
        "equity": -0.08,
        "credit": -0.06,
        "rates_bonds": 0.02,
        "commodity": -0.04,
        "fx": 0.02,
        "crypto": -0.20,
    },
    "risk_on_reacceleration": {
        "equity": 0.08,
        "credit": 0.03,
        "rates_bonds": -0.04,
        "commodity": 0.02,
        "fx": -0.01,
        "crypto": 0.15,
    },
}

_SCENARIO_RATIONALE = {
    "equity_down_10": "Equity-led drawdown with partial Treasury ballast and wider credit risk premium.",
    "rates_up_100bp": "Parallel rate shock; long-duration bonds and credit duration carry the main loss.",
    "usd_liquidity_shock": "Dollar liquidity tightening pressures risky assets, credit, commodities, and crypto together.",
    "risk_on_reacceleration": "Risk-on rebound benefits equities, credit, and crypto while duration sells off.",
}


def _asset_class_for_position(position: PortfolioPosition) -> tuple[str, list[str]]:
    notes: list[str] = []
    if position.asset_class:
        asset_class = _ASSET_CLASS_ALIASES.get(position.asset_class, position.asset_class)
        if asset_class not in {"equity", "rates_bonds", "credit", "commodity", "fx", "crypto"}:
            notes.append(f"Unknown explicit asset_class '{position.asset_class}', treated as equity.")
            asset_class = "equity"
        return asset_class, notes

    ticker = position.ticker.upper()
    if ticker in _KNOWN_CLASS_BY_TICKER:
        return _KNOWN_CLASS_BY_TICKER[ticker], notes
    if ticker.endswith("=X"):
        return "fx", notes
    if ticker.endswith("-USD") and ticker.split("-", 1)[0] in {"BTC", "ETH", "SOL"}:
        return "crypto", notes
    return "equity", notes


def _duration_for(ticker: str, asset_class: str) -> float | None:
    if asset_class not in {"rates_bonds", "credit"}:
        return None
    return _RATES_DURATION_PROXY.get(ticker.upper(), 7.0 if asset_class == "rates_bonds" else 4.0)


def _clean_weight(value: float) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 0.0
    return weight if isfinite(weight) else 0.0


def _scenario_shock_for(ticker: str, asset_class: str, scenario: str, shocks: dict[str, float]) -> float:
    if scenario == "rates_up_100bp":
        duration = _duration_for(ticker, asset_class)
        if duration is not None:
            return -duration * 0.01
    if ticker in shocks:
        return float(shocks[ticker])
    if asset_class in shocks:
        return float(shocks[asset_class])
    return float(shocks.get("default", 0.0))


def _direction(value: float) -> str:
    if value > 0.0025:
        return "positive"
    if value < -0.0025:
        return "negative"
    return "flat"


def analyze_portfolio_risk(request: PortfolioRiskRequest) -> PortfolioRiskResponse:
    """Compute deterministic portfolio exposure, concentration, and scenario stress.

    This engine intentionally avoids LLM inference and external I/O. It is a
    reproducible baseline for portfolio-level questions and can later accept
    provider-backed covariance inputs without changing the public response.
    """

    as_of = datetime.now(timezone.utc).date().isoformat()
    raw_weights = [_clean_weight(position.weight) for position in request.positions]
    total_weight = round(sum(raw_weights), 8)
    gross_exposure = round(sum(abs(weight) for weight in raw_weights), 8)
    net_exposure = total_weight
    denominator = gross_exposure or 1.0

    positions: list[PortfolioPositionRisk] = []
    factor_exposures: dict[str, float] = {}
    warnings: list[str] = []
    weighted_squares = 0.0
    max_position_weight = 0.0

    for position, weight in zip(request.positions, raw_weights):
        asset_class, notes = _asset_class_for_position(position)
        normalized = weight / denominator
        abs_normalized = abs(weight) / denominator
        factor_exposures[asset_class] = factor_exposures.get(asset_class, 0.0) + weight
        weighted_squares += abs_normalized**2
        max_position_weight = max(max_position_weight, abs(weight))
        duration_proxy = _duration_for(position.ticker, asset_class)
        concentration_flag = abs(weight) >= 0.25
        if notes:
            warnings.extend(f"{position.ticker}: {note}" for note in notes)
        positions.append(
            PortfolioPositionRisk(
                ticker=position.ticker,
                asset_class=asset_class,
                weight=round(weight, 8),
                normalized_weight=round(normalized, 8),
                risk_contribution_pct=round(abs_normalized * 100.0, 2),
                concentration_flag=concentration_flag,
                duration_proxy=duration_proxy,
                notes=notes,
            )
        )

    factor_exposures = {key: round(value, 8) for key, value in sorted(factor_exposures.items())}
    hhi = round(weighted_squares, 6)
    concentration_level = "high" if hhi >= 0.25 or max_position_weight >= 0.35 else "medium" if hhi >= 0.15 or max_position_weight >= 0.25 else "low"
    if abs(total_weight - 1.0) > 0.05:
        warnings.append(f"Total weight is {total_weight:.2f}; expected roughly 1.00 for a fully invested long-only portfolio.")
    if gross_exposure <= 0:
        warnings.append("Gross exposure is zero; stress table is not economically meaningful.")

    scenario_inputs = dict(_DEFAULT_SCENARIOS)
    if request.shocks:
        scenario_inputs.update(request.shocks)

    stress_table: list[PortfolioStressRow] = []
    for scenario, shocks in scenario_inputs.items():
        position_impacts: dict[str, float] = {}
        for position_risk in positions:
            shock_return = _scenario_shock_for(position_risk.ticker, position_risk.asset_class, scenario, shocks)
            position_impacts[position_risk.ticker] = round(position_risk.weight * shock_return * 100.0, 2)
        portfolio_impact = round(sum(position_impacts.values()), 2)
        largest_loss_ticker = ""
        largest_loss_pct = 0.0
        if position_impacts:
            largest_loss_ticker, largest_loss_pct = min(position_impacts.items(), key=lambda item: item[1])
        stress_table.append(
            PortfolioStressRow(
                scenario=scenario,
                portfolio_impact_pct=portfolio_impact,
                direction=_direction(portfolio_impact / 100.0),
                largest_loss_ticker=largest_loss_ticker,
                largest_loss_pct=largest_loss_pct,
                position_impacts=position_impacts,
                rationale=_SCENARIO_RATIONALE.get(scenario, "User-provided deterministic scenario override."),
            )
        )

    status = "partial" if warnings else "success"
    return PortfolioRiskResponse(
        status=status,
        as_of=as_of,
        base_currency=request.base_currency,
        total_weight=total_weight,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        hhi_concentration=hhi,
        max_position_weight=round(max_position_weight, 8),
        concentration_level=concentration_level,
        positions=positions,
        factor_exposures=factor_exposures,
        stress_table=stress_table,
        warnings=warnings,
        execution_meta={
            "engine": "deterministic_portfolio_quant_v1",
            "lookback_days": request.lookback_days,
            "scenario_count": len(stress_table),
            "uses_external_io": False,
        },
    )
