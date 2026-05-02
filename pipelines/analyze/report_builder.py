from html import escape
from typing import Sequence, Tuple

from core.schemas.request import AnalysisRequest
from core.schemas.response import AnalysisResponse, CatalystTimeline, KeyMetric


def build_report(request: AnalysisRequest, response: AnalysisResponse, language: str = "ko") -> Tuple[str, str]:
    """Build decision-grade Markdown and HTML reports for single-name analysis."""

    strings = _labels(language)
    sentiment = response.sentiment or "Neutral"
    sentiment_label = strings["sentiments"].get(sentiment, sentiment)
    return _build_markdown(response, strings), _build_html(response, strings, sentiment_label)


def _labels(language: str) -> dict:
    lang = str(language or "ko").strip().lower()
    if lang == "ko":
        return {
            "title": "투자 리서치 보고서",
            "request": "분석 요청",
            "question": "질문",
            "status": "상태",
            "sentiment": "판단 톤",
            "confidence": "신뢰도",
            "summary_heading": "요약",
            "core_heading": "핵심 분석",
            "macro_context": "거시 환경",
            "business_drivers": "사업 및 매출 동인",
            "cost_margin": "비용 구조 및 마진",
            "ai_competition": "AI 전략 및 경쟁 포지션",
            "risk_factors": "리스크 요인",
            "catalysts": "촉매 요인 (단기 / 중기)",
            "pricing_reality": "시장 가격 vs 현실",
            "synthesis": "Synthesis (핵심 판단 구간)",
            "decision_edge": "Decision Edge / 투자 판단 체크리스트",
            "conclusion_heading": "결론",
            "investment_checklist": "투자 판단 체크리스트",
            "check_item": "항목",
            "check_value": "내용",
            "field": "항목",
            "value": "값",
            "citations_label": "개 인용",
            "context_chunks_label": "개 근거 청크",
            "decision_bias": "판단 방향",
            "evidence_quality": "근거 품질",
            "quant_anchors": "정량 앵커",
            "upside_monitor": "상방 확인 요인",
            "downside_monitor": "하방 방어선",
            "next_research": "다음 확인 사항",
            "snapshot": "기업 스냅샷",
            "metrics": "핵심 지표",
            "metric_name": "지표",
            "metric_value": "값",
            "metric_as_of": "기준일",
            "metric_context": "맥락",
            "near_term": "단기 (0~3개월)",
            "mid_term": "중기 (3~12개월)",
            "long_term": "장기 (12개월+)",
            "uncertainty": "잔여 불확실성",
            "open_questions": "추가 확인 질문",
            "conclusion": "결론 및 투자 의견",
            "investment_stance": "투자 의견",
            "view_change": "판단 변경 조건",
            "additional_evidence_required": "추가 근거 확인 필요",
            "evidence": "전체 근거 자료",
            "key_evidence": "핵심 근거",
            "run_status": "실행 상태",
            "note": "운영 참고사항",
            "degraded": "일부 데이터 부족으로 분석 신뢰도가 제한됩니다.",
            "none": "식별된 항목 없음",
            "no_context": "수집된 문맥 없음",
            "no_metrics": "정량 근거가 추출되지 않았습니다.",
            "no_questions": "추가 조사 항목 없음",
            "quality_high": "높음",
            "quality_medium": "보통",
            "quality_limited": "제한적",
            "evidence_label": "근거",
            "bullish": "상승",
            "bearish": "하락",
            "current_read": "현재 판단",
            "upside": "상방",
            "downside": "하방",
            "sentiments": {
                "Positive": "긍정적",
                "positive": "긍정적",
                "Negative": "부정적",
                "negative": "부정적",
                "Neutral": "중립",
                "neutral": "중립",
                "Mixed": "혼재",
                "mixed": "혼재",
            },
        }
    return {
        "title": "Financial Research Report",
        "request": "Request",
        "question": "Question",
        "status": "Status",
        "sentiment": "Sentiment",
        "confidence": "Confidence",
        "summary_heading": "Summary",
        "core_heading": "Core Analysis",
        "macro_context": "Macro Context",
        "business_drivers": "Business & Revenue Drivers",
        "cost_margin": "Cost Structure & Margin Dynamics",
        "ai_competition": "AI Strategy & Competitive Positioning",
        "risk_factors": "Risk Factors",
        "catalysts": "Catalysts (Near / Mid Term)",
        "pricing_reality": "Market Pricing vs Reality",
        "synthesis": "Synthesis",
        "decision_edge": "Decision Edge / Investment Decision Checklist",
        "conclusion_heading": "Conclusion",
        "investment_checklist": "Investment Decision Checklist",
        "check_item": "Item",
        "check_value": "Detail",
        "field": "Field",
        "value": "Value",
        "citations_label": "citations",
        "context_chunks_label": "context chunks",
        "decision_bias": "Decision bias",
        "evidence_quality": "Evidence quality",
        "quant_anchors": "Quantitative anchors",
        "upside_monitor": "Upside monitor",
        "downside_monitor": "Downside guardrail",
        "next_research": "Next research",
        "snapshot": "Company Snapshot",
        "metrics": "Key Metrics",
        "metric_name": "Metric",
        "metric_value": "Value",
        "metric_as_of": "As of",
        "metric_context": "Context",
        "near_term": "Near term (0-3 months)",
        "mid_term": "Mid term (3-12 months)",
        "long_term": "Long term (12 months+)",
        "uncertainty": "Residual Uncertainty",
        "open_questions": "Open Questions",
        "conclusion": "Conclusion",
        "investment_stance": "Investment stance",
        "view_change": "View-change factor",
        "additional_evidence_required": "additional evidence required",
        "evidence": "Evidence Base",
        "key_evidence": "Key Thesis Evidence",
        "run_status": "Run Status",
        "note": "Operator Note",
        "degraded": "Execution completed with degraded evidence.",
        "none": "None identified",
        "no_context": "No context retrieved",
        "no_metrics": "No quantitative evidence was extracted.",
        "no_questions": "No outstanding follow-ups flagged.",
        "quality_high": "High",
        "quality_medium": "Medium",
        "quality_limited": "Limited",
        "evidence_label": "evidence",
        "bullish": "Bullish",
        "bearish": "Bearish",
        "current_read": "Current read",
        "upside": "Upside",
        "downside": "Downside",
        "sentiments": {
            "Positive": "Positive",
            "positive": "Positive",
            "Negative": "Negative",
            "negative": "Negative",
            "Neutral": "Neutral",
            "neutral": "Neutral",
            "Mixed": "Mixed",
            "mixed": "Mixed",
        },
    }


