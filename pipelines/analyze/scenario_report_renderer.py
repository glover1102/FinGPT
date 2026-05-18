from __future__ import annotations

from html import escape
from typing import Any, Mapping, Sequence


def _clean_sentence(value: object) -> str:
    return " ".join(str(value or "").split()).strip(" -")


def _scenario_simulation_payload(response: Any) -> dict[str, Any] | None:
    meta = getattr(response, "execution_meta", None)
    extras = getattr(meta, "extras", None) or {}
    payload = extras.get("scenario_simulation")
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return payload if isinstance(payload, dict) else None


def _as_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _join_values(value: object, *, limit: int = 4) -> str:
    items = [_clean_sentence(item) for item in _as_list(value)]
    items = [item for item in items if item]
    if not items:
        return "-"
    suffix = "" if len(items) <= limit else f" (+{len(items) - limit})"
    return "; ".join(items[:limit]) + suffix


def _md_cell(value: object) -> str:
    text = _clean_sentence(value) or "-"
    return text.replace("|", "\\|")


def _scenario_diagnostics(payload: Mapping[str, Any]) -> list[str]:
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    errors = _as_list(diagnostics.get("errors"))
    warnings = _as_list(diagnostics.get("warnings"))
    return [_clean_sentence(item) for item in [*errors, *warnings] if _clean_sentence(item)]


def scenario_simulation_md(response: Any) -> str:
    payload = _scenario_simulation_payload(response)
    if not payload:
        return ""

    if payload.get("status") == "failed":
        diagnostics = _scenario_diagnostics(payload)
        diagnostic_block = "\n".join(f"- {_md_cell(item)}" for item in diagnostics) or "- unavailable"
        return (
            "## Scenario Simulation\n\n"
            "Scenario simulation was not available for this run.\n\n"
            "Diagnostics:\n"
            f"{diagnostic_block}\n\n"
        )

    scenarios = _as_list(payload.get("scenarios"))
    scenario_rows = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        probability = scenario.get("probability")
        confidence = scenario.get("confidence")
        probability_text = f"{float(probability):.2f}" if isinstance(probability, (int, float)) else "-"
        confidence_text = f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "-"
        scenario_rows.append(
            "| "
            + " | ".join(
                [
                    _md_cell(scenario.get("name") or scenario.get("id")),
                    probability_text,
                    _md_cell(scenario.get("direction")),
                    confidence_text,
                    _md_cell(_join_values(scenario.get("triggers"))),
                    _md_cell(_join_values(scenario.get("invalidation_signals"))),
                ]
            )
            + " |"
        )
    if not scenario_rows:
        scenario_rows.append("| - | - | - | - | - | - |")

    consensus = payload.get("consensus") if isinstance(payload.get("consensus"), dict) else {}
    scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    disagreement_map = payload.get("disagreement_map") if isinstance(payload.get("disagreement_map"), dict) else {}
    agent_rows = []
    for view in _as_list(payload.get("agent_views")):
        if not isinstance(view, dict):
            continue
        confidence = view.get("confidence")
        confidence_text = f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "-"
        agent_rows.append(
            "| "
            + " | ".join(
                [
                    _md_cell(view.get("agent_id")),
                    _md_cell(view.get("scenario_id")),
                    _md_cell(view.get("stance")),
                    confidence_text,
                    _md_cell(view.get("thesis")),
                    _md_cell(_join_values(view.get("change_mind_conditions"), limit=2)),
                ]
            )
            + " |"
        )
    if not agent_rows:
        agent_rows.append("| - | - | - | - | - | - |")

    risk_rows = []
    for trigger in _as_list(payload.get("risk_triggers")):
        if not isinstance(trigger, dict):
            continue
        risk_rows.append(
            "| "
            + " | ".join(
                [
                    _md_cell(trigger.get("category")),
                    _md_cell(trigger.get("trigger")),
                    _md_cell(trigger.get("direction")),
                    _md_cell(trigger.get("monitoring_data")),
                    _md_cell(trigger.get("response")),
                ]
            )
            + " |"
        )
    if not risk_rows:
        risk_rows.append("| - | - | - | - | - |")

    decision = payload.get("decision_implication") if isinstance(payload.get("decision_implication"), dict) else {}
    evidence_strength = scores.get("evidence_strength", consensus.get("evidence_strength", "-"))
    risk_score = scores.get("risk_score", consensus.get("risk_score", "-"))
    if isinstance(evidence_strength, (int, float)):
        evidence_strength = f"{float(evidence_strength):.2f}"
    if isinstance(risk_score, (int, float)):
        risk_score = f"{float(risk_score):.2f}"

    return f"""## Scenario Simulation

### Scenario Cases

| Scenario | Probability | Direction | Confidence | Key Triggers | Invalidation |
|---|---:|---|---:|---|---|
{chr(10).join(scenario_rows)}

### Market Participant Consensus

- Overall bias: {_md_cell(consensus.get("overall_bias") or decision.get("bias"))}
- Main agreement: {_md_cell(consensus.get("main_agreement"))}
- Main disagreement: {_md_cell(consensus.get("main_disagreement") or disagreement_map.get("summary"))}
- Evidence strength: {_md_cell(evidence_strength)}
- Risk score: {_md_cell(risk_score)}

### Agent Debate Summary

| Agent | Scenario | Stance | Confidence | Thesis | What Changes Their Mind |
|---|---|---|---:|---|---|
{chr(10).join(agent_rows)}

### Risk Triggers

| Category | Trigger | Direction | Monitoring Data | Response |
|---|---|---|---|---|
{chr(10).join(risk_rows)}

### Decision Checklist

- Bias: {_md_cell(decision.get("bias"))}
- Entry conditions: {_md_cell(_join_values(decision.get("entry_conditions")))}
- Invalidation conditions: {_md_cell(_join_values(decision.get("invalidation_conditions")))}
- Monitoring indicators: {_md_cell(_join_values(decision.get("monitoring_indicators")))}
- Risk management: {_md_cell(_join_values(decision.get("risk_management")))}
- Uncertainty: {_md_cell(decision.get("uncertainty"))}
- Disclaimer: {_md_cell(decision.get("disclaimer"))}

"""


