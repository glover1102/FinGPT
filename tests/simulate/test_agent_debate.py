import asyncio

from pipelines.simulate.agent_debate import run_agent_debate
from pipelines.simulate.persona_builder import build_personas
from pipelines.simulate.scenario_builder import build_scenarios


def _payload():
    return {
        "ticker_or_topic": "NVDA",
        "summary": "AI demand remains the central debate.",
        "bull_points": ["AI demand remains strong"],
        "bear_points": ["Valuation expectations are demanding"],
        "bull_evidence_ids": ["doc-bull"],
        "bear_evidence_ids": ["doc-bear"],
        "documents": [
            {"doc_id": "doc-bull", "source": "filing", "date": "2026-05-01", "title": "Bull", "snippet": "demand"},
            {"doc_id": "doc-bear", "source": "news", "date": "2026-05-02", "title": "Bear", "snippet": "valuation"},
        ],
    }


def test_agent_debate_references_known_personas_and_scenarios():
    payload = _payload()
    personas = asyncio.run(build_personas(payload))
    scenarios = asyncio.run(build_scenarios(payload))
    views = asyncio.run(run_agent_debate(personas, scenarios, payload))
    persona_ids = {persona.id for persona in personas}
    scenario_ids = {scenario.id for scenario in scenarios}
    required = {"base_case", "bull_case", "bear_case"}
    assert required <= {view.scenario_id for view in views}
    for view in views:
        assert view.agent_id in persona_ids
        assert view.scenario_id in scenario_ids
        assert 0.0 <= view.confidence <= 1.0
        assert view.thesis
        assert view.counterarguments
        assert view.change_mind_conditions