def _is_english(strings: dict) -> bool:
    return strings.get("request") == "Request"


def _txt(strings: dict, ko: str, en: str) -> str:
    return en if _is_english(strings) else ko


def _clean_sentence(value: object) -> str:
    return " ".join(str(value or "").split()).strip(" -")


def _dedupe_sentence_key(value: object) -> str:
    text = _clean_sentence(value).lower()
    return "".join(ch for ch in text if ch.isalnum() or "\uac00" <= ch <= "\ud7a3")


def _dedupe_sentences(items: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        clean = _clean_sentence(item)
        if not clean:
            continue
        key = _dedupe_sentence_key(clean)
        if key and key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = str(text or "").lower()
    return any(term.lower() in lowered for term in terms)


def _format_evidence_suffix(ids: Sequence[str], label: str) -> str:
    if not ids:
        return ""
    return f"  \n  _{label}_: " + ", ".join(f"`{x}`" for x in ids)


def _bullet_list_md(points: Sequence[str], evidence: Sequence[Sequence[str]], strings: dict) -> str:
    if not points:
        return f"- {strings['none']}"
    lines: list[str] = []
    evidence = evidence or []
    for i, text in enumerate(points):
        ids = evidence[i] if i < len(evidence) else []
        lines.append(f"- {_clean_sentence(text)}{_format_evidence_suffix(ids, strings['evidence_label'])}")
    return "\n".join(lines)


def _bullet_block(items: Sequence[str], empty: str) -> str:
    cleaned = _dedupe_sentences(items)
    return "\n".join(f"- {item}" for item in cleaned) if cleaned else f"- {empty}"


def _compact_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    value = float(value)
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.2f}"


def _num(value: float | None, digits: int = 2) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{float(value) * 100:.2f}%"


def _as_of_suffix(value: object, strings: dict) -> str:
    as_of = _clean_sentence(value)
    if not as_of:
        return ""
    return f" ({_txt(strings, '기준일', 'as of')} {as_of})"


def _metric_anchor_text(metrics: Sequence[KeyMetric], strings: dict) -> str:
    anchors = []
    for metric in list(metrics or [])[:3]:
        name = _clean_sentence(metric.name)
        value = _clean_sentence(metric.value)
        as_of = _clean_sentence(getattr(metric, "as_of", None))
        if name and value:
            anchors.append(f"{name}: {value}{_as_of_suffix(as_of, strings)}")
    return "; ".join(anchors) if anchors else strings["no_metrics"]


def _metrics_table_md(metrics: Sequence[KeyMetric], strings: dict) -> str:
    if not metrics:
        return f"_{strings['no_metrics']}_"
    as_of_label = strings.get("metric_as_of") or _txt(strings, "기준일", "As of")
    unknown_as_of = _txt(strings, "기준일 미확인", "unknown")
    header = f"| {strings['metric_name']} | {strings['metric_value']} | Unit | {as_of_label} | Source | Grounding | {strings['metric_context']} |"
    sep = "| --- | --- | --- | --- | --- | --- | --- |"
    rows = []
    for metric in metrics:
        name = _clean_sentence(metric.name).replace("|", "\\|")
        value = _clean_sentence(metric.value).replace("|", "\\|")
        unit = _clean_sentence(getattr(metric, "unit", "")).replace("|", "\\|") or "-"
        as_of = (_clean_sentence(getattr(metric, "as_of", None)) or unknown_as_of).replace("|", "\\|")
        source = (_clean_sentence(getattr(metric, "source", "")) or "unknown").replace("|", "\\|")
        grounding = (_clean_sentence(getattr(metric, "grounding_status", "")) or "unknown").replace("|", "\\|")
        context_text = _clean_sentence(metric.context).replace("|", "\\|") or "-"
        if metric.evidence_doc_ids:
            ids = ", ".join(f"`{x}`" for x in metric.evidence_doc_ids)
            context_text = f"{context_text} ({ids})"
        rows.append(f"| {name} | {value} | {unit} | {as_of} | {source} | {grounding} | {context_text} |")
    return "\n".join([header, sep, *rows])


def _escape_md_cell(value: object) -> str:
    return _clean_sentence(value).replace("|", "\\|")


def _evidence_quality(response: AnalysisResponse, strings: dict) -> str:
    raw_count = len(response.raw_context or [])
    citation_count = len(response.citations or [])
    if response.status != "success" or raw_count < 2:
        return strings["quality_limited"]
    if citation_count >= 2 and raw_count >= 3:
        return strings["quality_high"]
    return strings["quality_medium"]


def _first_or_default(items: Sequence[str], default: str) -> str:
    for item in items or []:
        text = _clean_sentence(item)
        if text:
            return text
    return default


def _bias(response: AnalysisResponse, strings: dict) -> tuple[str, str]:
    sentiment = str(response.sentiment or "Neutral").lower()
    bull_count = len(response.bull_points or [])
    bear_count = len(response.bear_points or [])
    if sentiment in {"positive", "bullish"} or bull_count >= bear_count + 2:
        return "Bullish", strings["bullish"]
    if sentiment in {"negative", "bearish"} or bear_count >= bull_count + 2:
        return "Bearish", strings["bearish"]
    return "Neutral", _txt(strings, "중립", "Neutral")


def _stance_action(response: AnalysisResponse, strings: dict) -> str:
    bias_key, _ = _bias(response, strings)
    if bias_key == "Bullish":
        return _txt(
            strings,
            "분할 매수 또는 기존 비중 확대가 가능하지만, 핵심 리스크 트리거가 악화되면 속도를 낮춰야 합니다.",
            "Accumulate selectively, with position sizing tied to the main risk trigger.",
        )
    if bias_key == "Bearish":
        return _txt(
            strings,
            "신규 진입은 보수적으로 보고, 반전 촉매가 확인되기 전까지 회피 또는 축소가 합리적입니다.",
            "Avoid or reduce until the main reversal catalyst is evidenced.",
        )
    return _txt(
        strings,
        "공격적인 추가 매수보다 관망 또는 보유가 적절하며, 다음 촉매 확인 후 판단을 갱신해야 합니다.",
        "Hold or watch rather than add aggressively until the next catalyst resolves the setup.",
    )


