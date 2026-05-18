from __future__ import annotations

from html import escape

from core.schemas.topic import DecisionSection, ExecutionStrategy, ScenarioAnalysis, TopicResponse
from pipelines.analyze.scenario_report_renderer import scenario_simulation_html, scenario_simulation_md


def _ko_labels() -> dict[str, str]:
    return {
        "title": "주제 투자 메모",
        "question": "질문",
        "summary": "Decision Summary",
        "quant_snapshot": "Quant Snapshot",
        "core_analysis": "Evidence-backed Core Analysis",
        "asset_overview": "대상/주제 개요",
        "macro_regime": "거시/정책 환경",
        "rate_structure": "가격/시장 구조",
        "scenario_analysis": "Scenario Table",
        "risk_factors": "Risk/Reward",
        "execution": "Execution Plan",
        "pricing_reality": "Market Pricing vs Reality",
        "synthesis": "Synthesis",
        "decision_edge": "Decision Edge",
        "conclusion": "Conclusion",
        "drivers": "상방 동인",
        "risks": "하방 리스크",
        "touchpoints": "관련 자산 / 표현 수단",
        "metrics": "핵심 지표",
        "as_of": "기준일",
        "source": "출처",
        "unknown_as_of": "unknown",
        "open_questions": "판단을 바꿀 확인 질문",
        "citations": "인용 근거",
        "evidence": "Evidence Base",
        "none": "식별된 항목 없음",
        "no_context": "수집된 근거 문서 없음",
        "probability": "확률",
        "outcome": "예상 전개",
        "implication": "자산 영향",
        "decision": "판단",
        "trigger": "진입/확인 조건",
        "rationale": "근거",
        "risk_control": "리스크 관리",
        "uncertainty": "불확실성",
        "evidence_label": "근거",
    }


def _labels(language: str) -> dict[str, str]:
    if str(language or "ko").strip().lower() == "ko":
        return _ko_labels()
    labels = _ko_labels()
    labels.update(
        {
            "title": "Topic Investment Memo",
            "question": "Question",
            "asset_overview": "Target Asset / Theme Overview",
            "macro_regime": "Macro / Policy Context",
            "rate_structure": "Pricing / Market Structure",
            "risk_factors": "Risk/Reward",
            "execution": "Execution Plan",
            "open_questions": "What Would Change This View",
            "none": "None identified",
            "no_context": "No context retrieved",
            "as_of": "As of",
            "source": "Source",
            "evidence_label": "Evidence",
        }
    )
    return labels


def _asset_class(response: TopicResponse) -> str:
    extras = {}
    if response.execution_meta and isinstance(response.execution_meta.extras, dict):
        extras = response.execution_meta.extras
    quant_snapshot = extras.get("quant_snapshot") if isinstance(extras.get("quant_snapshot"), dict) else {}
    return str(extras.get("asset_class") or quant_snapshot.get("asset_class") or "").strip().lower()


def _asset_labels(response: TopicResponse, labels: dict[str, str]) -> dict[str, str]:
    updated = dict(labels)
    asset_class = _asset_class(response)
    overrides: dict[str, dict[str, str]] = {
        "rates_bonds": {
            "asset_overview": "자산 개요 / 듀레이션 특성",
            "macro_regime": "성장·물가·Fed 레짐",
            "rate_structure": "금리 곡선 / 실질금리 / 기간 프리미엄",
            "pricing_reality": "채권 가격 매력도 vs 금리 리스크",
        },
        "credit": {
            "asset_overview": "신용 노출 / 스프레드 프록시",
            "macro_regime": "유동성 / 부도 사이클",
            "rate_structure": "스프레드·주식-신용 괴리",
            "pricing_reality": "시장 가격에 반영된 신용 스트레스",
        },
        "fx": {
            "asset_overview": "통화쌍 / 달러 노출",
            "macro_regime": "금리차 / 정책 divergence",
            "rate_structure": "환율 추세 / 달러 유동성",
            "pricing_reality": "환율 포지셔닝 vs 매크로 현실",
        },
        "commodity": {
            "asset_overview": "원자재 노출 / 상품 구조",
            "macro_regime": "달러·실질금리·수요 환경",
            "rate_structure": "수급 / 재고 / 선물곡선",
            "pricing_reality": "현물 가격 vs 수급 현실",
        },
        "crypto": {
            "asset_overview": "크립토 자산 / 유동성 민감도",
            "macro_regime": "위험선호 / 달러 유동성 / 규제",
            "rate_structure": "ETF flow / 거래소·시장 구조",
            "pricing_reality": "시장 내러티브 vs 온체인·flow 근거",
        },
        "sector_theme": {
            "asset_overview": "테마 범위 / 수혜·피해 자산",
            "macro_regime": "수요 주기 / Capex 환경",
            "rate_structure": "가격 결정력 / 밸류체인 구조",
            "pricing_reality": "시장 기대 vs 실적 현실",
        },
    }
    updated.update(overrides.get(asset_class, {}))
    return updated


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe_key(value: object) -> str:
    text = _clean(value).lower()
    return "".join(ch for ch in text if ch.isalnum() or "\uac00" <= ch <= "\ud7a3")


