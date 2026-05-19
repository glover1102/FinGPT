import asyncio

from pipelines.simulate.persona_builder import build_personas


def test_persona_builder_returns_distinct_tlt_personas():
    personas = asyncio.run(build_personas({"ticker_or_topic": "TLT"}))
    assert 5 <= len(personas) <= 8
    roles = [persona.role for persona in personas]
    assert len(roles) == len(set(roles))
    assert "Macro hedge fund rates trader" in roles
    for persona in personas:
        assert persona.decision_rule
        assert persona.evidence_focus
        assert persona.horizon
        assert persona.risk_preference


def test_persona_builder_returns_large_cap_equity_personas_for_nvda():
    personas = asyncio.run(build_personas({"ticker_or_topic": "NVDA"}))
    roles = {persona.role for persona in personas}
    assert "Growth long-only portfolio manager" in roles
    assert "Valuation skeptic" in roles
    assert "Options/momentum trader" in roles