def _investment_checklist_rows(response: AnalysisResponse, strings: dict) -> list[tuple[str, str]]:
    sentiment = response.sentiment or "Neutral"
    sentiment_label = strings["sentiments"].get(sentiment, sentiment)
    next_research = _first_or_default(
        response.open_questions,
        _clean_sentence(response.uncertainty) or strings["no_questions"],
    )
    return [
        (strings["decision_bias"], f"{sentiment_label} / {strings['confidence']} {response.confidence:.2f}"),
        (
            strings["evidence_quality"],
            (
                f"{_evidence_quality(response, strings)} "
                f"({len(response.citations or [])} {strings['citations_label']}, "
                f"{len(response.raw_context or [])} {strings['context_chunks_label']})"
            ),
        ),
        (strings["quant_anchors"], _metric_anchor_text(response.key_metrics, strings)),
        (strings["upside_monitor"], _first_or_default(response.bull_points, strings["none"])),
        (strings["downside_monitor"], _first_or_default(response.bear_points, strings["none"])),
        (strings["next_research"], next_research),
    ]


def _investment_checklist_md(response: AnalysisResponse, strings: dict) -> str:
    rows = []
    for label, value in _investment_checklist_rows(response, strings):
        rows.append(f"| {_escape_md_cell(label)} | {_escape_md_cell(value)} |")
    return (
        f"| {strings['check_item']} | {strings['check_value']} |\n"
        "| --- | --- |\n"
        + "\n".join(rows)
    )


def _decision_sections_md(response: AnalysisResponse, strings: dict) -> str:
    decision = response.decision_view
    scenarios = response.scenario_analysis
    monitoring = response.monitoring_plan
    risk = response.risk_management
    confidence = response.confidence_rationale
    quality = response.quality_metrics

    def bullets(items: Sequence[str], empty: str) -> str:
        return _bullet_block([_clean_sentence(x) for x in items], empty)

    def scenario_row(label: str, case) -> str:
        drivers = "; ".join(_dedupe_sentences(case.drivers)) or strings["none"]
        risks = "; ".join(_dedupe_sentences(case.risks)) or strings["none"]
        evidence = ", ".join(f"`{x}`" for x in case.evidence_doc_ids) or strings["none"]
        return (
            f"| {label} | {case.probability:.2f} | {_escape_md_cell(case.thesis)} | "
            f"{_escape_md_cell(drivers)} | {_escape_md_cell(risks)} | {evidence} |"
        )

    scenario_table = "\n".join(
        [
            "| Scenario | Probability | Thesis | Drivers | Risks | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
            scenario_row("Base", scenarios.base_case),
            scenario_row("Bull", scenarios.bull_case),
            scenario_row("Bear", scenarios.bear_case),
        ]
    )
    caps = confidence.caps_applied or [_txt(strings, "적용된 신뢰도 캡 없음", "No confidence caps applied")]
    warnings = response.warnings or [_txt(strings, "경고 없음", "No warnings")]
    return f"""## Decision View
- **Rating**: `{decision.rating}`
- **Time horizon**: `{decision.time_horizon}`
- **Confidence**: {decision.confidence:.2f}
- **Decision summary**: {decision.decision_summary or strings['none']}
- **Primary thesis**: {decision.primary_thesis or strings['none']}

### What Would Change This View
{bullets(decision.what_would_change_my_view, strings['none'])}

## Scenario Analysis
{scenario_table}

## Monitoring Plan
- **Next events**
{bullets(monitoring.next_events, strings['none'])}
- **Key indicators**
{bullets(monitoring.key_indicators, strings['none'])}
- **Alert conditions**
{bullets(monitoring.alert_conditions, strings['none'])}
- **Review cadence**: {monitoring.review_cadence or strings['none']}

## Risk Management
- **Risk level**: `{risk.risk_level}`
- **Main risks**
{bullets(risk.main_risks, strings['none'])}
- **Invalidating conditions**
{bullets(risk.invalidating_conditions, strings['none'])}
- **Position sizing**: {risk.position_sizing_comment or strings['none']}

## Confidence Rationale
| Metric | Value |
| --- | --- |
| Claim support rate | {quality.claim_support_rate:.2f} |
| Numeric grounding rate | {quality.numeric_grounding_rate:.2f} |
| Evidence quality average | {quality.evidence_quality_average:.2f} |
| Freshness coverage | {quality.freshness_coverage:.2f} |
| Stale context rate | {quality.stale_context_rate:.2f} |
| Source diversity | {quality.source_diversity} |
| Required bucket coverage | {quality.required_bucket_coverage:.2f} |

### Confidence Caps / Warnings
{bullets(caps + warnings, strings['none'])}
"""


def _snapshot_rows(response: AnalysisResponse, strings: dict) -> list[tuple[str, str]]:
    card = response.fundamentals
    if card is None:
        return []
    labels = (
        {
            "name": "이름",
            "sector": "섹터 / 산업",
            "market": "시가총액 / 가격",
            "range": "52주 범위",
            "valuation": "밸류에이션",
            "growth": "성장 / 마진",
            "yield": "배당 / 베타",
            "analyst": "애널리스트",
            "asof": "기준일 / 출처",
        }
        if not _is_english(strings)
        else {
            "name": "Name",
            "sector": "Sector / Industry",
            "market": "Market Cap / Price",
            "range": "52 Week Range",
            "valuation": "Valuation",
            "growth": "Growth / Margin",
            "yield": "Yield / Beta",
            "analyst": "Analyst",
            "asof": "As Of / Source",
        }
    )
    return [
        (labels["name"], f"{card.name or card.ticker} ({card.ticker})"),
        (labels["sector"], f"{card.sector or 'N/A'} / {card.industry or 'N/A'}"),
        (labels["market"], f"{_compact_money(card.market_cap)} / {_compact_money(card.price)}"),
        (labels["range"], f"{_compact_money(card.week52_low)} - {_compact_money(card.week52_high)}"),
        (labels["valuation"], f"TTM P/E {_num(card.trailing_pe, 1)} | Fwd P/E {_num(card.forward_pe, 1)} | P/B {_num(card.price_to_book, 1)}"),
        (labels["growth"], f"Revenue {_pct(card.revenue_growth)} | EPS {_pct(card.earnings_growth)} | Profit {_pct(card.profit_margin)}"),
        (labels["yield"], f"Dividend {_pct(card.dividend_yield)} | Beta {_num(card.beta, 2)}"),
        (labels["analyst"], f"Target {_compact_money(card.analyst_target_mean)} | Rating {_num(card.analyst_rating_mean, 1)} | Count {card.num_analysts if card.num_analysts is not None else 'N/A'}"),
        (labels["asof"], f"{card.as_of} / {card.source}"),
    ]


