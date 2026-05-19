from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from core.schemas.response import Citation
from core.schemas.retrieval import RetrievalItem

_DOC_REF_PATTERN = re.compile(r"\((?:(?:doc)|(?:document))\s*(\d+)\)", re.IGNORECASE)
_DOC_REF_FALLBACK_PATTERN = re.compile(r"\b(?:(?:doc)|(?:document))\s*(\d+)\b", re.IGNORECASE)
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
_NUMERIC_SIGNAL_PATTERN = re.compile(r"(?:\$?\d+(?:\.\d+)?%?)")

_SIGNIFICANCE_TERMS = {
    "en": ("adoption", "approval", "capex", "competition", "cost", "demand", "debt", "earnings", "execution", "growth", "guidance", "launch", "loss", "margin", "market share", "partnership", "pricing", "profit", "regulatory", "revenue", "tariff", "valuation"),
    "ko": ("채택", "승인", "자본지출", "경쟁", "비용", "수요", "부채", "실적", "집행", "성장", "가이던스", "출시", "손실", "마진", "점유율", "파트너십", "가격", "이익", "규제", "매출", "관세", "밸류에이션")
}
_SO_WHAT_TERMS = {
    "en": ("could", "demand", "driven", "indicating", "offset", "pressure", "risk", "signaling", "suggesting", "upside", "weigh"),
    "ko": ("가능성", "수요", "동인", "시사", "상쇄", "압박", "리스크", "신호", "판단", "상승", "영향")
}
_RISK_TERMS = {
    "en": ("downside", "headwind", "pressure", "risk", "uncertainty", "delay", "decline", "loss", "competition"),
    "ko": ("하락", "역풍", "압박", "리스크", "불확실성", "지연", "감소", "손실", "경쟁")
}
_CATALYST_TERMS = {
    "en": ("adoption", "catalyst", "demand", "growth", "launch", "partnership", "revenue", "upside"),
    "ko": ("채택", "촉매", "수요", "성장", "출시", "파트너십", "매출", "상승")
}
_SHORT_TERM_TERMS = {
    "en": ("days", "earnings", "month", "near-term", "next", "quarter", "upcoming", "weeks"),
    "ko": ("일", "실적", "달", "단기", "다음", "분기", "예정", "주")
}
_MEDIUM_TERM_TERMS = {
    "en": ("12-month", "6-month", "half", "medium-term", "year"),
    "ko": ("12개월", "6개월", "반기", "중기", "년")
}


@dataclass(frozen=True)
class ScoredPoint:
    text: str
    score: int
    doc_refs: tuple[int, ...]
    order: int


@dataclass(frozen=True)
class ThesisResult:
    conclusion: str
    citations: tuple[Citation, ...]


def build_thesis(
    *,
    ticker: str,
    question: str,
    status: str,
    error_metadata: str | None,
    task_type: str,
    horizon: str,
    summary: str,
    bull_points: Sequence[str],
    bear_points: Sequence[str],
    sentiment: str,
    confidence: float,
    uncertainty: str,
    cited_doc_ids: Sequence[str] | str | None,
    raw_context: Sequence[RetrievalItem],
    language: str = "ko",
) -> ThesisResult:
    prepared_bulls = _prepare_points(bull_points, task_type=task_type, horizon=horizon, side="bull", language=language)
    prepared_bears = _prepare_points(bear_points, task_type=task_type, horizon=horizon, side="bear", language=language)

    limited_evidence = _is_limited_evidence(status, raw_context, prepared_bulls, prepared_bears)
    stance = _resolve_stance(sentiment, prepared_bulls, prepared_bears, limited_evidence)
    view_label = _build_view_label(task_type, horizon, language=language)

    selected_points: List[ScoredPoint] = []
    conclusion = _build_conclusion(
        ticker=ticker,
        question=question,
        status=status,
        error_metadata=error_metadata,
        summary=summary,
        uncertainty=uncertainty,
        confidence=confidence,
        stance=stance,
        view_label=view_label,
        limited_evidence=limited_evidence,
        prepared_bulls=prepared_bulls,
        prepared_bears=prepared_bears,
        selected_points=selected_points,
        language=language,
    )
    citations = _build_citations(cited_doc_ids, raw_context, selected_points)
    return ThesisResult(conclusion=conclusion, citations=tuple(citations))


