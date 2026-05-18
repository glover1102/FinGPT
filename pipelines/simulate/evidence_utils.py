from __future__ import annotations

from typing import Any

from pipelines.simulate.fallback import clean_text, unique_strings


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _metadata(obj: Any) -> dict[str, Any]:
    value = _get(obj, "metadata", {}) or {}
    return value if isinstance(value, dict) else {}


def extract_evidence_doc_ids(obj: Any) -> list[str]:
    if obj is None:
        return []
    if isinstance(obj, (list, tuple, set)):
        ids: list[str] = []
        for item in obj:
            ids.extend(extract_evidence_doc_ids(item))
        return unique_strings(ids)
    metadata = _metadata(obj)
    candidates: list[Any] = [
        _get(obj, "parent_doc_id"),
        _get(obj, "doc_id"),
        _get(obj, "id"),
        metadata.get("parent_doc_id"),
        metadata.get("doc_id"),
        metadata.get("id"),
    ]
    for field in ("evidence_doc_ids", "key_evidence_doc_ids", "bull_evidence_ids", "bear_evidence_ids"):
        candidates.extend(extract_evidence_doc_ids(_get(obj, field)))
    return unique_strings(candidates)


def extract_key_metrics(analysis_response: Any) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for metric in _get(analysis_response, "key_metrics", []) or []:
        if hasattr(metric, "model_dump"):
            payload = metric.model_dump(mode="json")
        elif isinstance(metric, dict):
            payload = dict(metric)
        else:
            payload = {
                "name": _get(metric, "name", ""),
                "value": _get(metric, "value", ""),
                "unit": _get(metric, "unit", ""),
                "as_of": _get(metric, "as_of", None),
            }
        if payload.get("name") or payload.get("value"):
            metrics.append(payload)
    return metrics


def _driver_texts(items: list[Any], expected_direction: str | None = None) -> list[str]:
    output: list[str] = []
    for item in items or []:
        direction = _get(item, "direction", "")
        if expected_direction and direction and direction != expected_direction:
            continue
        text = _get(item, "text", "")
        if text:
            output.append(clean_text(text, limit=260))
    return [item for item in output if item]


def _section_bullets(items: list[Any]) -> list[str]:
    output: list[str] = []
    for item in items or []:
        output.extend(clean_text(text, limit=260) for text in (_get(item, "bullets", []) or []))
        conclusion = clean_text(_get(item, "conclusion", ""), limit=260)
        if conclusion:
            output.append(conclusion)
    return [item for item in output if item]


def extract_quant_snapshot(analysis_response: Any, explicit_quant_snapshot: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if explicit_quant_snapshot is not None:
        return explicit_quant_snapshot if isinstance(explicit_quant_snapshot, dict) else None
    meta = _get(analysis_response, "execution_meta")
    extras = _get(meta, "extras", {}) or {}
    if not isinstance(extras, dict):
        return None
    for key in ("quant_snapshot", "structured_context"):
        value = extras.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def _document_from_item(item: Any, fallback: str) -> dict[str, Any]:
    metadata = _metadata(item)
    doc_id = (
        metadata.get("parent_doc_id")
        or metadata.get("doc_id")
        or _get(item, "parent_doc_id")
        or _get(item, "doc_id")
        or fallback
    )
    title = _get(item, "title", "") or metadata.get("title", "")
    source = _get(item, "source", "") or metadata.get("source", "unknown")
    date = _get(item, "date", "") or metadata.get("date", "")
    snippet = _get(item, "chunk", "") or _get(item, "snippet", "") or _get(item, "text", "")
    return {
        "doc_id": clean_text(doc_id, limit=100) or fallback,
        "title": clean_text(title, limit=160),
        "source": clean_text(source, limit=80) or "unknown",
        "date": clean_text(date, limit=40),
        "snippet": clean_text(snippet, limit=520),
    }


def build_evidence_payload(
    analysis_response: Any,
    retrieved_documents: list[Any] | None = None,
    quant_snapshot: dict[str, Any] | None = None,
    max_docs: int = 12,
) -> dict[str, Any]:
    source_docs = retrieved_documents
    if source_docs is None:
        source_docs = _get(analysis_response, "raw_context", []) or []

    documents: list[dict[str, Any]] = []
    for idx, item in enumerate(source_docs or [], start=1):
        documents.append(_document_from_item(item, fallback=f"doc-{idx}"))
        if len(documents) >= max_docs:
            break

    citations = _get(analysis_response, "citations", []) or []
    if not documents and citations:
        for idx, citation in enumerate(citations, start=1):
            documents.append(_document_from_item(citation, fallback=f"citation-{idx}"))
            if len(documents) >= max_docs:
                break

    bull_evidence_ids = extract_evidence_doc_ids(_get(analysis_response, "bull_evidence_ids", []))
    bear_evidence_ids = extract_evidence_doc_ids(_get(analysis_response, "bear_evidence_ids", []))
    key_metrics = extract_key_metrics(analysis_response)
    snapshot = extract_quant_snapshot(analysis_response, quant_snapshot)
    ticker = (
        _get(analysis_response, "ticker", "")
        or _get(analysis_response, "theme", "")
        or _get(analysis_response, "topic", "")
        or "UNKNOWN"
    )
    summary = _get(analysis_response, "summary", "") or _get(analysis_response, "executive_summary", "") or _get(analysis_response, "core_thesis", "")
    bull_points = [clean_text(item, limit=260) for item in (_get(analysis_response, "bull_points", []) or []) if clean_text(item)]
    bear_points = [clean_text(item, limit=260) for item in (_get(analysis_response, "bear_points", []) or []) if clean_text(item)]
    if not bull_points:
        bull_points = unique_strings(
            _driver_texts(_get(analysis_response, "key_drivers", []) or [], "supporting")
            + _section_bullets(_get(analysis_response, "asset_overview", []) or [])
            + _section_bullets(_get(analysis_response, "investment_judgment", []) or []),
            limit=6,
        )
    if not bear_points:
        bear_points = unique_strings(
            _driver_texts(_get(analysis_response, "key_risks", []) or [], "opposing")
            + _section_bullets(_get(analysis_response, "macro_regime", []) or [])
            + _section_bullets(_get(analysis_response, "rate_structure", []) or []),
            limit=6,
        )

    return {
        "ticker_or_topic": clean_text(ticker, limit=80),
        "question": clean_text(_get(analysis_response, "question", ""), limit=260),
        "summary": clean_text(summary, limit=900),
        "status": clean_text(_get(analysis_response, "status", "unknown"), limit=40),
        "sentiment": clean_text(_get(analysis_response, "sentiment", ""), limit=80),
        "confidence": float(_get(analysis_response, "confidence", 0.0) or 0.0),
        "bull_points": bull_points,
        "bear_points": bear_points,
        "bull_evidence_ids": bull_evidence_ids,
        "bear_evidence_ids": bear_evidence_ids,
        "key_metrics": key_metrics,
        "quant_snapshot": snapshot or {},
        "documents": documents,
        "uncertainty": clean_text(_get(analysis_response, "uncertainty", ""), limit=420),
    }