def _snapshot_table_md(response: AnalysisResponse, strings: dict) -> str:
    rows = _snapshot_rows(response, strings)
    if not rows:
        return ""
    rendered_rows = [f"| {_escape_md_cell(label)} | {_escape_md_cell(value)} |" for label, value in rows]
    return f"## {strings['snapshot']}\n| {strings['field']} | {strings['value']} |\n| --- | --- |\n" + "\n".join(rendered_rows) + "\n\n"


def _point_candidates(response: AnalysisResponse) -> list[str]:
    items: list[str] = []
    items.extend([str(x) for x in response.bull_points or [] if str(x).strip()])
    items.extend([str(x) for x in response.bear_points or [] if str(x).strip()])
    timeline = response.catalyst_timeline or CatalystTimeline()
    for item in timeline.near_term + timeline.mid_term + timeline.long_term:
        if str(item).strip():
            items.append(str(item))
    for metric in response.key_metrics or []:
        as_of = _clean_sentence(getattr(metric, "as_of", None))
        metric_text = f"{metric.name}: {metric.value}{f' as of {as_of}' if as_of else ''} - {metric.context}".strip()
        if metric_text:
            items.append(metric_text)
    if response.uncertainty:
        items.append(response.uncertainty)
    if response.conclusion:
        items.append(response.conclusion)
    return items


def _select_points(response: AnalysisResponse, terms: Sequence[str], limit: int = 3) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for item in _point_candidates(response):
        cleaned = _clean_sentence(item)
        key = cleaned.lower()
        if cleaned and key not in seen and _contains_any(cleaned, terms):
            selected.append(cleaned)
            seen.add(key)
        if len(selected) >= limit:
            break
    return selected


def _metric_line(response: AnalysisResponse, terms: Sequence[str], strings: dict) -> str | None:
    for metric in response.key_metrics or []:
        text = f"{metric.name} {metric.context}"
        if _contains_any(text, terms):
            as_of = _clean_sentence(getattr(metric, "as_of", None))
            as_of_suffix = f"; {_txt(strings, '기준일', 'as of')} {as_of}" if as_of else ""
            return f"{metric.name}: {metric.value}{as_of_suffix}{f' ({metric.context})' if metric.context else ''}"
    return None


def _macro_context(response: AnalysisResponse, strings: dict) -> list[str]:
    terms = ("rate", "rates", "fed", "inflation", "liquidity", "yield", "macro", "interest", "금리", "연준", "인플레이션", "유동성", "거시")
    items = _select_points(response, terms, 3)
    card = response.fundamentals
    if card is not None and card.beta is not None:
        beta_read = _txt(strings, "시장 민감도가 낮은 편", "market beta is low") if float(card.beta) < 0.9 else _txt(strings, "시장 민감도가 높은 편", "market beta is high")
        items.insert(
            0,
            _txt(
                strings,
                f"Beta {card.beta:.2f}{_as_of_suffix(card.as_of, strings)} 기준 {beta_read}이므로 금리와 유동성 변화가 멀티플에 반영될 가능성을 함께 봐야 합니다.",
                f"Beta {card.beta:.2f}{_as_of_suffix(card.as_of, strings)} suggests {beta_read}; rate and liquidity shifts should be mapped to multiple risk.",
            ),
        )
    if not items:
        items.append(_txt(strings, "현재 근거만으로 금리, 유동성, 인플레이션 민감도를 직접 단정하기 어렵습니다. 거시 변수는 추가 확인 항목입니다.", "The retrieved evidence gives limited direct support on rate, liquidity, or inflation sensitivity; treat this as a diligence gap."))
    return items[:3]


def _business_drivers(response: AnalysisResponse, strings: dict) -> list[str]:
    items: list[str] = []
    card = response.fundamentals
    if card is not None and card.revenue_growth is not None:
        items.append(_txt(strings, f"최근 매출 성장률 {card.revenue_growth * 100:.2f}%{_as_of_suffix(card.as_of, strings)}는 성장 지속성을 판단하는 첫 정량 앵커입니다.", f"Revenue growth of {card.revenue_growth * 100:.2f}%{_as_of_suffix(card.as_of, strings)} is the first quantitative anchor for growth durability."))
    items.extend([_clean_sentence(p) for p in (response.bull_points or [])[:3] if _clean_sentence(p)])
    if not items:
        items.append(_txt(strings, "수익원과 세그먼트별 성장 동인은 현재 근거만으로 충분히 분해되지 않았습니다.", "Revenue streams and segment-level growth drivers are not sufficiently decomposed by the current evidence."))
    return items[:4]


def _cost_margin_points(response: AnalysisResponse, strings: dict) -> list[str]:
    terms = ("cost", "capex", "margin", "opex", "hiring", "restructuring", "expense", "비용", "자본지출", "마진", "고용", "구조조정")
    items = _select_points(response, terms, 3)
    card = response.fundamentals
    if card is not None and card.profit_margin is not None:
        items.insert(0, _txt(strings, f"Profit margin {card.profit_margin * 100:.2f}%{_as_of_suffix(card.as_of, strings)}는 단기 비용 압박과 장기 영업 레버리지를 비교하는 기준선입니다.", f"Profit margin of {card.profit_margin * 100:.2f}%{_as_of_suffix(card.as_of, strings)} is the baseline for near-term cost pressure versus long-term operating leverage."))
    if not items:
        items.append(_txt(strings, "현재 근거에서 비용 구조와 마진 변화가 직접 확인되지 않았습니다. 다음 실적에서 capex, opex, gross margin 확인이 필요합니다.", "The current evidence does not directly explain cost structure or margin change; capex, opex, and gross margin are the next key checks."))
    return items[:3]


