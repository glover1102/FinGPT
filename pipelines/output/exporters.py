"""Export adapters for analysis responses.

The pipeline always writes canonical artifacts (``response.json``, ``report.md``,
``report.html``) to disk. This module produces *derived* formats on demand:

- **CSV** — a flat Bull/Bear table with per-bullet evidence ids and citation
  columns. Optimized for spreadsheet review and portfolio tooling that prefers
  tabular data over JSON.
- **JSONL** — one document per line, suitable for feeding the project's eval
  pipeline (`evaluation_pass.py`) or external analytics. Each line bundles the
  retrieved chunk with the decision context (sentiment, confidence, thesis
  point text, evidence linkage) so downstream consumers can score grounding
  without rejoining tables.

Both formats are generated in memory from an ``AnalysisResponse``-shaped dict
so we can reuse them for both the "latest" run and any archived run_id.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Iterable


def _safe(val: Any, default: str = "") -> str:
    if val is None:
        return default
    if isinstance(val, (list, tuple)):
        return ", ".join(str(x) for x in val if x is not None)
    return str(val)


def response_to_csv(response: dict[str, Any]) -> str:
    """Render a response to a Bull/Bear-centric CSV.

    Layout: one header row + one row per bull/bear point + one trailing row per
    citation. This keeps the file self-contained (no second sheet needed) while
    remaining trivially filterable by the ``kind`` column.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")

    ticker = _safe(response.get("ticker"))
    question = _safe(response.get("question"))
    sentiment = _safe(response.get("sentiment"))
    confidence = response.get("confidence")
    status = _safe(response.get("status"))
    summary = _safe(response.get("summary"))

    writer.writerow([
        "ticker",
        "question",
        "status",
        "sentiment",
        "confidence",
        "kind",
        "index",
        "text",
        "evidence_doc_ids",
        "citation_source",
        "citation_title",
        "citation_date",
    ])

    # Row 0: top-level summary so every CSV carries the headline answer.
    writer.writerow([ticker, question, status, sentiment, confidence, "summary", 0, summary, "", "", "", ""])

    bulls = list(response.get("bull_points") or [])
    bull_ev = list(response.get("bull_evidence_ids") or [])
    for i, txt in enumerate(bulls):
        ev = bull_ev[i] if i < len(bull_ev) else []
        writer.writerow([
            ticker, question, status, sentiment, confidence,
            "bull", i + 1, _safe(txt), _safe(ev), "", "", "",
        ])

    bears = list(response.get("bear_points") or [])
    bear_ev = list(response.get("bear_evidence_ids") or [])
    for i, txt in enumerate(bears):
        ev = bear_ev[i] if i < len(bear_ev) else []
        writer.writerow([
            ticker, question, status, sentiment, confidence,
            "bear", i + 1, _safe(txt), _safe(ev), "", "", "",
        ])

    for i, c in enumerate(response.get("citations") or []):
        writer.writerow([
            ticker, question, status, sentiment, confidence,
            "citation", i + 1, "", _safe(c.get("doc_id")),
            _safe(c.get("source")), _safe(c.get("title")), _safe(c.get("date")),
        ])

    writer.writerow([
        ticker, question, status, sentiment, confidence,
        "conclusion", 0, _safe(response.get("conclusion")), "", "", "", "",
    ])

    return buf.getvalue()


def response_to_jsonl(response: dict[str, Any], *, include_raw_context: bool = True) -> str:
    """Render a response to JSONL — one record per evidence chunk + thesis point.

    The eval pipeline keys off of ``record_type`` to know whether it is scoring
    a retrieval hit, a bull point, or a bear point. Order is: run header,
    retrieval chunks, bull points, bear points, citations.
    """
    lines: list[str] = []
    exported_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    base = {
        "ticker": response.get("ticker"),
        "question": response.get("question"),
        "status": response.get("status"),
        "sentiment": response.get("sentiment"),
        "confidence": response.get("confidence"),
        "exported_at": exported_at,
    }

    lines.append(json.dumps({**base, "record_type": "run_header",
                             "summary": response.get("summary"),
                             "conclusion": response.get("conclusion"),
                             "execution_meta": response.get("execution_meta")},
                            ensure_ascii=False))

    if include_raw_context:
        for i, item in enumerate(response.get("raw_context") or []):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata") or {}
            lines.append(
                json.dumps(
                    {
                        **base,
                        "record_type": "retrieval",
                        "index": i,
                        "doc_id": metadata.get("doc_id"),
                        "source": metadata.get("source") or metadata.get("doc_type"),
                        "title": metadata.get("title"),
                        "published_at": metadata.get("published_at"),
                        "score": item.get("score"),
                        "text": item.get("document") or item.get("text"),
                    },
                    ensure_ascii=False,
                )
            )

    bulls = list(response.get("bull_points") or [])
    bull_ev = list(response.get("bull_evidence_ids") or [])
    for i, txt in enumerate(bulls):
        lines.append(json.dumps({
            **base,
            "record_type": "bull_point",
            "index": i,
            "text": txt,
            "evidence_doc_ids": bull_ev[i] if i < len(bull_ev) else [],
        }, ensure_ascii=False))

    bears = list(response.get("bear_points") or [])
    bear_ev = list(response.get("bear_evidence_ids") or [])
    for i, txt in enumerate(bears):
        lines.append(json.dumps({
            **base,
            "record_type": "bear_point",
            "index": i,
            "text": txt,
            "evidence_doc_ids": bear_ev[i] if i < len(bear_ev) else [],
        }, ensure_ascii=False))

    for i, c in enumerate(response.get("citations") or []):
        if not isinstance(c, dict):
            continue
        lines.append(json.dumps({
            **base,
            "record_type": "citation",
            "index": i,
            "source": c.get("source"),
            "title": c.get("title"),
            "date": c.get("date"),
            "doc_id": c.get("doc_id"),
        }, ensure_ascii=False))

    return "\n".join(lines) + "\n"


def iter_supported_formats() -> Iterable[str]:
    """Enumerate export keys recognized by the API layer."""
    return ("csv", "jsonl")
