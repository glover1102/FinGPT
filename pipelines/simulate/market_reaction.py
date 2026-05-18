from __future__ import annotations

from core.schemas.simulation import AgentView, ScenarioCase
from pipelines.simulate.fallback import unique_strings


def build_market_reaction_table(
    scenarios: list[ScenarioCase],
    agent_views: list[AgentView],
    evidence_payload: dict,
) -> list[dict]:
    rows: list[dict] = []
    view_map: dict[str, list[AgentView]] = {}
    for view in agent_views:
        view_map.setdefault(view.scenario_id, []).append(view)

    metric_names = [
        str(metric.get("name"))
        for metric in evidence_payload.get("key_metrics", []) or []
        if isinstance(metric, dict) and metric.get("name")
    ]
    for scenario in scenarios:
        views = view_map.get(scenario.id, [])
        supporters = [view.agent_id for view in views if view.stance == "support"]
        opponents = [view.agent_id for view in views if view.stance == "oppose"]
        if scenario.direction == "bearish":
            likely_buyers = opponents[:4] or ["risk-controlled allocators waiting for confirmation"]
            likely_sellers = supporters[:4] or ["risk reducers and hedgers"]
        elif scenario.direction == "bullish":
            likely_buyers = supporters[:4] or ["catalyst-sensitive participants"]
            likely_sellers = opponents[:4] or ["valuation and risk skeptics"]
        else:
            likely_buyers = supporters[:4] or ["balanced allocators"]
            likely_sellers = opponents[:4] or ["participants needing clearer evidence"]
        rows.append(
            {
                "scenario_id": scenario.id,
                "scenario": scenario.name,
                "probability": scenario.probability,
                "direction": scenario.direction,
                "expected_reaction": scenario.expected_reaction,
                "likely_buyers": likely_buyers,
                "likely_sellers": likely_sellers,
                "volatility_implication": _volatility_implication(scenario),
                "monitoring_indicators": unique_strings([*scenario.triggers, *metric_names], limit=5),
                "invalidation_signals": scenario.invalidation_signals[:5],
            }
        )
    return rows


def _volatility_implication(scenario: ScenarioCase) -> str:
    if scenario.type == "tail":
        return "High volatility risk if stress evidence is confirmed."
    if scenario.type == "bear":
        return "Elevated volatility as downside evidence becomes more important."
    if scenario.type == "bull":
        return "Volatility can remain two-sided while catalysts are tested."
    return "Balanced volatility unless triggers break the current evidence mix."
