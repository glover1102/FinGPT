import asyncio

from core.schemas.response import ExecutionMeta, KeyMetric
from core.schemas.retrieval import RetrievalItem
from core.schemas.topic import DecisionSection, KeyDriver, TopicResponse
from pipelines.analyze.topic_report_builder import build_topic_report
from pipelines.simulate.simulation_pipeline import run_scenario_simulation


def _topic_response():
    return TopicResponse(
        question="How do rates affect long-duration bonds?",
        theme="TLT rates risk",
        mode="sector_macro",
        status="success",
        executive_summary="Rates and inflation are the core scenario drivers.",
        core_thesis="Duration risk depends on policy and real-yield confirmation.",
        asset_overview=[DecisionSection(title="TLT", bullets=["Long-duration exposure"], conclusion="Sensitive to rates.")],
        macro_regime=[DecisionSection(title="Policy", bullets=["Fed remains restrictive"], conclusion="Bearish if restrictive policy persists.")],
        key_drivers=[KeyDriver(text="Long-end yields stabilize", direction="supporting", evidence_doc_ids=["doc-1"])],
        key_risks=[KeyDriver(text="Real yields rise", direction="opposing", evidence_doc_ids=["doc-2"])],
        key_metrics=[KeyMetric(name="10Y yield", value="4.2", unit="%", as_of="2026-05-01", evidence_doc_ids=["doc-1"])],
        raw_context=[
            RetrievalItem(source="macro", title="Rates", date="2026-05-01", chunk="Long-end yields stabilize", score=0.9, metadata={"doc_id": "doc-1"}),
            RetrievalItem(source="macro", title="Real yields", date="2026-05-02", chunk="Real yields rise", score=0.8, metadata={"doc_id": "doc-2"}),
        ],
        execution_meta=ExecutionMeta(extras={"asset_class": "rates_bonds"}),
    )


def test_topic_response_can_run_scenario_simulation_and_render_report():
    response = _topic_response()
    simulation = asyncio.run(run_scenario_simulation(response))
    response.execution_meta.extras["scenario_simulation"] = simulation.model_dump(mode="json")
    markdown, html = build_topic_report(response, language="en")
    assert simulation.status == "success"
    assert len(simulation.scenarios) == 4
    assert "Scenario Simulation" in markdown
    assert "Agent Debate Summary" in html
