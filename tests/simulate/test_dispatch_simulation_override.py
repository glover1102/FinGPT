import asyncio

from core.schemas.request import CompareRequest, UniversalRequest
from core.schemas.response import AnalysisResponse
from pipelines.orchestration import dispatch


def test_universal_request_propagates_simulation_override_to_single_ticker(monkeypatch):
    captured = {}

    async def fake_run_pipeline(request, event_sink=None):
        captured["override"] = request.scenario_simulation_enabled
        return AnalysisResponse(
            ticker=request.ticker,
            question=request.question,
            status="success",
            summary="ok",
            sentiment="Neutral",
            confidence=0.1,
            conclusion="ok",
        )

    monkeypatch.setattr(dispatch, "run_pipeline_async", fake_run_pipeline)
    result = asyncio.run(
        dispatch.dispatch_async(
            UniversalRequest(
                question="MSFT outlook",
                ticker="MSFT",
                mode_hint="ticker",
                scenario_simulation_enabled=True,
            )
        )
    )
    assert result.status == "success"
    assert captured["override"] is True


def test_compare_request_propagates_simulation_override_to_each_ticker(monkeypatch):
    captured = []

    async def fake_run_pipeline(request, event_sink=None):
        captured.append((request.ticker, request.scenario_simulation_enabled))
        return AnalysisResponse(
            ticker=request.ticker,
            question=request.question,
            status="success",
            summary="ok",
            sentiment="Neutral",
            confidence=0.1,
            conclusion="ok",
        )

    monkeypatch.setattr(dispatch, "run_pipeline_async", fake_run_pipeline)
    result = asyncio.run(
        dispatch._run_compare_async(
            CompareRequest(
                tickers=["MSFT", "AAPL"],
                question="Compare",
                scenario_simulation_enabled=True,
            )
        )
    )
    assert set(result.results) == {"MSFT", "AAPL"}
    assert set(captured) == {("MSFT", True), ("AAPL", True)}
