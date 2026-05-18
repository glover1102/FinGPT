import asyncio
from types import SimpleNamespace

from core.schemas.request import AnalysisRequest
from core.schemas.response import AnalysisResponse, ExecutionMeta
from pipelines.orchestration import research_pipeline


def _request():
    return AnalysisRequest(ticker="MSFT", question="What matters next?", sources=["news"])


def _response():
    return AnalysisResponse(
        ticker="MSFT",
        question="What matters next?",
        status="success",
        summary="Evidence is mixed.",
        bull_points=["Cloud demand is resilient."],
        bear_points=["Valuation remains demanding."],
        sentiment="Mixed",
        confidence=0.55,
        conclusion="Use a decision framework.",
        execution_meta=ExecutionMeta(),
    )


def _settings(enabled: bool):
    return SimpleNamespace(
        output_language="en",
        scenario_simulation_enabled=enabled,
        scenario_simulation_fail_open=True,
        scenario_simulation_llm_enabled=False,
        scenario_simulation_min_personas=5,
        scenario_simulation_max_personas=6,
        scenario_simulation_max_scenarios=4,
        scenario_simulation_strict_evidence=True,
    )


def test_finalize_skips_simulation_when_flag_disabled(monkeypatch):
    async def explode(*args, **kwargs):
        raise AssertionError("simulation should not run")

    monkeypatch.setattr(research_pipeline, "load_settings", lambda: _settings(False))
    monkeypatch.setattr(research_pipeline, "build_report", lambda *args, **kwargs: ("md", "html"))
    monkeypatch.setattr(research_pipeline, "save_outputs", lambda *args, **kwargs: None)

    import pipelines.simulate.simulation_pipeline as simulation_pipeline

    monkeypatch.setattr(simulation_pipeline, "run_scenario_simulation", explode)
    response = asyncio.run(
        research_pipeline._finalize_response(
            _request(),
            _response(),
            start_time=0.0,
            stages_ran=["collect", "retrieve", "infer", "analyze"],
        )
    )
    assert "scenario_simulation" not in response.execution_meta.extras


def test_finalize_attaches_simulation_before_report(monkeypatch):
    captured = {}

    def fake_report(request, response, language="en"):
        captured["simulation"] = response.execution_meta.extras.get("scenario_simulation")
        return "md", "html"

    monkeypatch.setattr(research_pipeline, "load_settings", lambda: _settings(True))
    monkeypatch.setattr(research_pipeline, "build_report", fake_report)
    monkeypatch.setattr(research_pipeline, "save_outputs", lambda *args, **kwargs: None)

    response = asyncio.run(
        research_pipeline._finalize_response(
            _request(),
            _response(),
            start_time=0.0,
            stages_ran=["collect", "retrieve", "infer", "analyze"],
        )
    )
    simulation = response.execution_meta.extras["scenario_simulation"]
    assert captured["simulation"] == simulation
    assert simulation["status"] in {"success", "partial"}
    assert len(simulation["scenarios"]) == 4


def test_request_override_enables_simulation_when_env_disabled(monkeypatch):
    monkeypatch.setattr(research_pipeline, "load_settings", lambda: _settings(False))
    monkeypatch.setattr(research_pipeline, "build_report", lambda *args, **kwargs: ("md", "html"))
    monkeypatch.setattr(research_pipeline, "save_outputs", lambda *args, **kwargs: None)
    request = _request().model_copy(update={"scenario_simulation_enabled": True})
    response = asyncio.run(
        research_pipeline._finalize_response(
            request,
            _response(),
            start_time=0.0,
            stages_ran=["collect", "retrieve", "infer", "analyze"],
        )
    )
    assert "scenario_simulation" in response.execution_meta.extras


def test_request_override_disables_simulation_when_env_enabled(monkeypatch):
    monkeypatch.setattr(research_pipeline, "load_settings", lambda: _settings(True))
    monkeypatch.setattr(research_pipeline, "build_report", lambda *args, **kwargs: ("md", "html"))
    monkeypatch.setattr(research_pipeline, "save_outputs", lambda *args, **kwargs: None)
    request = _request().model_copy(update={"scenario_simulation_enabled": False})
    response = asyncio.run(
        research_pipeline._finalize_response(
            request,
            _response(),
            start_time=0.0,
            stages_ran=["collect", "retrieve", "infer", "analyze"],
        )
    )
    assert "scenario_simulation" not in response.execution_meta.extras