def _ai_competition_points(response: AnalysisResponse, strings: dict) -> list[str]:
    terms = ("ai", "cloud", "gpu", "copilot", "openai", "google", "amazon", "aws", "azure", "nvidia", "meta", "competition", "competitive", "인공지능", "클라우드", "경쟁", "구글", "아마존", "엔비디아")
    items = _select_points(response, terms, 4)
    if not items:
        items.append(_txt(strings, "현재 근거에서는 AI 전략이나 직접 경쟁 우위가 핵심 투자 변수로 확인되지 않습니다. AI를 강제로 투자 가설에 넣지 않는 편이 안전합니다.", "The evidence does not show AI strategy or direct competitive advantage as a core variable; do not force AI into the thesis."))
    return items[:4]


def _risk_points(response: AnalysisResponse, strings: dict) -> list[str]:
    risks = [_clean_sentence(item) for item in response.bear_points or [] if _clean_sentence(item)]
    card = response.fundamentals
    if len(risks) < 3 and card is not None and (card.trailing_pe is not None or card.forward_pe is not None):
        pe = card.forward_pe if card.forward_pe is not None else card.trailing_pe
        risks.append(_txt(strings, f"밸류에이션 리스크: P/E {pe:.1f}{_as_of_suffix(card.as_of, strings)}를 정당화할 성장 또는 마진 개선이 확인되지 않으면 멀티플 압축이 발생할 수 있습니다.", f"Valuation risk: if growth or margin evidence does not justify P/E of {pe:.1f}{_as_of_suffix(card.as_of, strings)}, multiple compression can drive downside."))
    if len(risks) < 3 and response.uncertainty:
        risks.append(_txt(strings, f"근거 공백 리스크: {response.uncertainty}", f"Evidence-gap risk: {response.uncertainty}"))
    while len(risks) < 3:
        risks.append(_txt(strings, "실적 리스크: 다음 실적에서 매출 성장 또는 마진이 기대를 밑돌면 추정치 하향과 주가 재평가가 동시에 발생할 수 있습니다.", "Earnings risk: if the next print misses growth or margin expectations, estimates and valuation can reset together."))
    return risks[:4]


def _timeline_directional(response: AnalysisResponse, strings: dict, bullish: bool) -> list[str]:
    positive_terms = ("bull", "upside", "growth", "beat", "launch", "approval", "demand", "margin expansion", "상승", "성장", "수요", "개선", "승인", "출시")
    negative_terms = ("bear", "downside", "risk", "miss", "delay", "pressure", "decline", "하락", "리스크", "지연", "압박", "악화", "둔화")
    terms = positive_terms if bullish else negative_terms
    out: list[str] = []
    timeline = response.catalyst_timeline or CatalystTimeline()
    for label, values in (
        (_txt(strings, "단기", "Near"), timeline.near_term),
        (_txt(strings, "중기", "Mid"), timeline.mid_term),
        (_txt(strings, "장기", "Long"), timeline.long_term),
    ):
        for value in values or []:
            text = _clean_sentence(value)
            if not text:
                continue
            directionally_marked = "[Bullish]" in text or "[Bearish]" in text
            if (directionally_marked and (("[Bullish]" in text) == bullish)) or (not directionally_marked and _contains_any(text, terms)):
                out.append(f"{label}: {text}")
    if not out:
        source = response.bull_points if bullish else response.bear_points
        out.extend([_clean_sentence(item) for item in list(source or [])[:2] if _clean_sentence(item)])
    return out


def _pricing_reality(response: AnalysisResponse, strings: dict) -> list[str]:
    items: list[str] = []
    card = response.fundamentals
    if card is not None:
        valuation_bits = []
        if card.trailing_pe is not None:
            valuation_bits.append(f"TTM P/E {card.trailing_pe:.1f}")
        if card.forward_pe is not None:
            valuation_bits.append(f"Fwd P/E {card.forward_pe:.1f}")
        if card.analyst_target_mean is not None and card.price is not None:
            valuation_bits.append(f"target/price {card.analyst_target_mean:.2f}/{card.price:.2f}")
        if valuation_bits:
            items.append(_txt(strings, f"시장은 {'; '.join(valuation_bits)}{_as_of_suffix(card.as_of, strings)}를 통해 성장 지속성과 리스크 보상을 일부 반영하고 있습니다.", f"Market pricing already embeds growth durability and risk compensation through {'; '.join(valuation_bits)}{_as_of_suffix(card.as_of, strings)}."))
    metric = _metric_line(response, ("valuation", "multiple", "target", "price", "밸류에이션", "멀티플", "목표가", "가격"), strings)
    if metric:
        items.append(_txt(strings, f"추가 가격 앵커: {metric}.", f"Additional pricing anchor: {metric}."))
    if response.bull_points and response.bear_points:
        items.append(_txt(strings, "시장이 틀릴 수 있는 지점은 상방 동인이 실적 추정치로 전환되는 속도와 하방 리스크가 마진/멀티플에 반영되는 강도입니다.", "The market may be wrong on the speed at which upside drivers convert into estimates versus the severity of risk transmission into margin or multiple."))
    if not items:
        items.append(_txt(strings, "현재 근거만으로 주가에 이미 반영된 기대와 미반영 기대를 분리하기 어렵습니다. 밸류에이션, 컨센서스, 가격 추세 확인이 필요합니다.", "Current evidence is insufficient to separate priced-in expectations from underappreciated reality; valuation, consensus, and price trend are needed."))
    return items[:3]


def _synthesis_lines(response: AnalysisResponse, strings: dict) -> list[str]:
    _, bias_label = _bias(response, strings)
    support = _clean_sentence(response.bull_points[0]) if response.bull_points else _txt(strings, "명확한 상방 근거는 제한적입니다.", "clear upside evidence is limited.")
    risk = _clean_sentence(response.bear_points[0]) if response.bear_points else _txt(strings, "명확한 하방 근거는 제한적입니다.", "clear downside evidence is limited.")
    return [
        _txt(strings, f"방향성 판단은 {bias_label}입니다.", f"Directional bias is {bias_label}."),
        _txt(strings, f"핵심 지지 근거는 {support}", f"The main support is {support}"),
        _txt(strings, f"핵심 반대 근거는 {risk}", f"The main offset is {risk}"),
        _txt(strings, f"따라서 결론은 신뢰도 {response.confidence:.2f}와 근거 품질을 감안한 조건부 판단입니다.", f"Therefore the conclusion is conditional on confidence {response.confidence:.2f} and evidence quality."),
    ]


