from __future__ import annotations

from collections import Counter
from typing import Any

from core.config.settings import load_settings
from core.schemas.simulation import (
    AgentPersona,
    AgentView,
    DecisionImplication,
    RiskTrigger,
    ScenarioCase,
    ScenarioScores,
    ScenarioSimulationDiagnostics,
    ScenarioSimulationResult,
)
from pipelines.simulate.agent_debate import run_agent_debate
from pipelines.simulate.evidence_utils import build_evidence_payload
from pipelines.simulate.fallback import (
    clean_text,
    confidence_for,
    fallback_agent_views,
    fallback_personas,
    fallback_scenarios,
    normalize_probabilities,
    primary_doc_ids,
    unique_strings,
)
from pipelines.simulate.market_reaction import build_market_reaction_table
from pipelines.simulate.persona_builder import build_personas
from pipelines.simulate.scenario_builder import build_scenarios
from pipelines.simulate.scenario_scoring import score_simulation


async def run_scenario_simulation(
    analysis_response,
    retrieved_documents: list | None = None,
    quant_snapshot: dict | None = None,
    settings=None,
) -> ScenarioSimulationResult:
    settings = settings or load_settings()
    diagnostics = ScenarioSimulationDiagnostics(fallback_used=True, llm_used=False)
    try:
        evidence_payload = build_evidence_payload(
            analysis_response,
            retrieved_documents=retrieved_documents,
            quant_snapshot=quant_snapshot,
        )
        diagnostics.evidence_doc_id_coverage = _evidence_doc_id_coverage(evidence_payload)
        if not evidence_payload.get("documents"):
            diagnostics.warnings.append("No retrieved documents were available; scenario confidence is capped.")
        if getattr(settings, "scenario_simulation_llm_enabled", True):
            diagnostics.warnings.append("LLM-backed simulation is reserved; deterministic fallback was used.")

        personas: list[AgentPersona]
        scenarios: list[ScenarioCase]
        agent_views: list[AgentView]
        scores: ScenarioScores | None
        status = "success"

        try:
            personas = await build_personas(evidence_payload, settings=settings)
        except Exception as exc:  # noqa: BLE001
            diagnostics.errors.append(f"persona_builder: {exc}")
            diagnostics.warnings.append("Persona builder failed; fallback personas were used.")
            personas = fallback_personas(evidence_payload, count=int(getattr(settings, "scenario_simulation_max_personas", 6) or 6))
            status = "partial"

        try:
            scenarios = await build_scenarios(evidence_payload, settings=settings)
        except Exception as exc:  # noqa: BLE001
            diagnostics.errors.append(f"scenario_builder: {exc}")
            diagnostics.warnings.append("Scenario builder failed; fallback scenarios were used.")
            scenarios = fallback_scenarios(evidence_payload)
            status = "partial"

        before_sum = sum(float(scenario.probability or 0.0) for scenario in scenarios)
        diagnostics.scenario_probability_sum_before_normalization = round(before_sum, 6)
        scenarios = _normalize_scenario_probabilities(scenarios)
        diagnostics.scenario_probability_sum_after_normalization = round(sum(s.probability for s in scenarios), 6)
        if len(scenarios) != 4:
            diagnostics.warnings.append("Scenario builder did not return four cases; fallback scenarios were used.")
            scenarios = _normalize_scenario_probabilities(fallback_scenarios(evidence_payload))
            status = "partial"

        try:
            agent_views = await run_agent_debate(personas, scenarios, evidence_payload, settings=settings)
        except Exception as exc:  # noqa: BLE001
            diagnostics.errors.append(f"agent_debate: {exc}")
            diagnostics.warnings.append("Agent debate failed; fallback agent views were used.")
            agent_views = fallback_agent_views(personas, scenarios)
            status = "partial"

        market_reaction_table = build_market_reaction_table(scenarios, agent_views, evidence_payload)
        risk_triggers = _build_risk_triggers(scenarios, evidence_payload)

        try:
            scores = score_simulation(scenarios, personas, agent_views, risk_triggers, evidence_payload)
        except Exception as exc:  # noqa: BLE001
            diagnostics.errors.append(f"scenario_scoring: {exc}")
            diagnostics.warnings.append("Scenario scoring failed.")
            scores = None
            status = "partial"

        consensus = _build_consensus(scenarios, agent_views, scores)
        disagreement_map = _build_disagreement_map(agent_views)
        decision_implication = _build_decision_implication(scenarios, risk_triggers, scores)

        return ScenarioSimulationResult(
            status=status,
            personas=personas,
            scenarios=scenarios,
            agent_views=agent_views,
            consensus=consensus,
            disagreement_map=disagreement_map,
            market_reaction_table=market_reaction_table,
            risk_triggers=risk_triggers,
            decision_implication=decision_implication,
            scores=scores,
            diagnostics=diagnostics,
        )
    except Exception as exc:  # noqa: BLE001
        if getattr(settings, "scenario_simulation_fail_open", True):
            diagnostics.errors.append(str(exc))
            return ScenarioSimulationResult(status="failed", diagnostics=diagnostics)
        raise