def _prepare_points(points: Sequence[str], *, task_type: str, horizon: str, side: str, language: str) -> list[ScoredPoint]:
    deduped: dict[str, ScoredPoint] = {}
    for order, raw_point in enumerate(points or []):
        cleaned_text, doc_refs = _normalize_point(raw_point)
        if not cleaned_text:
            continue
        score = _score_point(cleaned_text, task_type=task_type, horizon=horizon, side=side, language=language)
        key = _point_key(cleaned_text)
        current = deduped.get(key)
        candidate = ScoredPoint(text=cleaned_text, score=score, doc_refs=tuple(doc_refs), order=order)
        if current is None or (candidate.score, -candidate.order) > (current.score, -current.order):
            deduped[key] = candidate
    return sorted(deduped.values(), key=lambda item: (-item.score, item.order))


def _normalize_point(text: str) -> tuple[str, list[int]]:
    raw = " ".join(str(text or "").split())
    if not raw:
        return "", []

    refs = [int(match.group(1)) for match in _DOC_REF_PATTERN.finditer(raw)]
    if not refs:
        refs = [int(match.group(1)) for match in _DOC_REF_FALLBACK_PATTERN.finditer(raw)]

    cleaned = _DOC_REF_PATTERN.sub("", raw)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" -;:,")
    return cleaned, list(dict.fromkeys(refs))


def _score_point(text: str, *, task_type: str, horizon: str, side: str, language: str) -> int:
    lower = text.lower()
    score = 1

    lang = language if language in _SIGNIFICANCE_TERMS else "en"
    sig_terms = _SIGNIFICANCE_TERMS[lang]
    so_what_terms = _SO_WHAT_TERMS[lang]
    risk_terms = _RISK_TERMS[lang]
    cat_terms = _CATALYST_TERMS[lang]
    st_terms = _SHORT_TERM_TERMS[lang]
    mt_terms = _MEDIUM_TERM_TERMS[lang]

    if _NUMERIC_SIGNAL_PATTERN.search(text):
        score += 2
    if any(term in lower for term in sig_terms):
        score += 1
    if any(term in lower for term in so_what_terms):
        score += 1
    if len(text.split()) >= 12:
        score += 1
    if task_type == "risk" and any(term in lower for term in risk_terms):
        score += 1
    if task_type == "catalyst" and any(term in lower for term in cat_terms):
        score += 1
    if horizon == "short_term" and any(term in lower for term in st_terms):
        score += 1
    if horizon == "medium_term" and any(term in lower for term in mt_terms):
        score += 1
    if side == "bear" and any(term in lower for term in risk_terms):
        score += 1
    if side == "bull" and any(term in lower for term in cat_terms):
        score += 1
    return score


def _point_key(text: str) -> str:
    return _NON_ALNUM_PATTERN.sub(" ", text.lower()).strip()


def _is_limited_evidence(
    status: str,
    raw_context: Sequence[RetrievalItem],
    prepared_bulls: Sequence[ScoredPoint],
    prepared_bears: Sequence[ScoredPoint],
) -> bool:
    return (
        status != "success"
        or len(raw_context) < 2
        or (len(prepared_bulls) + len(prepared_bears)) < 2
    )


def _resolve_stance(
    sentiment: str,
    prepared_bulls: Sequence[ScoredPoint],
    prepared_bears: Sequence[ScoredPoint],
    limited_evidence: bool,
) -> str:
    bull_score = sum(point.score for point in prepared_bulls)
    bear_score = sum(point.score for point in prepared_bears)
    sentiment_normalized = str(sentiment or "").strip().lower()

    if bull_score == 0 and bear_score == 0:
        if sentiment_normalized == "positive":
            return "Positive"
        if sentiment_normalized == "negative":
            return "Negative"
        return "Mixed"

    if bull_score and not bear_score:
        return "Positive"
    if bear_score and not bull_score:
        return "Negative"

    ratio = (max(bull_score, bear_score) + 1) / (min(bull_score, bear_score) + 1)
    threshold = 1.65 if limited_evidence else 1.35
    if ratio < threshold:
        return "Mixed"

    stance = "Positive" if bull_score > bear_score else "Negative"
    if sentiment_normalized == "mixed" and ratio < 1.85:
        return "Mixed"
    if sentiment_normalized == "positive" and stance == "Negative" and ratio < 1.85:
        return "Mixed"
    if sentiment_normalized == "negative" and stance == "Positive" and ratio < 1.85:
        return "Mixed"
    return stance


