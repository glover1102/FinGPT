from __future__ import annotations

from core.schemas.macro import MacroDataQuality, MacroRegime, PortfolioPolicyHint


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
        warnings=warnings,
        data_quality=data_quality,
        advisory_only=True,
    )
