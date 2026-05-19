from __future__ import annotations

from typing import Any

from core.schemas.simulation import AgentPersona
from pipelines.simulate.fallback import asset_label


def _ticker(evidence_payload: dict[str, Any]) -> str:
    return str(evidence_payload.get("ticker_or_topic") or "").upper()


def persona_templates(evidence_payload: dict[str, Any]) -> list[dict[str, Any]]:
    ticker = _ticker(evidence_payload)
    label = asset_label(evidence_payload)
    if any(term in ticker for term in ("TLT", "IEF", "AGG", "HYG", "BOND", "TREASURY", "RATE")):
        raw = [
            ("rates_trader", "Rates Trader", "Macro hedge fund rates trader", "short_term", "medium", "bearish", ["rates", "policy", "positioning"], "Support scenarios only when rate and curve evidence confirm the path."),
            ("duration_allocator", "Duration Allocator", "Long-duration bond allocator", "long_term", "low", "bullish", ["yield", "duration", "income"], "Prefer evidence that improves duration-adjusted risk/reward."),
            ("risk_parity_manager", "Risk Parity Manager", "Risk parity portfolio manager", "medium_term", "medium", "mixed", ["volatility", "correlation", "drawdown"], "Reduce conviction when correlation or volatility risk rises."),
            ("inflation_hawk", "Inflation Hawk", "Inflation hawk", "medium_term", "low", "bearish", ["inflation", "real yields", "policy"], "Oppose bullish cases unless inflation evidence softens."),
            ("fed_watcher", "Fed Watcher", "Fed policy watcher", "medium_term", "medium", "mixed", ["Fed", "labor", "inflation"], "Change stance when policy reaction evidence changes."),
            ("income_investor", "Income Investor", "Retail income investor", "long_term", "low", "neutral", ["income", "yield", "risk"], "Favor scenarios with stable income and clear downside guardrails."),
        ]
    elif any(term in ticker for term in ("NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "META")):
        raw = [
            ("growth_pm", "Growth PM", "Growth long-only portfolio manager", "long_term", "medium", "bullish", ["growth", "catalysts", "competitive position"], "Support upside only when growth evidence remains durable."),
            ("valuation_skeptic", "Valuation Skeptic", "Valuation skeptic", "medium_term", "low", "bearish", ["valuation", "margins", "expectations"], "Require valuation support before accepting bullish scenarios."),
            ("momentum_trader", "Momentum Trader", "Options/momentum trader", "short_term", "high", "bullish", ["momentum", "catalysts", "positioning"], "Follow catalysts while invalidating quickly on failed follow-through."),
            ("sector_analyst", "Sector Analyst", "Sector analyst", "medium_term", "medium", "mixed", ["sector", "fundamentals", "competition"], "Balance company evidence against sector-level risk."),
            ("retail_participant", "Retail Participant", "Retail momentum investor", "short_term", "high", "bullish", ["headlines", "sentiment", "narrative"], "React to visible catalysts but reduce conviction when evidence is thin."),
            ("risk_manager", "Risk Manager", "Risk manager", "medium_term", "low", "bearish", ["drawdown", "liquidity", "concentration"], "Prioritize invalidation and exposure control over upside narratives."),
        ]
    elif any(term in ticker for term in ("BTC", "ETH", "CRYPTO")):
        raw = [
            ("liquidity_trader", "Liquidity Trader", "Macro liquidity trader", "short_term", "high", "mixed", ["liquidity", "rates", "risk appetite"], "Support scenarios that align with liquidity evidence."),
            ("risk_on_trader", "Risk-On Trader", "Risk-on speculative trader", "short_term", "high", "bullish", ["momentum", "flows", "sentiment"], "Stay constructive only while risk appetite persists."),
            ("regulatory_analyst", "Regulatory Analyst", "Regulatory risk analyst", "medium_term", "low", "bearish", ["regulation", "policy", "custody"], "Raise risk when policy evidence worsens."),
            ("onchain_analyst", "On-Chain Analyst", "On-chain analyst", "medium_term", "medium", "mixed", ["network activity", "flows", "holder behavior"], "Require measurable activity confirmation."),
            ("crypto_allocator", "Crypto Allocator", "Long-term crypto allocator", "long_term", "medium", "bullish", ["adoption", "scarcity", "cycle"], "Prefer durable adoption evidence over short-term noise."),
            ("risk_manager", "Risk Manager", "Risk manager", "medium_term", "low", "bearish", ["volatility", "liquidity", "tail risk"], "Cap exposure when volatility or liquidity evidence deteriorates."),
        ]
    elif any(term in ticker for term in ("EURUSD", "USDJPY", "=X", "FX")):
        raw = [
            ("carry_trader", "Carry Trader", "Carry trader", "short_term", "medium", "mixed", ["carry", "rate differential", "volatility"], "Support carry only when volatility is controlled."),
            ("central_bank_watcher", "Central Bank Watcher", "Central bank watcher", "medium_term", "medium", "mixed", ["policy", "inflation", "growth"], "Follow policy divergence evidence."),
            ("macro_fund_manager", "Macro Fund Manager", "Macro fund manager", "medium_term", "medium", "mixed", ["macro", "flows", "positioning"], "Balance valuation, policy, and positioning evidence."),
            ("corporate_hedger", "Corporate Hedger", "Corporate hedger", "medium_term", "low", "neutral", ["cash flows", "hedging cost", "risk"], "Prefer risk-reduction scenarios over directional conviction."),
            ("technical_fx_trader", "Technical FX Trader", "Technical FX trader", "short_term", "high", "mixed", ["trend", "levels", "momentum"], "React only to confirmed trend and momentum evidence."),
            ("risk_manager", "Risk Manager", "Risk manager", "medium_term", "low", "bearish", ["tail risk", "liquidity", "policy shock"], "Reduce risk when event uncertainty rises."),
        ]
    else:
        raw = [
            ("macro_strategist", "Macro Strategist", "Macro strategist", "medium_term", "medium", "mixed", ["macro", "rates", "liquidity"], "Anchor views to macro evidence and policy sensitivity."),
            ("sector_analyst", "Sector Analyst", "Sector analyst", "medium_term", "medium", "mixed", ["fundamentals", "industry", "competition"], "Require sector and company evidence to agree."),
            ("long_only_investor", "Long-Only Investor", "Long-only investor", "long_term", "medium", "bullish", ["quality", "growth", "cash flow"], "Support constructive cases only with durable evidence."),
            ("skeptical_risk_manager", "Skeptical Risk Manager", "Skeptical risk manager", "medium_term", "low", "bearish", ["risks", "liquidity", "invalidation"], "Prioritize capital preservation and invalidation signals."),
            ("event_trader", "Event Trader", "Event-driven trader", "short_term", "high", "mixed", ["catalysts", "timing", "positioning"], "Act only around concrete catalysts and timing evidence."),
            ("retail_participant", "Retail Participant", "Retail participant", "short_term", "high", "bullish", ["headlines", "sentiment", "narrative"], "Follow visible evidence but reduce conviction when warnings rise."),
        ]
    return [
        {
            "id": persona_id,
            "name": name,
            "role": role,
            "horizon": horizon,
            "risk_preference": risk,
            "bias": bias,
            "evidence_focus": [*focus, label],
            "decision_rule": rule,
        }
        for persona_id, name, role, horizon, risk, bias, focus, rule in raw
    ]


async def build_personas(
    evidence_payload: dict,
    settings=None,
) -> list[AgentPersona]:
    templates = persona_templates(evidence_payload)
    min_count = int(getattr(settings, "scenario_simulation_min_personas", 5) or 5)
    max_count = int(getattr(settings, "scenario_simulation_max_personas", 6) or 6)
    min_count = max(5, min(8, min_count))
    max_count = max(min_count, min(8, max_count))
    count = max(min_count, min(max_count, 6, len(templates)))
    return [AgentPersona(**template) for template in templates[:count]]