def _normalize_scenario_probabilities(scenarios: list[ScenarioCase]) -> list[ScenarioCase]:
    probabilities = normalize_probabilities({scenario.type: scenario.probability for scenario in scenarios})
    return [scenario.model_copy(update={"probability": probabilities.get(scenario.type, scenario.probability)}) for scenario in scenarios]


def _evidence_doc_id_coverage(evidence_payload: dict[str, Any]) -> float:
    documents = evidence_payload.get("documents") or []
    if not documents:
        return 0.0
    with_doc_id = sum(1 for document in documents if isinstance(document, dict) and document.get("doc_id"))
    return round(with_doc_id / len(documents), 4)


def _build_risk_triggers(scenarios: list[ScenarioCase], evidence_payload: dict[str, Any]) -> list[RiskTrigger]:
    ticker = str(evidence_payload.get("ticker_or_topic") or "").upper()
    doc_ids = primary_doc_ids(evidence_payload)
    category = _asset_risk_category(ticker)
    triggers: list[RiskTrigger] = []
    for scenario in scenarios:
        if scenario.type not in {"bear", "tail"}:
            continue
        for trigger in scenario.triggers[:2]:
            triggers.append(
                RiskTrigger(
                    category=category if scenario.type == "bear" else "data_quality" if not doc_ids else "liquidity",
                    trigger=trigger,
                    direction=scenario.direction,
                    monitoring_data=_monitoring_data(evidence_payload, fallback=trigger),
                    response="Treat as an invalidation or exposure-review condition, not as a trade instruction.",
                    evidence_doc_ids=scenario.evidence_doc_ids[:3],
                    confidence=min(scenario.confidence, confidence_for(evidence_payload)),
                )
            )
    if not evidence_payload.get("documents"):
        triggers.append(
            RiskTrigger(
                category="data_quality",
                trigger="Scenario evidence set is sparse or missing.",
                direction="mixed",
                monitoring_data="retrieved document count, source coverage, metric freshness",
                response="Keep the result at watchlist/framework level until stronger evidence is available.",
                evidence_doc_ids=[],
                confidence=0.35,
            )
        )
    return triggers[:8]


def _asset_risk_category(ticker: str) -> str:
    if any(term in ticker for term in ("TLT", "IEF", "AGG", "HYG", "BOND")):
        return "rates"
    if any(term in ticker for term in ("BTC", "ETH")):
        return "liquidity"
    if "=X" in ticker or "USD" in ticker:
        return "macro"
    return "valuation"


def _monitoring_data(evidence_payload: dict[str, Any], fallback: str) -> str:
    metrics = [
        clean_text(metric.get("name"), limit=80)
        for metric in evidence_payload.get("key_metrics", []) or []
        if isinstance(metric, dict) and metric.get("name")
    ]
    return ", ".join(metrics[:3]) if metrics else clean_text(fallback, limit=120)


