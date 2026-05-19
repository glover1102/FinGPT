from __future__ import annotations

from datetime import datetime, timezone

from core.schemas.macro import AssetImpact, MacroDataQuality, MacroScenarioRequest, MacroScenarioResponse, PortfolioEtfCandidate


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _stress_score(request: MacroScenarioRequest) -> float:
    rate_stress = _clamp(max(request.rate_shock_bp, 0.0) / 150.0)
    credit_stress = _clamp(max(request.credit_spread_shock_bp, 0.0) / 300.0)
    inflation_stress = _clamp(max(request.inflation_shock_pct, 0.0) / 2.0)
    oil_stress = _clamp(max(request.oil_shock_pct, 0.0) / 50.0)
    growth_stress = _clamp(max(-request.growth_shock_pct, 0.0) / 5.0)
    score = (
        0.25 * rate_stress
        + 0.30 * credit_stress
        + 0.15 * inflation_stress
        + 0.10 * oil_stress
        + 0.20 * growth_stress
    )
    return round(_clamp(score), 3)


def _risk_level(score: float) -> str:
    if score >= 0.65:
        return "reduce"
    if score >= 0.30:
        return "watch"
    return "neutral"


def _impact(asset_class: str, impact: str, confidence: float, reason: str, risks: list[str], indicators: list[str]) -> AssetImpact:
    return AssetImpact(
        asset_class=asset_class,
        impact=impact,
        confidence=round(confidence, 3),
        reason=reason,
        key_risks=risks,
        related_indicators=indicators,
    )


def _asset_impacts(request: MacroScenarioRequest, score: float, risk_level: str) -> list[AssetImpact]:
    confidence = 0.55 + score * 0.35
    rate_pressure = request.rate_shock_bp > 50 or request.inflation_shock_pct > 0.25
    credit_pressure = request.credit_spread_shock_bp > 75
    growth_pressure = request.growth_shock_pct < -1.0
    oil_pressure = request.oil_shock_pct > 10
    return [
        _impact(
            "US Equities",
            "negative" if risk_level == "reduce" or credit_pressure or growth_pressure else "neutral",
            confidence,
            "Higher discount rates, wider credit spreads, or weaker growth can compress equity multiples and earnings expectations.",
            ["valuation compression", "earnings revisions", "liquidity stress"],
            ["rate_shock_bp", "credit_spread_shock_bp", "growth_shock_pct"],
        ),
        _impact(
            "Long Bonds",
            "negative" if rate_pressure else "neutral",
            confidence,
            "Positive rate and inflation shocks increase duration risk for long-maturity bonds.",
            ["duration drawdown", "inflation repricing"],
            ["rate_shock_bp", "inflation_shock_pct"],
        ),
        _impact(
            "Credit",
            "negative" if credit_pressure or growth_pressure else "neutral",
            confidence,
            "Credit spread widening and weaker growth raise default and liquidity risk.",
            ["spread widening", "downgrades", "liquidity discount"],
            ["credit_spread_shock_bp", "growth_shock_pct"],
        ),
        _impact(
            "Gold",
            "positive" if oil_pressure or request.inflation_shock_pct > 0.25 else "neutral",
            confidence,
            "Inflation and commodity shocks can increase demand for real-asset hedges, while higher real rates remain a constraint.",
            ["real-rate drag", "commodity volatility"],
            ["inflation_shock_pct", "oil_shock_pct", "rate_shock_bp"],
        ),
        _impact(
            "Cash",
            "positive" if risk_level in {"watch", "reduce"} else "neutral",
            confidence,
            "Cash and T-bill sleeves can reduce drawdown sensitivity while the stress scenario is under review.",
            ["reinvestment risk", "opportunity cost"],
            ["stress_score", "risk_level"],
        ),
    ]


