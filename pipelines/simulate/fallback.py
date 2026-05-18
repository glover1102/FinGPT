from __future__ import annotations

from typing import Any

from core.schemas.simulation import AgentPersona, AgentView, ScenarioCase


FALLBACK_PROBABILITIES = {
    "base": 0.45,
    "bull": 0.25,
    "bear": 0.25,
    "tail": 0.05,
}

UNSUPPORTED_PRICE_TARGET_TERMS = (
    "target price",
    "price target",
    "목표가",
    "will reach",
    "guaranteed",
    "certain return",
)


def clamp(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def clean_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "..."


def unique_strings(values: list[Any] | tuple[Any, ...] | None, *, limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = clean_text(value, limit=360)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def normalize_probabilities(raw: dict[str, float] | None = None) -> dict[str, float]:
    values = dict(FALLBACK_PROBABILITIES)
    if raw:
        for key in values:
            values[key] = max(0.0, float(raw.get(key, values[key]) or 0.0))
    total = sum(values.values())
    if total <= 0:
        return dict(FALLBACK_PROBABILITIES)
    normalized = {key: round(value / total, 6) for key, value in values.items()}
    drift = round(1.0 - sum(normalized.values()), 6)
    normalized["tail"] = round(normalized["tail"] + drift, 6)
    return normalized


def primary_doc_ids(evidence_payload: dict[str, Any], *, limit: int = 4) -> list[str]:
    candidates: list[Any] = []
    candidates.extend(evidence_payload.get("bull_evidence_ids") or [])
    candidates.extend(evidence_payload.get("bear_evidence_ids") or [])
    for document in evidence_payload.get("documents") or []:
        if isinstance(document, dict):
            candidates.append(document.get("doc_id"))
    return unique_strings(candidates, limit=limit)


def evidence_is_weak(evidence_payload: dict[str, Any]) -> bool:
    docs = evidence_payload.get("documents") or []
    metrics = evidence_payload.get("key_metrics") or []
    evidence_ids = primary_doc_ids(evidence_payload, limit=8)
    return len(docs) < 2 and len(metrics) < 2 and len(evidence_ids) < 2


def confidence_for(evidence_payload: dict[str, Any], *, adjustment: float = 0.0) -> float:
    base = 0.36 if evidence_is_weak(evidence_payload) else 0.62
    return clamp(base + adjustment, default=base)


def asset_label(evidence_payload: dict[str, Any]) -> str:
    return clean_text(evidence_payload.get("ticker_or_topic") or "the asset", limit=80) or "the asset"


def fallback_scenarios(evidence_payload: dict[str, Any]) -> list[ScenarioCase]:
    ticker = asset_label(evidence_payload)
    doc_ids = primary_doc_ids(evidence_payload)
    bull_points = unique_strings(evidence_payload.get("bull_points") or [], limit=2)
    bear_points = unique_strings(evidence_payload.get("bear_points") or [], limit=2)
    summary = clean_text(evidence_payload.get("summary"), limit=220)
    uncertainty = clean_text(evidence_payload.get("uncertainty"), limit=180)
    weak = evidence_is_weak(evidence_payload)
    low_conf_note = "Evidence is limited, so this case should be treated as a low-confidence framework."
    probabilities = normalize_probabilities()

    base_trigger = bull_points[:1] + bear_points[:1] or [summary or f"New evidence for {ticker} remains mixed."]
    base_invalidation = bear_points[:1] or [uncertainty or "Fresh evidence materially contradicts the current summary."]
    bull_trigger = bull_points or [f"Positive catalysts for {ticker} strengthen across the supplied evidence."]
    bear_trigger = bear_points or [f"Negative risks for {ticker} dominate the supplied evidence."]
    tail_trigger = bear_points[:1] or [f"A low-probability adverse regime shift affects {ticker}."]

    return [
        ScenarioCase(
            id="base_case",
            name="Base Case",
            type="base",
            probability=probabilities["base"],
            direction="mixed" if bull_points and bear_points else "neutral",
            time_horizon="medium_term",
            assumptions=unique_strings([summary or f"{ticker} follows the current evidence mix.", low_conf_note if weak else ""], limit=3),
            triggers=unique_strings(base_trigger, limit=3),
            invalidation_signals=unique_strings(base_invalidation, limit=3),
            expected_reaction="Market reaction remains balanced while investors wait for clearer confirmation.",
            evidence_doc_ids=doc_ids,
            confidence=confidence_for(evidence_payload),
        ),
        ScenarioCase(
            id="bull_case",
            name="Bull Case",
            type="bull",
            probability=probabilities["bull"],
            direction="bullish",
            time_horizon="medium_term",
            assumptions=unique_strings([f"Positive catalysts for {ticker} strengthen.", "Downside risks fail to materialize."], limit=3),
            triggers=unique_strings(bull_trigger, limit=4),
            invalidation_signals=unique_strings(bear_points or ["Positive evidence weakens or is contradicted by fresher data."], limit=4),
            expected_reaction="Risk appetite improves if catalysts are confirmed by evidence.",
            evidence_doc_ids=doc_ids,
            confidence=confidence_for(evidence_payload, adjustment=0.03),
        ),
        ScenarioCase(
            id="bear_case",
            name="Bear Case",
            type="bear",
            probability=probabilities["bear"],
            direction="bearish",
            time_horizon="medium_term",
            assumptions=unique_strings([f"Negative risks for {ticker} dominate.", "Positive catalysts are delayed or diluted."], limit=3),
            triggers=unique_strings(bear_trigger, limit=4),
            invalidation_signals=unique_strings(bull_points or ["Risk evidence fades or new data confirms stronger fundamentals."], limit=4),
            expected_reaction="Investors reduce risk if the negative evidence becomes more persistent.",
            evidence_doc_ids=doc_ids,
            confidence=confidence_for(evidence_payload, adjustment=0.02),
        ),
        ScenarioCase(
            id="tail_risk_case",
            name="Tail-Risk Case",
            type="tail",
            probability=probabilities["tail"],
            direction="bearish",
            time_horizon="event_risk",
            assumptions=unique_strings([f"{ticker} faces a low-probability but high-impact adverse event.", low_conf_note if weak else ""], limit=3),
            triggers=unique_strings(tail_trigger + ["Liquidity, policy, credit, or positioning stress becomes the dominant driver."], limit=4),
            invalidation_signals=unique_strings(["Stress indicators normalize and downside evidence is not corroborated."], limit=3),
            expected_reaction="Volatility rises and risk-sensitive participants demand stronger confirmation before adding exposure.",
            evidence_doc_ids=doc_ids,
            confidence=confidence_for(evidence_payload, adjustment=-0.12),
        ),
    ]


def fallback_personas(evidence_payload: dict[str, Any], count: int = 6) -> list[AgentPersona]:
    from pipelines.simulate.persona_builder import persona_templates

    templates = persona_templates(evidence_payload)
    bounded = max(5, min(8, count, len(templates)))
    return [AgentPersona(**template) for template in templates[:bounded]]


def fallback_agent_views(personas: list[AgentPersona], scenarios: list[ScenarioCase]) -> list[AgentView]:
    views: list[AgentView] = []
    for persona in personas:
        for scenario in scenarios:
            stance = "neutral" if scenario.type == "base" else "mixed"
            views.append(
                AgentView(
                    agent_id=persona.id,
                    scenario_id=scenario.id,
                    stance=stance,
                    confidence=clamp(min(persona_confidence(persona), scenario.confidence)),
                    thesis=f"{persona.role} treats {scenario.name} as a scenario to monitor, not a prediction.",
                    key_evidence_doc_ids=scenario.evidence_doc_ids[:3],
                    counterarguments=["Available evidence may be incomplete or stale."],
                    change_mind_conditions=scenario.invalidation_signals[:2] or ["Material new evidence changes the scenario balance."],
                )
            )
    return views


def persona_confidence(persona: AgentPersona) -> float:
    lowered = " ".join([persona.role, persona.bias, persona.risk_preference]).lower()
    if "risk" in lowered or "skeptic" in lowered:
        return 0.58
    if "trader" in lowered or "momentum" in lowered:
        return 0.54
    return 0.56


def contains_unsupported_price_target(text: str) -> bool:
    lowered = str(text or "").lower()
    if any(term in lowered for term in UNSUPPORTED_PRICE_TARGET_TERMS):
        return True
    return False
