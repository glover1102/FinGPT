import sys

from core.schemas.response import AnalysisResponse
from app.cli import main as cli_main
from app.cli.main import parse_args


def test_cli_accepts_simulate_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--ticker", "TLT", "--question", "risks?", "--simulate"])
    args = parse_args()
    assert args.simulate is True
    assert args.no_simulate is False


def test_cli_accepts_no_simulate_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--ticker", "TLT", "--question", "risks?", "--no-simulate"])
    args = parse_args()
    assert args.simulate is False
    assert args.no_simulate is True


def test_cli_simulate_flag_passes_request_override(monkeypatch):
    captured = {}

    def fake_run_pipeline(request):
        captured["override"] = request.scenario_simulation_enabled
        return AnalysisResponse(
            ticker=request.ticker,
            question=request.question,
            status="success",
            summary="ok",
            sentiment="Neutral",
            conclusion="ok",
        )

    monkeypatch.setattr(cli_main, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--ticker", "MSFT", "--question", "risks?", "--simulate"],
    )

    cli_main.main()

    assert captured["override"] is True


def test_cli_no_simulate_flag_passes_request_override(monkeypatch):
    captured = {}

    def fake_run_pipeline(request):
        captured["override"] = request.scenario_simulation_enabled
        return AnalysisResponse(
            ticker=request.ticker,
            question=request.question,
            status="success",
            summary="ok",
            sentiment="Neutral",
            conclusion="ok",
        )

    monkeypatch.setattr(cli_main, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--ticker", "MSFT", "--question", "risks?", "--no-simulate"],
    )

    cli_main.main()

    assert captured["override"] is False