def scenario_simulation_html(response: Any) -> str:
    payload = _scenario_simulation_payload(response)
    if not payload:
        return ""

    if payload.get("status") == "failed":
        diagnostics = _scenario_diagnostics(payload)
        diagnostic_html = "".join(f"<li>{escape(item)}</li>" for item in diagnostics) or "<li>unavailable</li>"
        return (
            "<h2>Scenario Simulation</h2>"
            "<p>Scenario simulation was not available for this run.</p>"
            f"<p><strong>Diagnostics:</strong></p><ul>{diagnostic_html}</ul>"
        )

    def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
        header_html = "".join(
            f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(header)}</th>"
            for header in headers
        )
        body_html = ""
        for row in rows:
            body_html += "<tr>" + "".join(
                f"<td style=\"padding:4px 8px;vertical-align:top;\">{escape(_clean_sentence(value) or '-')}</td>"
                for value in row
            ) + "</tr>"
        return f"<table style=\"border-collapse:collapse;width:100%;margin:8px 0;\"><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"

    scenario_rows = []
    for scenario in _as_list(payload.get("scenarios")):
        if not isinstance(scenario, dict):
            continue
        probability = scenario.get("probability")
        confidence = scenario.get("confidence")
        scenario_rows.append(
            [
                scenario.get("name") or scenario.get("id"),
                f"{float(probability):.2f}" if isinstance(probability, (int, float)) else "-",
                scenario.get("direction"),
                f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "-",
                _join_values(scenario.get("triggers")),
                _join_values(scenario.get("invalidation_signals")),
            ]
        )
    scenario_rows = scenario_rows or [["-", "-", "-", "-", "-", "-"]]

    agent_rows = []
    for view in _as_list(payload.get("agent_views")):
        if not isinstance(view, dict):
            continue
        confidence = view.get("confidence")
        agent_rows.append(
            [
                view.get("agent_id"),
                view.get("scenario_id"),
                view.get("stance"),
                f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "-",
                view.get("thesis"),
                _join_values(view.get("change_mind_conditions"), limit=2),
            ]
        )
    agent_rows = agent_rows or [["-", "-", "-", "-", "-", "-"]]

    risk_rows = []
    for trigger in _as_list(payload.get("risk_triggers")):
        if not isinstance(trigger, dict):
            continue
        risk_rows.append(
            [
                trigger.get("category"),
                trigger.get("trigger"),
                trigger.get("direction"),
                trigger.get("monitoring_data"),
                trigger.get("response"),
            ]
        )
    risk_rows = risk_rows or [["-", "-", "-", "-", "-"]]

    consensus = payload.get("consensus") if isinstance(payload.get("consensus"), dict) else {}
    scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    disagreement_map = payload.get("disagreement_map") if isinstance(payload.get("disagreement_map"), dict) else {}
    decision = payload.get("decision_implication") if isinstance(payload.get("decision_implication"), dict) else {}
    evidence_strength = scores.get("evidence_strength", consensus.get("evidence_strength", "-"))
    risk_score = scores.get("risk_score", consensus.get("risk_score", "-"))
    if isinstance(evidence_strength, (int, float)):
        evidence_strength = f"{float(evidence_strength):.2f}"
    if isinstance(risk_score, (int, float)):
        risk_score = f"{float(risk_score):.2f}"

    consensus_html = (
        "<ul>"
        f"<li><strong>Overall bias</strong>: {escape(_clean_sentence(consensus.get('overall_bias') or decision.get('bias')) or '-')}</li>"
        f"<li><strong>Main agreement</strong>: {escape(_clean_sentence(consensus.get('main_agreement')) or '-')}</li>"
        f"<li><strong>Main disagreement</strong>: {escape(_clean_sentence(consensus.get('main_disagreement') or disagreement_map.get('summary')) or '-')}</li>"
        f"<li><strong>Evidence strength</strong>: {escape(str(evidence_strength))}</li>"
        f"<li><strong>Risk score</strong>: {escape(str(risk_score))}</li>"
        "</ul>"
    )
    checklist_html = (
        "<ul>"
        f"<li><strong>Bias</strong>: {escape(_clean_sentence(decision.get('bias')) or '-')}</li>"
        f"<li><strong>Entry conditions</strong>: {escape(_join_values(decision.get('entry_conditions')))}</li>"
        f"<li><strong>Invalidation conditions</strong>: {escape(_join_values(decision.get('invalidation_conditions')))}</li>"
        f"<li><strong>Monitoring indicators</strong>: {escape(_join_values(decision.get('monitoring_indicators')))}</li>"
        f"<li><strong>Risk management</strong>: {escape(_join_values(decision.get('risk_management')))}</li>"
        f"<li><strong>Uncertainty</strong>: {escape(_clean_sentence(decision.get('uncertainty')) or '-')}</li>"
        f"<li><strong>Disclaimer</strong>: {escape(_clean_sentence(decision.get('disclaimer')) or '-')}</li>"
        "</ul>"
    )
    return (
        "<h2>Scenario Simulation</h2>"
        "<h3>Scenario Cases</h3>"
        + table(["Scenario", "Probability", "Direction", "Confidence", "Key Triggers", "Invalidation"], scenario_rows)
        + "<h3>Market Participant Consensus</h3>"
        + consensus_html
        + "<h3>Agent Debate Summary</h3>"
        + table(["Agent", "Scenario", "Stance", "Confidence", "Thesis", "What Changes Their Mind"], agent_rows)
        + "<h3>Risk Triggers</h3>"
        + table(["Category", "Trigger", "Direction", "Monitoring Data", "Response"], risk_rows)
        + "<h3>Decision Checklist</h3>"
        + checklist_html
    )
