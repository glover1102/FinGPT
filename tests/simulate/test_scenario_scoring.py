from core.schemas.simulation import AgentPersona, AgentView, RiskTrigger, ScenarioCase
from pipelines.simulate.scenario_scoring import score_simulation


def _scenario(scenario_type, probability, confidence=0.6):
    direction = "bullish" if scenario_type == "bull" else "bearish" if scenario_type in {"bear", "tail"} else "neutral"
    return ScenarioCase(
        id=f"{scenario_type}_case" if scenario_type != "tail" else "tail_risk_case",
        name=scenario_type.title(),
        type=scenario_type,
        probability=probability,
        direction=direction,
        time_horizon="medium_term",
        assumptions=["assumption"],
        triggers=["trigger"],
        invalidation_signals=["invalidate"],
        expected_reaction="reaction",
        evidence_doc_ids=["doc-1"],
        confidence=confidence,
    )


def _personas():
    return [
        AgentPersona(id="a", name="A", role="Risk manager", horizon="medium", risk_preference="low", bias="bearish", decision_rule="risk"),
        AgentPersona(id="b", name="B", role="Growth PM", horizon="long", risk_preference="medium", bias="bullish", decision_rule="growth"),
    ]


def test_scores_are_bounded_and_weak_evidence_scores_lower():
    scenarios = [_scenario("base", 0.45), _scenario("bull", 0.25), _scenario("bear", 0.25), _scenario("tail", 0.05)]
    views = [
        AgentView(agent_id="a", scenario_id="bear_case", stance="support", confidence=0.7, thesis="risk"),
        AgentView(agent_id="b", scenario_id="bull_case", stance="support", confidence=0.7, thesis="growth"),
    ]
    strong_payload = {
        "documents": [{"doc_id": "doc-1", "source": "news", "date": "2026-05-01"}],
        "key_metrics": [{"name": "metric", "as_of": "2026-05-01"}],
    }
    weak_payload = {"documents": [], "key_metrics": []}
    strong = score_simulation(scenarios, _personas(), views, [], strong_payload)
    weak = score_simulation(scenarios, _personas(), views, [], weak_payload)
    for value in strong.model_dump(mode="json").values():
        assert 0.0 <= value <= 1.0
    assert weak.evidence_strength < strong.evidence_strength


def test_disagreement_and_bear_tail_risk_are_reflected():
    scenarios = [_scenario("base", 0.1), _scenario("bull", 0.1), _scenario("bear", 0.55, 0.8), _scenario("tail", 0.25, 0.8)]
    views = [
        AgentView(agent_id="a", scenario_id="bear_case", stance="support", confidence=0.8, thesis="risk"),
        AgentView(agent_id="b", scenario_id="bear_case", stance="oppose", confidence=0.8, thesis="risk"),
        AgentView(agent_id="c", scenario_id="bull_case", stance="mixed", confidence=0.8, thesis="mixed"),
    ]
    triggers = [
        RiskTrigger(category="macro", trigger="risk", direction="bearish", monitoring_data="metric", response="review")
        for _ in range(6)
    ]
    scores = score_simulation(scenarios, _personas(), views, triggers, {"documents": [], "key_metrics": []})
    assert scores.disagreement_score > 0.5
    assert scores.risk_score > 0.35