def _dedupe_texts(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _clean(item)
        if not clean:
            continue
        key = _dedupe_key(clean)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _md_bullets(items: list[str], none: str) -> str:
    cleaned = _dedupe_texts(items)
    return "\n".join(f"- {item}" for item in cleaned) if cleaned else f"- {none}"


def _html_list(items: list[str], none: str) -> str:
    cleaned = _dedupe_texts(items)
    if not cleaned:
        return f"<ul><li>{escape(none)}</li></ul>"
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in cleaned) + "</ul>"


def _evidence_lookup(response: TopicResponse) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for item in response.raw_context:
        metadata = item.metadata or {}
        doc_id = str(metadata.get("parent_doc_id") or metadata.get("doc_id") or "").strip()
        if not doc_id:
            continue
        lookup[doc_id] = {"date": _clean(item.date) or "unknown", "source": _clean(item.source) or "doc", "title": _clean(item.title)}
    for citation in response.citations:
        doc_id = _clean(citation.doc_id)
        if doc_id and doc_id not in lookup:
            lookup[doc_id] = {"date": _clean(citation.date) or "unknown", "source": _clean(citation.source) or "doc", "title": _clean(citation.title)}
    return lookup


def _evidence_suffix_md(ids: list[str], lookup: dict[str, dict[str, str]], labels: dict[str, str]) -> str:
    cleaned = [str(doc_id).strip() for doc_id in ids if str(doc_id).strip()]
    if not cleaned:
        return ""
    parts = []
    for doc_id in cleaned:
        info = lookup.get(doc_id, {})
        parts.append(f"`{doc_id}` · {info.get('date') or 'unknown'} · {info.get('source') or 'doc'}")
    return f"\n- **{labels['evidence_label']}**: " + "; ".join(parts)


def _evidence_suffix_html(ids: list[str], lookup: dict[str, dict[str, str]], labels: dict[str, str]) -> str:
    cleaned = [str(doc_id).strip() for doc_id in ids if str(doc_id).strip()]
    if not cleaned:
        return ""
    chips = []
    for doc_id in cleaned:
        info = lookup.get(doc_id, {})
        label = f"{doc_id} · {info.get('date') or 'unknown'} · {info.get('source') or 'doc'}"
        chips.append(f"<code>{escape(label)}</code>")
    return f"<p><strong>{escape(labels['evidence_label'])}</strong>: {'; '.join(chips)}</p>"


def _section_md(sections: list[DecisionSection], labels: dict[str, str], evidence_lookup: dict[str, dict[str, str]]) -> str:
    if not sections:
        return f"- {labels['none']}"
    parts: list[str] = []
    for section in sections:
        if section.title:
            parts.append(f"#### {section.title}")
        parts.extend(f"- {bullet}" for bullet in section.bullets)
        if section.conclusion:
            parts.append(f"- **{labels['conclusion']}**: {section.conclusion}")
        suffix = _evidence_suffix_md(list(section.evidence_doc_ids), evidence_lookup, labels)
        if suffix:
            parts.append(suffix)
    return "\n".join(parts).strip()


def _section_html(sections: list[DecisionSection], labels: dict[str, str], evidence_lookup: dict[str, dict[str, str]]) -> str:
    if not sections:
        return f"<p>{escape(labels['none'])}</p>"
    blocks: list[str] = []
    for section in sections:
        title = f"<h4>{escape(section.title)}</h4>" if section.title else ""
        bullets = "".join(f"<li>{escape(bullet)}</li>" for bullet in section.bullets)
        conclusion = f"<p><strong>{escape(labels['conclusion'])}</strong>: {escape(section.conclusion)}</p>" if section.conclusion else ""
        blocks.append(f"{title}<ul>{bullets}</ul>{conclusion}{_evidence_suffix_html(list(section.evidence_doc_ids), evidence_lookup, labels)}")
    return "".join(blocks)


