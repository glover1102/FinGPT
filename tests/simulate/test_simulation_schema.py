import pytest
from pydantic import ValidationError

from core.schemas.simulation import (
    DecisionImplication,
    ScenarioCase,
    ScenarioSimulationResult,
)


def test_scenario_probability_bounds_are_enforced():
    with pytest.raises(ValidationError):
        ScenarioCase(
            id="bad",
            name="Bad",
            type="base",
            probability=1.2,
            direction="neutral",
            time_horizon="medium_term",
            assumptions=["x"],
            triggers=["x"],
            invalidation_signals=["x"],
            expected_reaction="x",
        )


def test_simulation_result_serializes_and_deserializes():
    result = ScenarioSimulationResult(status="success")
    payload = result.model_dump(mode="json")
    restored = ScenarioSimulationResult.model_validate(payload)
    assert restored.status == "success"
    assert restored.diagnostics.errors == []


def test_decision_implication_includes_required_disclaimer():
    decision = DecisionImplication(bias="watchlist", uncertainty="high")
    assert "not personalized financial advice" in decision.disclaimer
