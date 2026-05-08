from __future__ import annotations

from core.schemas.macro import AssetImpact, MacroRegime, MacroSignal


ASSET_CLASSES = [
    "US Equities",
    "Growth Stocks",
    "Value Stocks",
    "Defensive Stocks",
    "Long Bonds",
    "Short Bonds",
    "Credit",
    "USD",
    "Gold",
    "Oil",
    "Cash",
]


_MAP: dict[str, dict[str, tuple[str, str, list[str], list[str]]]] = {
    "goldilocks": {
        "US Equities": ("positive", "Growth is firm and inflation is cooling.", ["Inflation reacceleration", "policy stays restrictive"], ["GDPC1", "CPIAUCSL", "DGS10"]),
        "Growth Stocks": ("positive", "Lower inflation pressure can support longer-duration equity cash flows.", ["Real yields rise"], ["DFII10", "T10YIE"]),
        "Value Stocks": ("neutral", "Cyclical support exists but relative edge may be less clear.", ["Growth slows"], ["INDPRO", "RSAFS"]),
        "Defensive Stocks": ("neutral", "Defensives may lag in a risk-on regime.", ["Risk-off shock"], ["VIXCLS"]),
        "Long Bonds": ("positive", "Cooling inflation can support duration if growth is not overheating.", ["Term premium rises"], ["DGS10", "T10Y2Y"]),
        "Short Bonds": ("neutral", "Front-end yields depend on the policy path.", ["Policy repricing"], ["FEDFUNDS", "DGS2"]),
        "Credit": ("positive", "Benign growth can support credit spreads.", ["Late-cycle leverage"], ["BAMLH0A0HYM2"]),
        "USD": ("mixed", "Risk-on conditions can soften safe-haven demand, but rate differentials matter.", ["Policy divergence"], ["DGS2"]),
        "Gold": ("mixed", "Lower inflation helps real yields but risk appetite may reduce hedge demand.", ["Real-yield spike"], ["DFII10", "T10YIE"]),
        "Oil": ("neutral", "Growth support is offset if inflation pressure cools.", ["Supply shock"], ["PPIACO"]),
        "Cash": ("negative", "Cash becomes less compelling if risk appetite improves.", ["High front-end yields persist"], ["FEDFUNDS"]),
    },
    "disinflation": {
        "US Equities": ("mixed", "Lower inflation helps multiples but growth is slowing.", ["Earnings downgrades"], ["CPIAUCSL", "GDPC1"]),
        "Growth Stocks": ("mixed", "Duration can benefit from lower yields, but growth risk remains.", ["Earnings risk"], ["DGS10", "INDPRO"]),
        "Value Stocks": ("neutral", "Cyclicals may face slower demand.", ["Demand slowdown"], ["RSAFS"]),
        "Defensive Stocks": ("positive", "Defensives can help if disinflation comes with slower growth.", ["Risk-on reversal"], ["UNRATE", "VIXCLS"]),
        "Long Bonds": ("positive", "Disinflation is generally supportive for duration.", ["Fiscal/term-premium shock"], ["DGS10", "T10Y3M"]),
        "Short Bonds": ("neutral", "Front-end depends on policy-cut timing.", ["Sticky core inflation"], ["FEDFUNDS", "CPILFESL"]),
        "Credit": ("mixed", "Lower rates help, but slowing growth can widen spreads.", ["Credit stress"], ["BAMLH0A0HYM2"]),
        "USD": ("mixed", "Lower rates can weigh on USD, but risk-off can support it.", ["Global stress"], ["DGS2", "VIXCLS"]),
        "Gold": ("positive", "Lower real yields and risk hedging can support gold.", ["USD strength"], ["DFII10", "T10YIE"]),
        "Oil": ("negative", "Slower growth can weigh on demand.", ["Supply disruption"], ["INDPRO"]),
        "Cash": ("neutral", "Cash yield remains useful until policy easing is clear.", ["Reinvestment risk"], ["FEDFUNDS"]),
    },
    "recession_risk": {
        "US Equities": ("negative", "Weak growth and credit/labor stress pressure earnings and risk appetite.", ["Policy response", "inflation shock"], ["GDPC1", "UNRATE", "BAMLH0A0HYM2"]),
        "Growth Stocks": ("mixed", "Lower yields may help, but earnings and liquidity risk are material.", ["Credit event"], ["DGS10", "VIXCLS"]),
        "Value Stocks": ("negative", "Cyclical value is vulnerable to demand contraction.", ["Commodity shock"], ["INDPRO", "RSAFS"]),
        "Defensive Stocks": ("positive", "Relative defensive exposure can be favored in risk-off conditions.", ["Valuation crowding"], ["VIXCLS"]),
        "Long Bonds": ("positive", "Duration can benefit if inflation is contained and growth weakens.", ["Sticky inflation"], ["DGS10", "CPIAUCSL"]),
        "Short Bonds": ("positive", "Short bonds can preserve capital with less duration volatility.", ["Rapid policy cuts lower income"], ["FEDFUNDS"]),
        "Credit": ("negative", "Credit spreads typically face pressure in recession risk.", ["Liquidity support"], ["BAMLH0A0HYM2", "BAMLC0A0CM"]),
        "USD": ("positive", "Safe-haven demand can support USD.", ["Policy easing narrows rate advantage"], ["VIXCLS", "DGS2"]),
        "Gold": ("positive", "Risk-off and lower real yields can support gold.", ["USD surge", "real yields rise"], ["DFII10", "VIXCLS"]),
        "Oil": ("negative", "Demand risk usually weighs on oil.", ["Supply shock"], ["INDPRO"]),
        "Cash": ("positive", "Liquidity has option value during macro stress.", ["Reinvestment risk"], ["FEDFUNDS"]),
    },
    "stagflation": {
        "US Equities": ("negative", "Weak growth with sticky inflation pressures margins and valuations.", ["Supply relief"], ["CPIAUCSL", "GDPC1"]),
        "Growth Stocks": ("negative", "High real/nominal rates can pressure long-duration equities.", ["Rapid disinflation"], ["DFII10", "DGS10"]),
        "Value Stocks": ("mixed", "Commodity-linked value may help but broad cyclicals face growth risk.", ["Demand destruction"], ["PPIACO", "INDPRO"]),
        "Defensive Stocks": ("mixed", "Defensives can help relative to cyclicals but inflation can pressure costs.", ["Margin pressure"], ["CPIAUCSL"]),
        "Long Bonds": ("mixed", "Growth risk helps duration, sticky inflation hurts it.", ["Inflation expectations rise"], ["T10YIE", "DGS10"]),
        "Short Bonds": ("neutral", "Front-end yield may stay high while policy is constrained.", ["Policy error"], ["FEDFUNDS"]),
        "Credit": ("negative", "Credit faces both growth and rate pressure.", ["Nominal revenue support"], ["BAMLH0A0HYM2"]),
        "USD": ("mixed", "Restrictive policy can support USD, but fiscal/inflation risks matter.", ["Policy credibility shock"], ["DGS2"]),
        "Gold": ("positive", "Inflation uncertainty and real-asset demand can support gold.", ["Real-yield surge"], ["T10YIE", "DFII10"]),
        "Oil": ("positive", "Supply-driven inflation can support oil.", ["Demand destruction"], ["PPIACO"]),
        "Cash": ("positive", "Cash yield and optionality are useful when risk premia are unstable.", ["Inflation erodes real return"], ["FEDFUNDS"]),
    },
}


def get_asset_impacts(regime: MacroRegime, signals: list[MacroSignal] | None = None) -> list[AssetImpact]:
    mapping = _MAP.get(regime.name)
    confidence = max(0.05, min(1.0, regime.confidence))
    if not mapping:
        return [
            AssetImpact(
                asset_class=asset,
                impact="unknown",
                confidence=round(confidence * 0.5, 3),
                reason="Insufficient macro data for a defensible asset-impact view.",
                key_risks=["Missing or stale macro inputs"],
                related_indicators=[],
            )
            for asset in ASSET_CLASSES
        ]
    return [
        AssetImpact(
            asset_class=asset,
            impact=mapping.get(asset, ("unknown", "No rule defined.", [], []))[0],
            confidence=round(confidence, 3),
            reason=mapping.get(asset, ("unknown", "No rule defined.", [], []))[1],
            key_risks=mapping.get(asset, ("unknown", "", [], []))[2],
            related_indicators=mapping.get(asset, ("unknown", "", [], []))[3],
        )
        for asset in ASSET_CLASSES
    ]