def _scenario_md(scenarios: list[ScenarioAnalysis], labels: dict[str, str], evidence_lookup: dict[str, dict[str, str]]) -> str:
    if not scenarios:
        return f"- {labels['none']}"
    parts: list[str] = []
    for scenario in scenarios:
        parts.append(f"#### {scenario.scenario or labels['scenario_analysis']}")
        if scenario.probability:
            parts.append(f"- **{labels['probability']}**: {scenario.probability}")
        if scenario.expected_outcome:
            parts.append(f"- **{labels['outcome']}**: {scenario.expected_outcome}")
        if scenario.asset_implication:
            parts.append(f"- **{labels['implication']}**: {scenario.asset_implication}")
        if scenario.decision_read:
            parts.append(f"- **{labels['decision']}**: {scenario.decision_read}")
        suffix = _evidence_suffix_md(list(scenario.evidence_doc_ids), evidence_lookup, labels)
        if suffix:
            parts.append(suffix)
    return "\n".join(parts)


def _scenario_html(scenarios: list[ScenarioAnalysis], labels: dict[str, str], evidence_lookup: dict[str, dict[str, str]]) -> str:
    if not scenarios:
        return f"<p>{escape(labels['none'])}</p>"
    blocks: list[str] = []
    for scenario in scenarios:
        rows = []
        for label_key, value in (
            ("probability", scenario.probability),
            ("outcome", scenario.expected_outcome),
            ("implication", scenario.asset_implication),
            ("decision", scenario.decision_read),
        ):
            if value:
                rows.append(f"<li><strong>{escape(labels[label_key])}</strong>: {escape(value)}</li>")
        blocks.append(f"<h4>{escape(scenario.scenario or labels['scenario_analysis'])}</h4><ul>{''.join(rows)}</ul>{_evidence_suffix_html(list(scenario.evidence_doc_ids), evidence_lookup, labels)}")
    return "".join(blocks)


def _execution_md(strategies: list[ExecutionStrategy], labels: dict[str, str], evidence_lookup: dict[str, dict[str, str]]) -> str:
    if not strategies:
        return f"- {labels['none']}"
    parts: list[str] = []
    for strategy in strategies:
        parts.append(f"#### {strategy.strategy or labels['execution']}")
        if strategy.trigger:
            parts.append(f"- **{labels['trigger']}**: {strategy.trigger}")
        if strategy.rationale:
            parts.append(f"- **{labels['rationale']}**: {strategy.rationale}")
        if strategy.risk_control:
            parts.append(f"- **{labels['risk_control']}**: {strategy.risk_control}")
        suffix = _evidence_suffix_md(list(strategy.evidence_doc_ids), evidence_lookup, labels)
        if suffix:
            parts.append(suffix)
    return "\n".join(parts)


def _execution_html(strategies: list[ExecutionStrategy], labels: dict[str, str], evidence_lookup: dict[str, dict[str, str]]) -> str:
    if not strategies:
        return f"<p>{escape(labels['none'])}</p>"
    blocks: list[str] = []
    for strategy in strategies:
        rows = []
        for label_key, value in (
            ("trigger", strategy.trigger),
            ("rationale", strategy.rationale),
            ("risk_control", strategy.risk_control),
        ):
            if value:
                rows.append(f"<li><strong>{escape(labels[label_key])}</strong>: {escape(value)}</li>")
        blocks.append(f"<h4>{escape(strategy.strategy or labels['execution'])}</h4><ul>{''.join(rows)}</ul>{_evidence_suffix_html(list(strategy.evidence_doc_ids), evidence_lookup, labels)}")
    return "".join(blocks)


def _section_conclusions(sections: list[DecisionSection]) -> list[str]:
    return [_clean(section.conclusion) for section in sections if _clean(section.conclusion)]