def _build_consensus(scenarios: list[ScenarioCase], agent_views: list[AgentView], scores: ScenarioScores | None) -> dict[str, Any]:
    stance_counts = Counter(view.stance for view in agent_views)
    top_stance = stance_counts.most_common(1)[0][0] if stance_counts else "mixed"
    bull = next((scenario for scenario in scenarios if scenario.type == "bull"), None)
    bear = next((scenario for scenario in scenarios if scenario.type == "bear"), None)
    overall_bias = "mixed"
    if scores:
        if scores.risk_score >= 0.65:
            overall_bias = "watchlist"
        elif bull and bear and bull.probability * bull.confidence > bear.probability * bear.confidence + 0.08:
            overall_bias = "constructive"
        elif bear and bull and bear.probability * bear.confidence > bull.probability * bull.confidence + 0.08:
            overall_bias = "watchlist"
    return {
        "overall_bias": overall_bias,
        "main_agreement": f"Most participant views cluster around a {top_stance} stance.",
        "main_disagreement": "Participants disagree most on whether catalysts or risk triggers deserve more weight.",
        "stance_counts": dict(stance_counts),
        "evidence_strength": scores.evidence_strength if scores else None,
        "risk_score": scores.risk_score if scores else None,
    }


def _build_disagreement_map(agent_views: list[AgentView]) -> dict[str, Any]:
    by_scenario: dict[str, Counter] = {}
    for view in agent_views:
        by_scenario.setdefault(view.scenario_id, Counter())[view.stance] += 1
    split = {
        scenario_id: dict(counter)
        for scenario_id, counter in by_scenario.items()
        if len(counter) > 1
    }
    return {
        "by_scenario": {scenario_id: dict(counter) for scenario_id, counter in by_scenario.items()},
        "split_scenarios": list(split.keys()),
        "summary": "Stance splits show where evidence interpretation differs across personas." if split else "Participant stances are relatively clustered.",
    }


def _build_decision_implication(
    scenarios: list[ScenarioCase],
    risk_triggers: list[RiskTrigger],
    scores: ScenarioScores | None,
) -> DecisionImplication:
    base = next((scenario for scenario in scenarios if scenario.type == "base"), None)
    bull = next((scenario for scenario in scenarios if scenario.type == "bull"), None)
    bear = next((scenario for scenario in scenarios if scenario.type == "bear"), None)
    tail = next((scenario for scenario in scenarios if scenario.type == "tail"), None)
    if scores is None:
        bias = "mixed"
        uncertainty = "high"
    elif scores.evidence_strength < 0.35:
        bias = "watchlist"
        uncertainty = "high"
    elif scores.risk_score >= 0.65:
        bias = "avoid"
        uncertainty = "high"
    elif bear and tail and bull and (bear.probability + tail.probability) > bull.probability + 0.12:
        bias = "watchlist"
        uncertainty = "medium"
    elif scores.consensus_score >= 0.55 and scores.risk_score < 0.45:
        bias = "constructive"
        uncertainty = "medium" if scores.evidence_strength < 0.7 else "low"
    else:
        bias = "mixed"
        uncertainty = "medium"

    entry_conditions = unique_strings((bull.triggers if bull else []) + (base.triggers if base else []), limit=4)
    invalidation_conditions = unique_strings((bear.triggers if bear else []) + (tail.triggers if tail else []), limit=4)
    monitoring_indicators = unique_strings([trigger.monitoring_data for trigger in risk_triggers], limit=5)
    risk_management = [
        "Use the scenarios as a decision framework rather than a deterministic forecast.",
        "Review exposure if invalidation conditions become better supported by evidence.",
    ]
    return DecisionImplication(
        bias=bias,
        entry_conditions=entry_conditions,
        invalidation_conditions=invalidation_conditions,
        monitoring_indicators=monitoring_indicators,
        risk_management=risk_management,
        uncertainty=uncertainty,
    )