def _build_view_label(task_type: str, horizon: str, language: str) -> str:
    if language == "ko":
        task_label = {
            "risk": "리스크 가중 분석",
            "catalyst": "촉매 중심 분석",
        }.get(task_type, "투자 분석")
        if horizon == "short_term":
            return f"단기 {task_label}"
        if horizon == "medium_term":
            return f"중기 {task_label}"
        return task_label
    else:
        task_label = {
            "risk": "risk-weighted view",
            "catalyst": "catalyst-driven view",
        }.get(task_type, "investment view")
        if horizon == "short_term":
            return f"near-term {task_label}"
        if horizon == "medium_term":
            return f"medium-term {task_label}"
        return task_label


def _build_conclusion(
    *,
    ticker: str,
    question: str,
    status: str,
    error_metadata: str | None,
    summary: str,
    uncertainty: str,
    confidence: float,
    stance: str,
    view_label: str,
    limited_evidence: bool,
    prepared_bulls: Sequence[ScoredPoint],
    prepared_bears: Sequence[ScoredPoint],
    selected_points: list[ScoredPoint],
    language: str,
) -> str:
    top_bulls = list(prepared_bulls[:2])
    top_bears = list(prepared_bears[:2])
    summary_text = _clean_sentence(summary)
    uncertainty_text = _clean_sentence(uncertainty)

    parts: list[str] = []
    if language == "ko":
        if limited_evidence:
            parts.append("본 분석은 제한된 근거에 기반한 가설이며, 완전한 투자 확약이 아닙니다.")
        elif confidence and confidence < 0.65:
            parts.append("현재 신호가 명확하게 한쪽으로 치우치지 않았으므로 신중한 접근이 필요합니다.")

        if stance == "Positive":
            lead = "조심스럽게 긍정적입니다" if limited_evidence else "긍정적입니다"
            parts.append(f"{ticker}에 대한 현재 {view_label}은 {lead}.")
            if top_bulls:
                selected_points.extend(top_bulls)
                parts.append(_build_driver_sentence("bull", top_bulls, language))
            elif summary_text:
                parts.append(f"현재 확인된 가장 강력한 근거는 다음과 같습니다: {summary_text}.")

            if top_bears:
                selected_points.append(top_bears[0])
                parts.append(f"이러한 관점을 뒤집을 수 있는 주요 요인은 {_clean_sentence(top_bears[0].text)}입니다.")
                parts.append(f"향후 반대 신호가 지배적으로 작용하는지 여부를 모니터링해야 합니다: {_clean_sentence(top_bears[0].text)}.")
            else:
                parts.append("현재 데이터 범위 내에서 이에 상응하는 강력한 하락 요인은 확인되지 않았으므로, 주관적인 판단보다는 확인된 근거에 기반한 확신을 유지해야 합니다.")
                if top_bulls:
                    parts.append(f"향후 가장 강력한 상승 신호가 지속되는지 여부를 모니터링해야 합니다: {_clean_sentence(top_bulls[0].text)}.")

        elif stance == "Negative":
            lead = "조심스럽게 보수적입니다" if limited_evidence else "보수적인 접근을 권고합니다"
            parts.append(f"{ticker}에 대한 현재 {view_label}은 {lead}.")
            if top_bears:
                selected_points.extend(top_bears)
                parts.append(_build_driver_sentence("bear", top_bears, language))
            elif summary_text:
                parts.append(f"현재 확인된 가장 강력한 하락 징후는 다음과 같습니다: {summary_text}.")

            if top_bulls:
                selected_points.append(top_bulls[0])
                parts.append(f"이러한 관점을 반전시킬 수 있는 주요 요인은 {_clean_sentence(top_bulls[0].text)}입니다.")
                parts.append(f"향후 상승 촉매가 더욱 견고해지는지 여부를 모니터링해야 합니다: {_clean_sentence(top_bulls[0].text)}.")
            else:
                parts.append("현재 데이터 범위 내에서 이에 상응하는 강력한 상승 동력은 확인되지 않았으므로, 반전의 근거가 아직 부족한 상태입니다.")
                if top_bears:
                    parts.append(f"향후 가장 강력한 하락 신호가 지속되는지 여부를 모니터링해야 합니다: {_clean_sentence(top_bears[0].text)}.")

        else:
            lead = "균형 잡힌 상태이지만 아직 불충분합니다" if limited_evidence else "한쪽으로 치우치지 않고 균형을 이루고 있습니다"
            parts.append(f"{ticker}에 대한 현재 {view_label}은 {lead}.")
            if top_bulls:
                selected_points.append(top_bulls[0])
                parts.append(f"매수 관점의 가장 강력한 근거는 {_clean_sentence(top_bulls[0].text)}입니다.")
            elif summary_text:
                parts.append(f"현재 확인된 주요 긍정적 지표는 다음과 같습니다: {summary_text}.")

            if top_bears:
                selected_points.append(top_bears[0])
                parts.append(f"명확한 판단을 제약하는 가장 큰 요인은 {_clean_sentence(top_bears[0].text)}입니다.")

            monitor_point = top_bears[1] if len(top_bears) > 1 else (top_bulls[1] if len(top_bulls) > 1 else None)
            if monitor_point is not None:
                selected_points.append(monitor_point)
                parts.append(f"향후 어느 쪽의 근거가 우세해지는지 모니터링하는 것이 핵심입니다: {_clean_sentence(monitor_point.text)}.")
            elif uncertainty_text:
                parts.append(f"현재 해결되지 않은 주요 문제는 {uncertainty_text}입니다.")

        if status == "partial" and error_metadata:
            parts.append(f"운영 측면에서, 본 분석은 현재 실행 조건에 의해 제한될 수 있습니다: {_clean_sentence(error_metadata)}.")

        if not prepared_bulls and not prepared_bears and summary_text:
            parts.append(f"현재 확인된 유일한 근거는 다음과 같습니다: {summary_text}.")

    else:
        # Default English path
        if limited_evidence:
            parts.append("This is a limited-evidence thesis, not a full underwriting call.")
        elif confidence and confidence < 0.65:
            parts.append("Conviction should remain measured because the current signal is not yet cleanly one-sided.")

        if stance == "Positive":
            lead = "is tentatively constructive" if limited_evidence else "is constructive"
            parts.append(f"The current {view_label} on {ticker} {lead}.")
            if top_bulls:
                selected_points.extend(top_bulls)
                parts.append(_build_driver_sentence("bull", top_bulls, language))
            elif summary_text:
                parts.append(f"The strongest grounded support in the current evidence window is: {summary_text}.")

            if top_bears:
                selected_points.append(top_bears[0])
                parts.append(f"The main factor that could invalidate that view is {_clean_sentence(top_bears[0].text)}.")
                parts.append(f"The key monitor from here is whether the current counter-signal starts to dominate: {_clean_sentence(top_bears[0].text)}.")
            else:
                parts.append("The current evidence window does not surface a comparably strong documented bear case, so conviction should stay evidence-bound rather than open-ended.")
                if top_bulls:
                    parts.append(f"The key monitor from here is whether the strongest bullish signal continues to hold: {_clean_sentence(top_bulls[0].text)}.")

        elif stance == "Negative":
            lead = "is tentatively cautious" if limited_evidence else "skews cautious"
            parts.append(f"The current {view_label} on {ticker} {lead}.")
            if top_bears:
                selected_points.extend(top_bears)
                parts.append(_build_driver_sentence("bear", top_bears, language))
            elif summary_text:
                parts.append(f"The strongest grounded downside read in the current evidence window is: {summary_text}.")

            if top_bulls:
                selected_points.append(top_bulls[0])
                parts.append(f"The main factor that could improve that view is {_clean_sentence(top_bulls[0].text)}.")
                parts.append(f"The key monitor from here is whether the current bullish offset becomes more durable: {_clean_sentence(top_bulls[0].text)}.")
            else:
                parts.append("The current evidence window does not surface a comparably strong documented bullish offset, so reversal evidence is still missing.")
                if top_bears:
                    parts.append(f"The key monitor from here is whether the strongest bearish signal continues to hold: {_clean_sentence(top_bears[0].text)}.")

        else:
            lead = "is balanced but still incomplete" if limited_evidence else "is balanced rather than one-sided"
            parts.append(f"The current {view_label} on {ticker} {lead}.")
            if top_bulls:
                selected_points.append(top_bulls[0])
                parts.append(f"The strongest support for the long case is {_clean_sentence(top_bulls[0].text)}.")
            elif summary_text:
                parts.append(f"The main supportive read in the current evidence window is: {summary_text}.")

            if top_bears:
                selected_points.append(top_bears[0])
                parts.append(f"The clearest constraint on a cleaner underwriting call is {_clean_sentence(top_bears[0].text)}.")

            monitor_point = top_bears[1] if len(top_bears) > 1 else (top_bulls[1] if len(top_bulls) > 1 else None)
            if monitor_point is not None:
                selected_points.append(monitor_point)
                parts.append(f"The key monitor from here is which side of the evidence set starts to dominate: {_clean_sentence(monitor_point.text)}.")
            elif uncertainty_text:
                parts.append(f"The main unresolved issue in the current evidence window is {uncertainty_text.lower()}.")

        if status == "partial" and error_metadata:
            parts.append(f"Operationally, the thesis is capped by the current run condition: {_clean_sentence(error_metadata)}.")

        if not prepared_bulls and not prepared_bears and summary_text:
            parts.append(f"The only grounded read available from the current evidence window is: {summary_text}.")

    return " ".join(_dedupe_sentences(parts))