def _decision_grade_markdown(response: AnalysisResponse, strings: dict) -> str:
    none = strings["none"]
    first_bull = _clean_sentence(response.bull_points[0]) if response.bull_points else none
    first_bear = _clean_sentence(response.bear_points[0]) if response.bear_points else none
    summary_lines = [_clean_sentence(response.summary), f"{strings['upside']}: {first_bull}", f"{strings['downside']}: {first_bear}", f"{strings['current_read']}: {_bias(response, strings)[1]}"]
    bullish = _timeline_directional(response, strings, bullish=True)
    bearish = _timeline_directional(response, strings, bullish=False)
    conclusion = _stance_action(response, strings)
    view_change_source = response.bear_points[0] if _bias(response, strings)[0] == "Bullish" and response.bear_points else response.bull_points[0] if response.bull_points else response.uncertainty
    view_change = _clean_sentence(view_change_source) or strings["additional_evidence_required"]

    return f"""## {strings['summary_heading']}
{_bullet_block(summary_lines, none)}

## {strings['core_heading']}
### (1) {strings['macro_context']}
{_bullet_block(_macro_context(response, strings), none)}

### (2) {strings['business_drivers']}
{_bullet_block(_business_drivers(response, strings), none)}

### (3) {strings['cost_margin']}
{_bullet_block(_cost_margin_points(response, strings), none)}

### (4) {strings['ai_competition']}
{_bullet_block(_ai_competition_points(response, strings), none)}

### (5) {strings['risk_factors']}
{_bullet_block(_risk_points(response, strings), none)}

### (6) {strings['catalysts']}
**{strings['bullish']}**
{_bullet_block(bullish, none)}

**{strings['bearish']}**
{_bullet_block(bearish, none)}

### (7) {strings['pricing_reality']}
{_bullet_block(_pricing_reality(response, strings), none)}

## {strings['synthesis']}
{_bullet_block(_synthesis_lines(response, strings), none)}

## {strings['decision_edge']}
{_investment_checklist_md(response, strings)}

## {strings['conclusion_heading']}
- {strings['investment_stance']}: {conclusion}
- {strings['view_change']}: {view_change}
"""


def _open_questions_md(questions: Sequence[str], uncertainty: str, strings: dict) -> str:
    parts = []
    if _clean_sentence(uncertainty):
        parts.append(f"> {strings['uncertainty']}: {_clean_sentence(uncertainty)}")
    if questions:
        parts.append("\n".join(f"- {_clean_sentence(q)}" for q in questions if _clean_sentence(q)))
    elif not parts:
        parts.append(f"_{strings['no_questions']}_")
    return "\n\n".join(parts)


def _build_markdown(response: AnalysisResponse, strings: dict) -> str:
    sentiment = response.sentiment or "Neutral"
    sentiment_label = strings["sentiments"].get(sentiment, sentiment)

    status_block = ""
    if response.status != "success":
        status_block = (
            f"> **{strings['run_status']}**: `{response.status}`\n"
            f"> **{strings['note']}**: {response.error_metadata or strings['degraded']}\n\n"
        )

    evidence_lines = []
    for idx, item in enumerate(response.raw_context or [], start=1):
        doc_id = item.metadata.get("parent_doc_id") or item.metadata.get("doc_id", f"doc-{idx}")
        chunk_suffix = ""
        if item.metadata.get("chunk_index") not in (None, "") and item.metadata.get("total_chunks") not in (None, ""):
            chunk_suffix = f" | chunk {item.metadata.get('chunk_index')}/{item.metadata.get('total_chunks')}"
        evidence_lines.append(f"{idx}. **{item.source}** | {item.date} | {item.title} | `{doc_id}`{chunk_suffix}")
    evidence_block = "\n".join(evidence_lines) or f"1. {strings['no_context']}"

    thesis_citation_lines = [f"- **{citation.source}** | {citation.date} | {citation.title}" for citation in (response.citations or [])]
    thesis_citation_block = ""
    if thesis_citation_lines:
        thesis_citation_block = f"## {strings['key_evidence']}\n" + "\n".join(thesis_citation_lines) + "\n\n"

    snapshot_md = _snapshot_table_md(response, strings)

    return f"""# {strings['title']}: {response.ticker}

## {strings['request']}
- **{strings['question']}**: {response.question}
- **{strings['status']}**: `{response.status}`
- **{strings['sentiment']}**: {sentiment_label}
- **{strings['confidence']}**: {response.confidence:.2f}

{status_block}{_decision_grade_markdown(response, strings)}

{_decision_sections_md(response, strings)}

{snapshot_md}## {strings['metrics']} / Evidence Audit
{_metrics_table_md(response.key_metrics, strings)}

## {strings['open_questions']}
{_open_questions_md(response.open_questions, response.uncertainty, strings)}

{thesis_citation_block}## {strings['evidence']}
{evidence_block}
"""


def _evidence_html_chips(ids: Sequence[str]) -> str:
    if not ids:
        return ""
    chips = "".join(
        f'<code style="font-size:11px;background:#eef2ff;border:1px solid #c7d2fe;border-radius:3px;padding:1px 5px;margin-right:4px;">{escape(str(x))}</code>'
        for x in ids
    )
    return f'<div style="margin-top:4px;">{chips}</div>'


def _metrics_table_html(metrics: Sequence[KeyMetric], strings: dict) -> str:
    if not metrics:
        return f"<p><em>{escape(strings['no_metrics'])}</em></p>"
    as_of_label = strings.get("metric_as_of") or _txt(strings, "기준일", "As of")
    unknown_as_of = _txt(strings, "기준일 미확인", "unknown")
    header = (
        f"<tr><th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(strings['metric_name'])}</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(strings['metric_value'])}</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">Unit</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(as_of_label)}</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">Source</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">Grounding</th>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(strings['metric_context'])}</th></tr>"
    )
    rows = []
    for metric in metrics:
        context_text = escape(_clean_sentence(metric.context) or "-")
        if metric.evidence_doc_ids:
            context_text += _evidence_html_chips(metric.evidence_doc_ids)
        rows.append(
            "<tr>"
            f"<td style=\"padding:4px 8px;vertical-align:top;\"><strong>{escape(_clean_sentence(metric.name))}</strong></td>"
            f"<td style=\"padding:4px 8px;vertical-align:top;\">{escape(_clean_sentence(metric.value))}</td>"
            f"<td style=\"padding:4px 8px;vertical-align:top;\">{escape(_clean_sentence(getattr(metric, 'unit', '')) or '-')}</td>"
            f"<td style=\"padding:4px 8px;vertical-align:top;\">{escape(_clean_sentence(getattr(metric, 'as_of', None)) or unknown_as_of)}</td>"
            f"<td style=\"padding:4px 8px;vertical-align:top;\">{escape(_clean_sentence(getattr(metric, 'source', '')) or 'unknown')}</td>"
            f"<td style=\"padding:4px 8px;vertical-align:top;\">{escape(_clean_sentence(getattr(metric, 'grounding_status', '')) or 'unknown')}</td>"
            f"<td style=\"padding:4px 8px;vertical-align:top;\">{context_text}</td>"
            "</tr>"
        )
    return f"<table style=\"border-collapse:collapse;width:100%;margin:8px 0;\"><thead>{header}</thead><tbody>{''.join(rows)}</tbody></table>"