def _sleeve_hints(risk_level: str) -> list[PortfolioEtfCandidate]:
    if risk_level == "reduce":
        return [
            PortfolioEtfCandidate(sleeve="equity", bias="lower_range", tickers=["USMV", "SPLV"], role="defensive_equity_review", rationale="Review lower-beta equity exposure; this is not an order."),
            PortfolioEtfCandidate(sleeve="bonds", bias="shorter_duration", tickers=["SHY", "SGOV"], role="duration_risk_control", rationale="Short-duration Treasury ETFs reduce rate sensitivity in stress review."),
            PortfolioEtfCandidate(sleeve="cash", bias="increase", tickers=["SGOV", "BIL"], role="liquidity_buffer", rationale="Liquidity sleeve can buffer scenario drawdowns pending policy review."),
            PortfolioEtfCandidate(sleeve="alternatives", bias="watch", tickers=["GLD", "TIP"], role="inflation_hedge_watch", rationale="Monitor real-asset hedges when inflation or oil shocks dominate."),
        ]
    if risk_level == "watch":
        return [
            PortfolioEtfCandidate(sleeve="equity", bias="neutral_to_lower", tickers=["SPY", "USMV"], role="beta_watch", rationale="Keep broad equity exposure under review without changing policy automatically."),
            PortfolioEtfCandidate(sleeve="bonds", bias="balanced_duration", tickers=["BND", "IEF"], role="duration_watch", rationale="Review duration balance against rate and inflation shocks."),
            PortfolioEtfCandidate(sleeve="cash", bias="neutral_to_higher", tickers=["SGOV", "BIL"], role="liquidity_watch", rationale="Maintain cash-like liquidity while stress inputs are monitored."),
            PortfolioEtfCandidate(sleeve="credit", bias="higher_quality", tickers=["LQD", "IGSB"], role="credit_quality_watch", rationale="Prefer quality review if spreads are widening."),
        ]
    return [
        PortfolioEtfCandidate(sleeve="equity", bias="neutral", tickers=["SPY", "VT"], role="neutral_equity_core", rationale="Scenario stress is low; keep normal review cadence."),
        PortfolioEtfCandidate(sleeve="bonds", bias="neutral", tickers=["BND", "IEF"], role="core_bond_balance", rationale="No deterministic stress signal requires duration action."),
        PortfolioEtfCandidate(sleeve="cash", bias="neutral", tickers=["SGOV", "BIL"], role="operational_liquidity", rationale="Keep standard liquidity reserve."),
        PortfolioEtfCandidate(sleeve="alternatives", bias="watch", tickers=["GLD", "TIP"], role="diversifier_watch", rationale="Use as a monitor list only."),
    ]


def _explanation(request: MacroScenarioRequest, score: float, risk_level: str) -> str:
    drivers: list[str] = []
    if request.rate_shock_bp:
        drivers.append(f"rate shock {request.rate_shock_bp:g} bp")
    if request.credit_spread_shock_bp:
        drivers.append(f"credit spread shock {request.credit_spread_shock_bp:g} bp")
    if request.inflation_shock_pct:
        drivers.append(f"inflation shock {request.inflation_shock_pct:g} percentage points")
    if request.oil_shock_pct:
        drivers.append(f"oil shock {request.oil_shock_pct:g}%")
    if request.growth_shock_pct:
        drivers.append(f"growth shock {request.growth_shock_pct:g} percentage points")
    driver_text = ", ".join(drivers) if drivers else "no material input shocks"
    return (
        f"Deterministic advisory-only scenario maps {driver_text} to stress_score={score:.3f} "
        f"and risk_level={risk_level}. The output is for review only and does not create trades, "
        "orders, or portfolio policy changes."
    )


def run_macro_scenario(request: MacroScenarioRequest) -> MacroScenarioResponse:
    score = _stress_score(request)
    risk_level = _risk_level(score)
    return MacroScenarioResponse(
        generated_at=_now_iso(),
        advisory_only=True,
        scenario=request.model_dump(mode="json"),
        stress_score=score,
        risk_level=risk_level,
        explanation=_explanation(request, score, risk_level),
        asset_impacts=_asset_impacts(request, score, risk_level),
        sleeve_hints=_sleeve_hints(risk_level),
        data_quality=MacroDataQuality(
            status="ok",
            provider="macro_scenario",
            notes=["Deterministic scenario uses request inputs only; no live market data is fetched or mutated."],
        ),
        warnings=[
            "Advisory-only deterministic scenario; no orders, trades, execution instructions, or portfolio policy mutation are produced.",
            "Use this output as a stress-review input alongside current Macro data quality and portfolio constraints.",
        ],
    )