def _build_driver_sentence(side: str, points: Sequence[ScoredPoint], language: str) -> str:
    cleaned_points = [_clean_sentence(point.text) for point in points if _clean_sentence(point.text)]
    if not cleaned_points:
        return ""
    
    if language == "ko":
        if len(cleaned_points) == 1:
            if side == "bull":
                return f"가장 잘 뒷받침되는 동인은 {cleaned_points[0]}입니다."
            return f"가장 잘 뒷받침되는 하위 요인은 {cleaned_points[0]}입니다."
        joined = ", ".join(cleaned_points[:-1]) + f", 그리고 {cleaned_points[-1]}"
        if side == "bull":
            return f"가장 잘 뒷받침되는 핵심 동인들은 {joined} 등입니다."
        return f"가장 잘 뒷받침되는 주요 하위 요인들은 {joined} 등입니다."
    else:
        if len(cleaned_points) == 1:
            if side == "bull":
                return f"The best-supported driver is {cleaned_points[0]}."
            return f"The best-supported downside driver is {cleaned_points[0]}."

        joined = "; ".join(cleaned_points[:-1]) + f"; and {cleaned_points[-1]}"
        if side == "bull":
            return f"The best-supported drivers are {joined}."
        return f"The best-supported downside drivers are {joined}."


