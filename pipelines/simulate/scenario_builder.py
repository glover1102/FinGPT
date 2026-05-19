from __future__ import annotations

from core.schemas.simulation import ScenarioCase
from pipelines.simulate.fallback import fallback_scenarios, normalize_probabilities


async def build_scenarios(
    evidence_payload: dict,
    settings=None,
) -> list[ScenarioCase]:
    scenarios = fallback_scenarios(evidence_payload)
    probabilities = normalize_probabilities({scenario.type: scenario.probability for scenario in scenarios})
    return [
        scenario.model_copy(update={"probability": probabilities[scenario.type]})
        for scenario in scenarios
    ]
