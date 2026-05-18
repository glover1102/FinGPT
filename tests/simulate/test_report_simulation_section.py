from core.schemas.request import AnalysisRequest
from core.schemas.response import AnalysisResponse, ExecutionMeta
from pipelines.analyze.report_builder import build_report


def _response_with_simulation(payload):
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
        execution_meta=ExecutionMeta(extras={"scenario_simulation": payload}),
    )


def test_report_renders_failed_simulation_diagnostics():
    response = _response_with_simulation(
        {
            "status": "failed",
            "diagnostics": {"errors": ["simulation unavailable"], "warnings": []},
        }
    )
    markdown, html = build_report(AnalysisRequest(ticker="MSFT", question="What matters next?"), response, language="en")
    assert "## Scenario Simulation" in markdown
    assert "simulation unavailable" in markdown
    assert "Scenario simulation was not available" in html


def test_report_renders_successful_simulation_tables():
    payload = {
        "status": "success",
        "scenarios": [
            {
                "id": "base_case",
                "name": "Base Case",
                "probability": 1.0,
                "direction": "mixed",
                "confidence": 0.5,
                "triggers": ["trigger"],
                "invalidation_signals": ["invalidate"],
            }
        ],
        "agent_views": [
            {
                "agent_id": "risk_manager",
                "scenario_id": "base_case",
                "stance": "mixed",
                "confidence": 0.5,
                "thesis": "Evidence remains mixed.",
                "change_mind_conditions": ["new evidence"],
            }
        ],
        "risk_triggers": [
            {
                "category": "valuation",
                "trigger": "valuation risk",
                "direction": "bearish",
                "monitoring_data": "metric",
                "response": "review",
            }
        ],
        "decision_implication": {
            "bias": "watchlist",
            "entry_conditions": ["confirm catalyst"],
            "invalidation_conditions": ["risk worsens"],
            "monitoring_indicators": ["metric"],
            "risk_management": ["review exposure"],
            "uncertainty": "medium",
            "disclaimer": "This is a scenario-based research aid, not personalized financial advice.",
        },
        "scores": {"evidence_strength": 0.5, "risk_score": 0.4},
        "consensus": {"overall_bias": "watchlist", "main_agreement": "mixed", "main_disagreement": "risk"},
    }
    markdown, html = build_report(AnalysisRequest(ticker="MSFT", question="What matters next?"), _response_with_simulation(payload), language="en")
    assert "| Base Case | 1.00 | mixed | 0.50 | trigger | invalidate |" in markdown
    assert "Decision Checklist" in markdown
    assert "Agent Debate Summary" in html