def _build_citations(
    cited_doc_ids: Sequence[str] | str | None,
    raw_context: Sequence[RetrievalItem],
    selected_points: Sequence[ScoredPoint],
    limit: int = 4,
) -> list[Citation]:
    by_doc_id = {}
    indexed_context = list(raw_context)
    for idx, item in enumerate(indexed_context, start=1):
        doc_id = str(item.metadata.get("doc_id", "")).strip()
        parent_doc_id = str(item.metadata.get("parent_doc_id", "")).strip()
        if doc_id:
            by_doc_id[doc_id] = item
        if parent_doc_id:
            by_doc_id[parent_doc_id] = item

    citations: list[Citation] = []
    seen: set[tuple[str, str, str]] = set()

    normalized_doc_ids: list[str] = []
    if isinstance(cited_doc_ids, str):
        normalized_doc_ids = [cited_doc_ids]
    elif cited_doc_ids:
        normalized_doc_ids = [str(value) for value in cited_doc_ids]

    for doc_id in normalized_doc_ids:
        item = by_doc_id.get(doc_id)
        if item is not None:
            _append_citation(citations, seen, item, limit)

    for point in selected_points:
        for ref in point.doc_refs:
            if 1 <= ref <= len(indexed_context):
                _append_citation(citations, seen, indexed_context[ref - 1], limit)
            if len(citations) >= limit:
                return citations
    if not citations:
        for item in indexed_context:
            _append_citation(citations, seen, item, limit)
            if len(citations) >= limit:
                return citations
    return citations


def _append_citation(
    citations: list[Citation],
    seen: set[tuple[str, str, str]],
    item: RetrievalItem,
    limit: int,
) -> None:
    if len(citations) >= limit:
        return
    doc_id = None
    if isinstance(getattr(item, "metadata", None), dict):
        raw_doc_id = item.metadata.get("parent_doc_id") or item.metadata.get("doc_id")
        if raw_doc_id:
            doc_id = str(raw_doc_id)
    citation = Citation(source=item.source, title=item.title, date=item.date, doc_id=doc_id)
    key = (citation.source, citation.title, citation.date)
    if key in seen:
        return
    seen.add(key)
    citations.append(citation)


def _clean_sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    return cleaned.rstrip(".")


def _dedupe_sentences(parts: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        cleaned = " ".join(str(part or "").split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result
