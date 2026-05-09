from __future__ import annotations

from core.schemas.macro import MacroDataQuality, MacroRegime, PortfolioEtfCandidate, PortfolioPolicyHint


def _candidate(sleeve: str, bias: str, tickers: list[str], role: str, rationale: str) -> PortfolioEtfCandidate:
    return PortfolioEtfCandidate(
        sleeve=sleeve,
        bias=bias,
        tickers=tickers,
        role=role,
        rationale=rationale,
    )


def _etf_candidates(
    *,
    equity_bias: str,
    bond_bias: str,
    cash_bias: str,
    alternative_bias: str,
    duration_bias: str,
    credit_bias: str,
) -> list[PortfolioEtfCandidate]:
    candidates: list[PortfolioEtfCandidate] = []
    if equity_bias in {"upper_range", "increase"}:
        candidates.append(_candidate("equity", equity_bias, ["SPY", "QQQ", "IWM"], "risk_on_equity_core", "Broad equity ETFs for policy-approved risk budget increases."))
    elif equity_bias == "lower_range":
        candidates.append(_candidate("equity", equity_bias, ["USMV", "SPLV"], "defensive_equity_or_reduce", "Minimum-volatility equity ETFs for maintaining equity exposure with lower beta."))
    else:
        candidates.append(_candidate("equity", equity_bias, ["SPY", "VT"], "neutral_equity_core", "Broad US/global equity ETFs for neutral equity sleeves."))

    if bond_bias == "upper_range" and str(duration_bias).startswith("longer"):
        candidates.append(_candidate("bonds", bond_bias, ["BND", "IEF", "TLT"], "duration_plus_core_bonds", "Core and Treasury duration ETFs when inflation pressure is contained."))
    elif duration_bias == "shorter":
        candidates.append(_candidate("bonds", bond_bias, ["SHY", "SGOV", "BIL"], "short_duration_defense", "Short-duration Treasury ETFs to reduce rate sensitivity."))
    else:
        candidates.append(_candidate("bonds", bond_bias, ["BND", "IEF"], "core_bond_balance", "Aggregate and intermediate Treasury ETFs for balanced duration."))

    if cash_bias in {"increase", "upper_range"}:
        candidates.append(_candidate("cash", cash_bias, ["SGOV", "BIL"], "liquidity_buffer", "Treasury-bill ETFs for cash-like liquidity and drawdown control."))
    elif cash_bias == "decrease":
        candidates.append(_candidate("cash", cash_bias, ["SGOV"], "minimum_liquidity_reserve", "Keep a policy minimum liquidity sleeve even when cash bias is lower."))
    else:
        candidates.append(_candidate("cash", cash_bias, ["SGOV", "BIL"], "neutral_liquidity_reserve", "Short Treasury ETFs for operational liquidity."))

    if alternative_bias in {"upper_range", "increase"}:
        candidates.append(_candidate("alternatives", alternative_bias, ["GLD", "DBC", "TIP"], "inflation_real_asset_hedge", "Gold, commodities, and TIPS ETFs for inflation-sensitive sleeves."))
    else:
        candidates.append(_candidate("alternatives", alternative_bias, ["GLD", "TIP"], "diversifier_watchlist", "Liquid diversifier ETFs for watchlist or small policy sleeves."))

    if credit_bias in {"higher_quality", "lower_quality"}:
        candidates.append(_candidate("credit", credit_bias, ["LQD", "IGSB"], "investment_grade_credit", "Investment-grade credit ETFs; avoid reaching for lower-quality credit in stressed regimes."))
    else:
        candidates.append(_candidate("credit", credit_bias, ["LQD", "HYG"], "credit_barbell_watch", "Investment-grade and high-yield ETFs for credit-spread monitoring, not automatic orders."))
    return candidates


def get_portfolio_policy_hint(regime: MacroRegime, data_quality: MacroDataQuality) -> PortfolioPolicyHint:
    warnings = ["Advisory only; no AI Portfolio policy is changed and no trade order is created."]
    if data_quality.status != "ok":
        warnings.append(f"Macro data quality is {data_quality.status}; reduce confidence in policy hints.")
    mapping = {
        "goldilocks": ("upper_range", "neutral", "decrease", "neutral", "neutral", "neutral", "increase", False, "Risk conditions are constructive, but allocation changes still require policy and user review."),
        "reflation": ("neutral", "lower_range", "neutral", "neutral", "shorter", "neutral", "maintain", True, "Growth support is positive, but inflation and rate risk argue for review."),
        "overheating": ("neutral", "lower_range", "increase", "neutral", "shorter", "lower_quality", "reduce", True, "Strong growth with inflation pressure can raise policy and valuation risk."),
        "stagflation": ("lower_range", "lower_range", "increase", "upper_range", "shorter", "higher_quality", "reduce", True, "Weak growth with sticky inflation requires a conservative risk posture."),
        "disinflation": ("neutral", "upper_range", "neutral", "neutral", "longer", "higher_quality", "maintain", True, "Cooling inflation can support duration, while slower growth requires earnings-risk review."),
        "recession_risk": ("lower_range", "upper_range", "increase", "neutral", "longer_if_inflation_contained", "higher_quality", "reduce", True, "Weak growth, softer labor, or credit stress point toward lower risk budgets."),
        "recovery": ("neutral", "neutral", "decrease", "neutral", "neutral", "neutral", "increase", False, "Improving growth with easier policy can support selective risk taking."),
    }
    fields = mapping.get(regime.name, ("unknown", "unknown", "unknown", "unknown", "unknown", "unknown", "unknown", True, "Insufficient data for a portfolio policy hint."))
    etf_candidates = _etf_candidates(
        equity_bias=fields[0],
        bond_bias=fields[1],
        cash_bias=fields[2],
        alternative_bias=fields[3],
        duration_bias=fields[4],
        credit_bias=fields[5],
    )
    return PortfolioPolicyHint(
        regime=regime.name,
        equity_bias=fields[0],
        bond_bias=fields[1],
        cash_bias=fields[2],
        alternative_bias=fields[3],
        duration_bias=fields[4],
        credit_bias=fields[5],
        risk_level=fields[6],
        rebalance_attention=bool(fields[7]),
        explanation=str(fields[8]),
        etf_candidates=etf_candidates,
        warnings=warnings,
        data_quality=data_quality,
        advisory_only=True,
    )