def _metric_lines(response: TopicResponse, labels: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for metric in response.key_metrics:
        as_of = _clean(getattr(metric, "as_of", None)) or labels["unknown_as_of"]
        source = _clean(getattr(metric, "source", None)) or "unknown"
        unit = f" {metric.unit}" if getattr(metric, "unit", "") else ""
        context = f" ({metric.context})" if metric.context else ""
        lines.append(f"{metric.name}: {metric.value}{unit} [{labels['as_of']}: {as_of}; {labels['source']}: {source}]{context}")
    if lines:
        return lines
    if response.uncertainty:
        return [f"{labels['uncertainty']}: {response.uncertainty}"]
    return [labels["none"]]


def _pricing_reality_lines(response: TopicResponse, labels: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for section in response.rate_structure + response.investment_judgment:
        conclusion = _clean(getattr(section, "conclusion", ""))
        if conclusion:
            lines.append(conclusion)
    for scenario in response.scenario_analysis[:2]:
        read = _clean(getattr(scenario, "decision_read", ""))
        implication = _clean(getattr(scenario, "asset_implication", ""))
        if read or implication:
            lines.append(f"{scenario.scenario}: {read or implication}")
    if not lines and response.key_metrics:
        names = ", ".join(_clean(metric.name) for metric in response.key_metrics[:4] if _clean(metric.name))
        if names:
            lines.append(f"{labels['quant_snapshot']}의 {names} 지표를 가격 판단의 기준점으로 사용했습니다.")
    if response.uncertainty:
        lines.append(f"{labels['uncertainty']}: {response.uncertainty}")
    return _dedupe_texts(lines) or [labels["none"]]


def build_topic_report(response: TopicResponse, language: str = "ko") -> tuple[str, str]:
    labels = _asset_labels(response, _labels(language))
    none = labels["none"]
    evidence_lookup = _evidence_lookup(response)
    drivers = _md_bullets([item.text for item in response.key_drivers], none)
    risks = _md_bullets([item.text for item in response.key_risks], none)
    tickers = _md_bullets([f"**{t.ticker}** ({t.role}): {t.rationale}" for t in response.related_tickers], none)
    metrics = _md_bullets(_metric_lines(response, labels), none)
    pricing_reality = _md_bullets(_pricing_reality_lines(response, labels), none)
    open_questions = _md_bullets(response.open_questions, none)
    citations = _md_bullets([f"**{c.source}** | {c.date} | {c.title}" for c in response.citations], none)
    evidence = "\n".join(
        f"{idx}. **{item.source}** | {item.date} | {item.title} | `{item.metadata.get('parent_doc_id') or item.metadata.get('doc_id', f'doc-{idx}')}`"
        for idx, item in enumerate(response.raw_context, start=1)
    ) or f"1. {labels['no_context']}"
    synthesis_lines = _dedupe_texts([response.core_thesis, *_section_conclusions(response.investment_judgment)])
    conclusion_lines = _dedupe_texts(_section_conclusions(response.investment_judgment) or [response.core_thesis])
    if response.uncertainty:
        conclusion_lines.append(f"{labels['uncertainty']}: {response.uncertainty}")
    decision = response.decision_view
    quality = response.quality_metrics
    confidence = response.confidence_rationale
    decision_quality_md = f"""## Decision View
- **Rating**: `{decision.rating}`
- **Time horizon**: `{decision.time_horizon}`
- **Confidence**: {decision.confidence:.2f}
- **Decision summary**: {decision.decision_summary or none}
- **Primary thesis**: {decision.primary_thesis or none}
- **What would change this view**: {', '.join(decision.what_would_change_my_view) if decision.what_would_change_my_view else none}

## Confidence / Quality Audit
| Metric | Value |
| --- | --- |
| Claim support rate | {quality.claim_support_rate:.2f} |
| Numeric grounding rate | {quality.numeric_grounding_rate:.2f} |
| Evidence quality average | {quality.evidence_quality_average:.2f} |
| Freshness coverage | {quality.freshness_coverage:.2f} |
| Stale context rate | {quality.stale_context_rate:.2f} |
| Source diversity | {quality.source_diversity} |
| Required bucket coverage | {quality.required_bucket_coverage:.2f} |
| Confidence caps | {', '.join(confidence.caps_applied) if confidence.caps_applied else none} |
"""

    md = f"""# {labels['title']}: {response.theme}

## {labels['question']}
{response.question}

## {labels['summary']}
{response.executive_summary}

{decision_quality_md}

## {labels['quant_snapshot']}
{metrics}

## {labels['core_analysis']}
### (1) {labels['asset_overview']}
{_section_md(response.asset_overview, labels, evidence_lookup)}

### (2) {labels['macro_regime']}
{_section_md(response.macro_regime, labels, evidence_lookup)}

### (3) {labels['rate_structure']}
{_section_md(response.rate_structure, labels, evidence_lookup)}

### (4) {labels['scenario_analysis']}
{_scenario_md(response.scenario_analysis, labels, evidence_lookup)}

### (5) {labels['risk_factors']}
{risks}

### (6) {labels['execution']}
{_execution_md(response.execution_strategy, labels, evidence_lookup)}

### (7) {labels['pricing_reality']}
{pricing_reality}

## {labels['synthesis']}
{_md_bullets(synthesis_lines, none)}

## {labels['decision_edge']}
### {labels['drivers']}
{drivers}

### {labels['risks']}
{risks}

### {labels['touchpoints']}
{tickers}

### {labels['open_questions']}
{open_questions}

## {labels['conclusion']}
{_md_bullets(conclusion_lines, none)}

## {labels['citations']}
{citations}

{scenario_simulation_md(response)}
## {labels['evidence']}
{evidence}
"""

    metric_html = _html_list(_metric_lines(response, labels), none)
    pricing_html = _html_list(_pricing_reality_lines(response, labels), none)
    driver_html = _html_list([d.text for d in response.key_drivers], none)
    risk_html = _html_list([r.text for r in response.key_risks], none)
    ticker_html = _html_list([f"{t.ticker} ({t.role}): {t.rationale}" for t in response.related_tickers], none)
    open_html = _html_list(response.open_questions, none)
    citation_html = _html_list([f"{c.source} | {c.date} | {c.title}" for c in response.citations], none)
    evidence_html = "".join(
        f"<li><strong>{escape(item.source)}</strong> | {escape(item.date)} | {escape(item.title)}</li>"
        for item in response.raw_context
    ) or f"<li>{escape(labels['no_context'])}</li>"
    decision_quality_html = f"""
      <h2>Decision View</h2>
      <ul>
        <li><strong>Rating</strong>: <code>{escape(decision.rating)}</code></li>
        <li><strong>Time horizon</strong>: <code>{escape(decision.time_horizon)}</code></li>
        <li><strong>Confidence</strong>: {decision.confidence:.2f}</li>
        <li><strong>Decision summary</strong>: {escape(decision.decision_summary or none)}</li>
        <li><strong>Primary thesis</strong>: {escape(decision.primary_thesis or none)}</li>
      </ul>
      <h2>Confidence / Quality Audit</h2>
      <table style="border-collapse:collapse;width:100%;margin:8px 0 18px;">
        <tbody>
          <tr><th>Claim support rate</th><td>{quality.claim_support_rate:.2f}</td></tr>
          <tr><th>Numeric grounding rate</th><td>{quality.numeric_grounding_rate:.2f}</td></tr>
          <tr><th>Evidence quality average</th><td>{quality.evidence_quality_average:.2f}</td></tr>
          <tr><th>Freshness coverage</th><td>{quality.freshness_coverage:.2f}</td></tr>
          <tr><th>Stale context rate</th><td>{quality.stale_context_rate:.2f}</td></tr>
          <tr><th>Source diversity</th><td>{quality.source_diversity}</td></tr>
          <tr><th>Required bucket coverage</th><td>{quality.required_bucket_coverage:.2f}</td></tr>
        </tbody>
      </table>
    """

    html = f"""
    <html>
    <head><title>{escape(labels['title'])}: {escape(response.theme)}</title></head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; max-width: 960px; margin: auto; padding: 2rem;">
      <h1>{escape(labels['title'])}: {escape(response.theme)}</h1>
      <h2>{escape(labels['question'])}</h2><p>{escape(response.question)}</p>
      <h2>{escape(labels['summary'])}</h2><p>{escape(response.executive_summary)}</p>
      {decision_quality_html}
      <h2>{escape(labels['quant_snapshot'])}</h2>{metric_html}
      <h2>{escape(labels['core_analysis'])}</h2>
      <h3>(1) {escape(labels['asset_overview'])}</h3>{_section_html(response.asset_overview, labels, evidence_lookup)}
      <h3>(2) {escape(labels['macro_regime'])}</h3>{_section_html(response.macro_regime, labels, evidence_lookup)}
      <h3>(3) {escape(labels['rate_structure'])}</h3>{_section_html(response.rate_structure, labels, evidence_lookup)}
      <h3>(4) {escape(labels['scenario_analysis'])}</h3>{_scenario_html(response.scenario_analysis, labels, evidence_lookup)}
      <h3>(5) {escape(labels['risk_factors'])}</h3>{risk_html}
      <h3>(6) {escape(labels['execution'])}</h3>{_execution_html(response.execution_strategy, labels, evidence_lookup)}
      <h3>(7) {escape(labels['pricing_reality'])}</h3>{pricing_html}
      <h2>{escape(labels['synthesis'])}</h2>{_html_list(synthesis_lines, none)}
      <h2>{escape(labels['decision_edge'])}</h2>
      <h3>{escape(labels['drivers'])}</h3>{driver_html}
      <h3>{escape(labels['risks'])}</h3>{risk_html}
      <h3>{escape(labels['touchpoints'])}</h3>{ticker_html}
      <h3>{escape(labels['open_questions'])}</h3>{open_html}
      <h2>{escape(labels['conclusion'])}</h2>{_html_list(conclusion_lines, none)}
      {scenario_simulation_html(response)}
      <h2>{escape(labels['citations'])}</h2>{citation_html}
      <h2>{escape(labels['evidence'])}</h2><ol>{evidence_html}</ol>
    </body>
    </html>
    """
    return md, html
