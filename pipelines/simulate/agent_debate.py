from __future__ import annotations

from core.schemas.simulation import AgentPersona, AgentView, ScenarioCase
from pipelines.simulate.fallback import clamp


def _stance(persona: AgentPersona, scenario: ScenarioCase) -> str:
    role = f"{persona.role} {persona.bias} {persona.risk_preference}".lower()
    if scenario.type == "base":
        return "neutral" if persona.bias in {"neutral", "mixed"} else "mixed"
    if "risk" in role or "skeptic" in role or "hawk" in role:
        if scenario.type in {"bear", "tail"}:
            return "support"
        if scenario.type == "bull":
            return "oppose"
    if "bull" in persona.bias or "constructive" in persona.bias:
        return "support" if scenario.direction == "bullish" else "oppose" if scenario.direction == "bearish" else "mixed"
    if "bear" in persona.bias or "skept" in persona.bias:
        return "support" if scenario.direction == "bearish" else "oppose" if scenario.direction == "bullish" else "mixed"
    return "mixed"


def _confidence(persona: AgentPersona, scenario: ScenarioCase) -> float:
    adjustment = 0.04 if scenario.evidence_doc_ids else -0.05
    if "risk" in persona.role.lower() and scenario.type in {"bear", "tail"}:
        adjustment += 0.05
    if "trader" in persona.role.lower() and scenario.triggers:
        adjustment += 0.03
    return clamp(scenario.confidence + adjustment, default=scenario.confidence)


async def run_agent_debate(
    personas: list[AgentPersona],
    scenarios: list[ScenarioCase],
    evidence_payload: dict,
    settings=None,
) -> list[AgentView]:
    views: list[AgentView] = []
    for persona in personas:
        for scenario in scenarios:
            if scenario.type == "tail" and "risk" not in persona.role.lower() and len(personas) > 6:
                continue
            stance = _stance(persona, scenario)
            evidence_note = "Available evidence supports monitoring this case." if scenario.evidence_doc_ids else "Evidence is limited, so conviction remains constrained."
            views.append(
                AgentView(
                    agent_id=persona.id,
                    scenario_id=scenario.id,
                    stance=stance,
                    confidence=_confidence(persona, scenario),
                    thesis=f"{persona.role} is {stance} on {scenario.name}: {evidence_note}",
                    key_evidence_doc_ids=scenario.evidence_doc_ids[:3],
                    counterarguments=[
                        "The supplied evidence may be stale, incomplete, or contradicted by future data.",
                        "Scenario probabilities are decision aids, not forecasts.",
                    ],
                    change_mind_conditions=scenario.invalidation_signals[:3] or ["New evidence invalidates the scenario assumptions."],
                )
            )
    return views
