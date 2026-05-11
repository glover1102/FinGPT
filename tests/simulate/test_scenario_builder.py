import asyncio

from pipelines.simulate.scenario_builder import build_scenarios


def _payload():
    return {
        "ticker_or_topic": "TLT",
        "summary": "Duration risk remains tied to rates and inflation evidence.",
        "bull_points": ["Long-end yields stabilize"],
        "bear_points": ["Real yields rise"],
        "bull_evidence_ids": ["doc-1"],
        "bear_evidence_ids": ["doc-2"],
        "key_metrics": [{"name": "10Y yield", "value": "4.2%", "as_of": "2026-05-01"}],
        "documents": [
            {"doc_id": "doc-1", "source": "macro", "date": "2026-05-01", "title": "Rates", "snippet": "rates"},
            {"doc_id": "doc-2", "source": "macro", "date": "2026-05-02", "title": "Inflation", "snippet": "inflation"},
        ],
        "uncertainty": "Policy path remains uncertain.",
    }


def test_scenario_builder_returns_four_normalized_stable_cases():
    scenarios = asyncio.run(build_scenarios(_payload()))
    assert len(scenarios) == 4
    assert {scenario.type for scenario in scenarios} == {"base", "bull", "bear", "tail"}
    assert [scenario.id for scenario in scenarios] == ["base_case", "bull_case", "bear_case", "tail_risk_case"]
    assert round(sum(scenario.probability for scenario in scenarios), 6) == 1.0
    for scenario in scenarios:
        assert scenario.assumptions
        assert scenario.triggers
        assert scenario.invalidation_signals
        assert scenario.expected_reaction
        assert 0.0 <= scenario.confidence <= 1.0