def _investment_checklist_html(response: AnalysisResponse, strings: dict) -> str:
    row_html = "".join(
        "<tr>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;\">{escape(label)}</th>"
        f"<td style=\"padding:4px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;\">{escape(value)}</td>"
        "</tr>"
        for label, value in _investment_checklist_rows(response, strings)
    )
    return f"<table style=\"border-collapse:collapse;width:100%;margin:8px 0 18px;\"><tbody>{row_html}</tbody></table>"


def _decision_sections_html(response: AnalysisResponse, strings: dict) -> str:
    decision = response.decision_view
    scenarios = response.scenario_analysis
    monitoring = response.monitoring_plan
    risk = response.risk_management
    confidence = response.confidence_rationale
    quality = response.quality_metrics

    def scenario_row(label: str, case) -> str:
        drivers = "; ".join(_dedupe_sentences(case.drivers)) or strings["none"]
        risks = "; ".join(_dedupe_sentences(case.risks)) or strings["none"]
        evidence = ", ".join(str(x) for x in case.evidence_doc_ids) or strings["none"]
        return (
            "<tr>"
            f"<td>{escape(label)}</td><td>{case.probability:.2f}</td>"
            f"<td>{escape(_clean_sentence(case.thesis))}</td>"
            f"<td>{escape(drivers)}</td><td>{escape(risks)}</td><td>{escape(evidence)}</td>"
            "</tr>"
        )

    q_rows = [
        ("Claim support rate", f"{quality.claim_support_rate:.2f}"),
        ("Numeric grounding rate", f"{quality.numeric_grounding_rate:.2f}"),
        ("Evidence quality average", f"{quality.evidence_quality_average:.2f}"),
        ("Freshness coverage", f"{quality.freshness_coverage:.2f}"),
        ("Stale context rate", f"{quality.stale_context_rate:.2f}"),
        ("Source diversity", str(quality.source_diversity)),
        ("Required bucket coverage", f"{quality.required_bucket_coverage:.2f}"),
    ]
    q_html = "".join(
        f"<tr><th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(k)}</th><td style=\"padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(v)}</td></tr>"
        for k, v in q_rows
    )
    caps = confidence.caps_applied or [_txt(strings, "적용된 신뢰도 캡 없음", "No confidence caps applied")]
    warnings = response.warnings or [_txt(strings, "경고 없음", "No warnings")]
    return f"""
        <h2>Decision View</h2>
        <ul>
          <li><strong>Rating</strong>: <code>{escape(decision.rating)}</code></li>
          <li><strong>Time horizon</strong>: <code>{escape(decision.time_horizon)}</code></li>
          <li><strong>Confidence</strong>: {decision.confidence:.2f}</li>
          <li><strong>Decision summary</strong>: {escape(decision.decision_summary or strings['none'])}</li>
          <li><strong>Primary thesis</strong>: {escape(decision.primary_thesis or strings['none'])}</li>
        </ul>
        <h3>What Would Change This View</h3>
        {_plain_list_html(decision.what_would_change_my_view, strings['none'])}
        <h2>Scenario Analysis</h2>
        <table style="border-collapse:collapse;width:100%;margin:8px 0;">
          <thead><tr><th>Scenario</th><th>Probability</th><th>Thesis</th><th>Drivers</th><th>Risks</th><th>Evidence</th></tr></thead>
          <tbody>{scenario_row('Base', scenarios.base_case)}{scenario_row('Bull', scenarios.bull_case)}{scenario_row('Bear', scenarios.bear_case)}</tbody>
        </table>
        <h2>Monitoring Plan</h2>
        <h4>Next events</h4>{_plain_list_html(monitoring.next_events, strings['none'])}
        <h4>Key indicators</h4>{_plain_list_html(monitoring.key_indicators, strings['none'])}
        <h4>Alert conditions</h4>{_plain_list_html(monitoring.alert_conditions, strings['none'])}
        <p><strong>Review cadence</strong>: {escape(monitoring.review_cadence or strings['none'])}</p>
        <h2>Risk Management</h2>
        <p><strong>Risk level</strong>: <code>{escape(risk.risk_level)}</code></p>
        <h4>Main risks</h4>{_plain_list_html(risk.main_risks, strings['none'])}
        <h4>Invalidating conditions</h4>{_plain_list_html(risk.invalidating_conditions, strings['none'])}
        <p><strong>Position sizing</strong>: {escape(risk.position_sizing_comment or strings['none'])}</p>
        <h2>Confidence Rationale</h2>
        <table style="border-collapse:collapse;width:100%;margin:8px 0 18px;"><tbody>{q_html}</tbody></table>
        <h3>Confidence Caps / Warnings</h3>
        {_plain_list_html(caps + warnings, strings['none'])}
    """


def _plain_list_html(items: Sequence[str], empty: str) -> str:
    cleaned = _dedupe_sentences(items)
    if not cleaned:
        return f"<ul><li>{escape(empty)}</li></ul>"
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in cleaned) + "</ul>"


def _snapshot_table_html(response: AnalysisResponse, strings: dict) -> str:
    rows = _snapshot_rows(response, strings)
    if not rows:
        return ""
    row_html = "".join(
        "<tr>"
        f"<th style=\"text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(label)}</th>"
        f"<td style=\"padding:4px 8px;border-bottom:1px solid #e5e7eb;\">{escape(value)}</td>"
        "</tr>"
        for label, value in rows
    )
    return f"<h2>{escape(strings['snapshot'])}</h2><table style=\"border-collapse:collapse;width:100%;margin:8px 0 18px;\"><tbody>{row_html}</tbody></table>"


