import asyncio
import json
from types import SimpleNamespace

from core.schemas.response import AnalysisResponse, ExecutionMeta, KeyMetric
from core.schemas.retrieval import RetrievalItem
from pipelines.simulate import simulation_pipeline
from pipelines.simulate.simulation_pipeline import run_scenario_simulation


def _response():
    return AnalysisResponse(
        ticker="TLT",
        question="What matters for the next quarter?",
        status="success",
        summary="Duration-sensitive bonds depend on rates and inflation evidence.",
        bull_points=["Long-end yields stabilize", "Inflation cools"],
        bear_points=["Fed stays restrictive", "Real yields rise"],
        bull_evidence_ids=[["doc-1"], ["doc-2"]],
        bear_evidence_ids=[["doc-1"], ["doc-3"]],
        key_metrics=[KeyMetric(name="10Y yield", value="4.2", unit="%", as_of="2026-05-01", evidence_doc_ids=["doc-1"])],
        sentiment="Mixed",
        confidence=0.62,
        conclusion="Use a scenario framework.",
        raw_context=[
            RetrievalItem(source="macro", title="Rates", date="2026-05-01", chunk="Fed and inflation evidence", score=0.9, metadata={"doc_id": "doc-1"})
        ],
        execution_meta=ExecutionMeta(extras={"quant_snapshot": {"duration_proxy": "long"}}),
    )


def _settings(**overrides):
    values = {
        "scenario_simulation_llm_enabled": False,
        "scenario_simulation_fail_open": True,
        "scenario_simulation_max_personas": 6,
        "scenario_simulation_min_personas": 5,
        "scenario_simulation_max_scenarios": 4,
        "scenario_simulation_strict_evidence": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_pipeline_returns_result_and_does_not_mutate_response():
    response = _response()
    before = response.model_dump(mode="json")
    result = asyncio.run(run_scenario_simulation(response, settings=_settings()))
    assert result.status == "success"
    assert len(result.scenarios) == 4
    assert 5 <= len(result.personas) <= 8
    assert result.scores is not None
    assert result.model_dump(mode="json")
    assert response.model_dump(mode="json") == before


def test_pipeline_fail_open_returns_failed_result(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("evidence unavailable")

    monkeypatch.setattr(simulation_pipeline, "build_evidence_payload", explode)
    result = asyncio.run(run_scenario_simulation(_response(), settings=_settings(scenario_simulation_fail_open=True)))
    assert result.status == "failed"
    assert "evidence unavailable" in result.diagnostics.errors[0]


def test_fallback_output_has_no_unsupported_price_target_language():
    result = asyncio.run(run_scenario_simulation(_response(), settings=_settings()))
    text = json.dumps(result.model_dump(mode="json"), ensure_ascii=False).lower()
    forbidden = ["target price", "price target", "목표가", "will reach", "guaranteed", "$123 target", "123달러 목표"]
    assert not any(term in text for term in forbidden)
