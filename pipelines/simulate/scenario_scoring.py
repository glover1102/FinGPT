from __future__ import annotations

from collections import Counter

from core.schemas.simulation import AgentPersona, AgentView, RiskTrigger, ScenarioCase, ScenarioScores
from pipelines.simulate.fallback import clamp


def score_simulation(
    scenarios: list[ScenarioCase],
    personas: list[AgentPersona],
    agent_views: list[AgentView],
    risk_triggers: list[RiskTrigger],
    evidence_payload: dict,
) -> ScenarioScores:
    evidence_strength = _evidence_strength(scenarios, agent_views, evidence_payload)
    consensus_score, disagreement_score = _stance_scores(agent_views)
    asymmetry_score = _asymmetry_score(scenarios)
    timing_score = _timing_score(scenarios, risk_triggers, evidence_payload)
    risk_score = _risk_score(scenarios, risk_triggers, evidence_strength)
    return ScenarioScores(
        evidence_strength=evidence_strength,
        consensus_score=consensus_score,
        disagreement_score=disagreement_score,
        asymmetry_score=asymmetry_score,
        timing_score=timing_score,
        risk_score=risk_score,
    )


def _evidence_strength(scenarios: list[ScenarioCase], agent_views: list[AgentView], evidence_payload: dict) -> float:
    documents = evidence_payload.get("documents") or []
    metrics = evidence_payload.get("key_metrics") or []
    doc_quality = 0.0
    if documents:
        with_id = sum(1 for doc in documents if doc.get("doc_id"))
        with_source = sum(1 for doc in documents if doc.get("source"))
        with_date = sum(1 for doc in documents if doc.get("date"))
        doc_quality = (with_id + with_source + with_date) / (3 * len(documents))
    metric_quality = 0.0
    if metrics:
        with_as_of = sum(1 for metric in metrics if isinstance(metric, dict) and metric.get("as_of"))
        metric_quality = with_as_of / len(metrics)
    scenario_coverage = sum(1 for scenario in scenarios if scenario.evidence_doc_ids) / max(1, len(scenarios))
    view_coverage = sum(1 for view in agent_views if view.key_evidence_doc_ids) / max(1, len(agent_views))
    return clamp(0.35 * doc_quality + 0.25 * metric_quality + 0.25 * scenario_coverage + 0.15 * view_coverage)


def _stance_scores(agent_views: list[AgentView]) -> tuple[float, float]:
    if not agent_views:
        return 0.0, 0.0
    counts = Counter(view.stance for view in agent_views)
    total = sum(counts.values())
    max_share = max(counts.values()) / total
    avg_confidence = sum(view.confidence for view in agent_views) / total
    coexistence = len([stance for stance in ("support", "oppose", "mixed", "neutral") if counts.get(stance)])
    consensus = clamp((max_share * 0.65) + (avg_confidence * 0.35))
    disagreement = clamp((1.0 - max_share) * 0.75 + ((coexistence - 1) / 3) * 0.25)
    return consensus, disagreement


def _asymmetry_score(scenarios: list[ScenarioCase]) -> float:
    bull = sum(s.probability * s.confidence for s in scenarios if s.type == "bull")
    downside = sum(s.probability * s.confidence for s in scenarios if s.type in {"bear", "tail"})
    if bull == 0 and downside == 0:
        return 0.0
    return clamp(abs(bull - downside) / max(bull + downside, 0.0001))


def _timing_score(scenarios: list[ScenarioCase], risk_triggers: list[RiskTrigger], evidence_payload: dict) -> float:
    trigger_coverage = sum(1 for scenario in scenarios if scenario.triggers) / max(1, len(scenarios))
    invalidation_coverage = sum(1 for scenario in scenarios if scenario.invalidation_signals) / max(1, len(scenarios))
    monitoring_coverage = min(1.0, (len(risk_triggers) + len(evidence_payload.get("key_metrics") or [])) / 8)
    return clamp(0.4 * trigger_coverage + 0.35 * invalidation_coverage + 0.25 * monitoring_coverage)


def _risk_score(scenarios: list[ScenarioCase], risk_triggers: list[RiskTrigger], evidence_strength: float) -> float:
    bear = next((scenario for scenario in scenarios if scenario.type == "bear"), None)
    tail = next((scenario for scenario in scenarios if scenario.type == "tail"), None)
    bear_component = (bear.probability * bear.confidence) if bear else 0.0
    tail_component = (tail.probability * tail.confidence * 1.6) if tail else 0.0
    trigger_component = min(1.0, len(risk_triggers) / 8)
    weak_evidence_component = 1.0 - evidence_strength
    return clamp(0.35 * bear_component + 0.25 * tail_component + 0.25 * trigger_component + 0.15 * weak_evidence_component)