def _open_questions_html(questions: Sequence[str], uncertainty: str, strings: dict) -> str:
    parts = []
    if _clean_sentence(uncertainty):
        parts.append(
            "<blockquote style=\"border-left:3px solid #f59e0b;margin:8px 0;padding:6px 10px;background:#fffbeb;\">"
            f"<strong>{escape(strings['uncertainty'])}</strong>: {escape(_clean_sentence(uncertainty))}"
            "</blockquote>"
        )
    if questions:
        li = "".join(f"<li>{escape(_clean_sentence(q))}</li>" for q in questions if _clean_sentence(q))
        parts.append(f"<ul>{li}</ul>")
    elif not parts:
        parts.append(f"<p><em>{escape(strings['no_questions'])}</em></p>")
    return "".join(parts)


def _decision_grade_html(response: AnalysisResponse, strings: dict) -> str:
    none = strings["none"]
    first_bull = _clean_sentence(response.bull_points[0]) if response.bull_points else none
    first_bear = _clean_sentence(response.bear_points[0]) if response.bear_points else none
    summary_lines = [_clean_sentence(response.summary), f"{strings['upside']}: {first_bull}", f"{strings['downside']}: {first_bear}", f"{strings['current_read']}: {_bias(response, strings)[1]}"]
    bullish = _timeline_directional(response, strings, bullish=True)
    bearish = _timeline_directional(response, strings, bullish=False)
    conclusion = _stance_action(response, strings)
    view_change_source = response.bear_points[0] if _bias(response, strings)[0] == "Bullish" and response.bear_points else response.bull_points[0] if response.bull_points else response.uncertainty
    view_change = _clean_sentence(view_change_source) or strings["additional_evidence_required"]
    return f"""
        <h2>{escape(strings['summary_heading'])}</h2>
        {_plain_list_html(summary_lines, none)}
        <h2>{escape(strings['core_heading'])}</h2>
        <h3>(1) {escape(strings['macro_context'])}</h3>{_plain_list_html(_macro_context(response, strings), none)}
        <h3>(2) {escape(strings['business_drivers'])}</h3>{_plain_list_html(_business_drivers(response, strings), none)}
        <h3>(3) {escape(strings['cost_margin'])}</h3>{_plain_list_html(_cost_margin_points(response, strings), none)}
        <h3>(4) {escape(strings['ai_competition'])}</h3>{_plain_list_html(_ai_competition_points(response, strings), none)}
        <h3>(5) {escape(strings['risk_factors'])}</h3>{_plain_list_html(_risk_points(response, strings), none)}
        <h3>(6) {escape(strings['catalysts'])}</h3>
        <h4>{escape(strings['bullish'])}</h4>{_plain_list_html(bullish, none)}
        <h4>{escape(strings['bearish'])}</h4>{_plain_list_html(bearish, none)}
        <h3>(7) {escape(strings['pricing_reality'])}</h3>{_plain_list_html(_pricing_reality(response, strings), none)}
        <h2>{escape(strings['synthesis'])}</h2>{_plain_list_html(_synthesis_lines(response, strings), none)}
        <h2>{escape(strings['decision_edge'])}</h2>{_investment_checklist_html(response, strings)}
        <h2>{escape(strings['conclusion_heading'])}</h2>
        <ul>
          <li><strong>{escape(strings['investment_stance'])}</strong>: {escape(conclusion)}</li>
          <li><strong>{escape(strings['view_change'])}</strong>: {escape(view_change)}</li>
        </ul>
    """


def _build_html(response: AnalysisResponse, strings: dict, sentiment_label: str) -> str:
    status_html = ""
    if response.status != "success":
        status_html = (
            "<div style=\"background:#fff4e5;border:1px solid #f0c36d;border-radius:8px;padding:12px 14px;margin:16px 0;\">"
            f"<strong>{escape(strings['run_status'])}</strong>: <code>{escape(response.status)}</code><br>"
            f"<strong>{escape(strings['note'])}</strong>: {escape(response.error_metadata or strings['degraded'])}"
            "</div>"
        )

    evidence_html = "".join(
        [
            (
                f"<li><strong>{escape(item.source)}</strong> | {escape(item.date)} | "
                f"{escape(item.title)} | <code>{escape(item.metadata.get('parent_doc_id') or item.metadata.get('doc_id', f'doc-{idx}'))}</code>"
                f"{' | chunk ' + escape(str(item.metadata.get('chunk_index'))) + '/' + escape(str(item.metadata.get('total_chunks'))) if item.metadata.get('chunk_index') not in (None, '') and item.metadata.get('total_chunks') not in (None, '') else ''}</li>"
            )
            for idx, item in enumerate(response.raw_context or [], start=1)
        ]
    ) or f"<li>{escape(strings['no_context'])}</li>"

    thesis_evidence_html = "".join(
        [f"<li><strong>{escape(citation.source)}</strong> | {escape(citation.date)} | {escape(citation.title)}</li>" for citation in (response.citations or [])]
    )
    thesis_evidence_block = f"<h2>{escape(strings['key_evidence'])}</h2><ul>{thesis_evidence_html}</ul>" if thesis_evidence_html else ""

    return f"""
    <html>
    <head><title>{escape(strings['title'])}: {escape(response.ticker)}</title></head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; max-width: 880px; margin: auto; padding: 2rem;">
        <h1>{escape(strings['title'])}: {escape(response.ticker)}</h1>
        <h2>{escape(strings['request'])}</h2>
        <ul>
            <li><strong>{escape(strings['question'])}</strong>: {escape(response.question)}</li>
            <li><strong>{escape(strings['status'])}</strong>: <code>{escape(response.status)}</code></li>
            <li><strong>{escape(strings['sentiment'])}</strong>: {escape(sentiment_label)}</li>
            <li><strong>{escape(strings['confidence'])}</strong>: {response.confidence:.2f}</li>
        </ul>
        {status_html}
        {_decision_grade_html(response, strings)}
        {_decision_sections_html(response, strings)}
        {_snapshot_table_html(response, strings)}
        <h2>{escape(strings['metrics'])} / Evidence Audit</h2>
        {_metrics_table_html(response.key_metrics, strings)}
        <h2>{escape(strings['open_questions'])}</h2>
        {_open_questions_html(response.open_questions, response.uncertainty, strings)}
        {thesis_evidence_block}
        <h2>{escape(strings['evidence'])}</h2>
        <ol>{evidence_html}</ol>
    </body>
    </html>
    """
