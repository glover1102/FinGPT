"""Aggregator for the UI Quality dashboard.

Stitches together the two evaluation artifacts the project already produces:

- ``reports/latest_eval_report.md`` — human-authored eval/hardening reports.
- ``quality_review_results.json`` — structured output of ``quality_review.py``
  (one entry per probe run).

The JSON file can live either at the project root (legacy path) or under
``reports/`` / ``data/``, so we probe all three. The summary collapses the
array into the stats the UI actually needs: pass/partial/fail counts, purity
/confidence averages, per-category breakdown, and the most recent cases.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


_EVAL_REPORT_CANDIDATES = (
    "reports/latest_eval_report.md",
    "reports/evaluation_report.md",
    "docs/latest_eval_report.md",
)

_QUALITY_RESULT_CANDIDATES = (
    "quality_review_results.json",
    "reports/quality_review_results.json",
    "data/quality_review_results.json",
    "data/outputs/quality_review_results.json",
    "../quality_review_results.json",  # legacy location (one level above repo)
)


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _locate(project_root: Path, candidates: Iterable[str]) -> Path | None:
    for rel in candidates:
        candidate = (project_root / rel).resolve()
        if candidate.exists():
            return candidate
    return None


def _summarize_entries(entries: list[dict]) -> dict:
    if not entries:
        return {
            "total": 0,
            "status_counts": {},
            "avg_confidence": None,
            "avg_purity": None,
            "avg_elapsed_s": None,
            "categories": [],
        }

    status_counts: dict[str, int] = {}
    by_category: dict[str, dict[str, Any]] = {}
    confidences: list[float] = []
    purities: list[float] = []
    elapsed: list[float] = []

    for entry in entries:
        status = str(entry.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        category = str(entry.get("category") or "uncategorized")
        bucket = by_category.setdefault(
            category,
            {"category": category, "count": 0, "pass": 0, "partial": 0, "failed": 0, "avg_confidence": None},
        )
        bucket["count"] += 1
        if status == "success":
            bucket["pass"] += 1
        elif status == "partial":
            bucket["partial"] += 1
        elif status == "failed":
            bucket["failed"] += 1

        conf = entry.get("confidence")
        if isinstance(conf, (int, float)):
            confidences.append(float(conf))
        purity = entry.get("purity_ratio")
        if isinstance(purity, (int, float)):
            purities.append(float(purity))
        el = entry.get("elapsed_s")
        if isinstance(el, (int, float)):
            elapsed.append(float(el))

    # Per-category avg confidence second pass (cheap — same array).
    for category, bucket in by_category.items():
        cat_conf = [
            float(e.get("confidence"))
            for e in entries
            if str(e.get("category") or "uncategorized") == category and isinstance(e.get("confidence"), (int, float))
        ]
        bucket["avg_confidence"] = round(mean(cat_conf), 3) if cat_conf else None

    return {
        "total": len(entries),
        "status_counts": status_counts,
        "avg_confidence": round(mean(confidences), 3) if confidences else None,
        "avg_purity": round(mean(purities), 3) if purities else None,
        "avg_elapsed_s": round(mean(elapsed), 2) if elapsed else None,
        "categories": sorted(by_category.values(), key=lambda b: (-b["count"], b["category"])),
    }


def _slim_entry(entry: dict) -> dict:
    """Trim the cases list for the UI — the full raw_context bloats the payload."""
    return {
        "suite": entry.get("suite"),
        "category": entry.get("category"),
        "desc": entry.get("desc"),
        "ticker": entry.get("ticker"),
        "question": entry.get("question"),
        "mode": entry.get("mode"),
        "status": entry.get("status"),
        "error": entry.get("error"),
        "summary": entry.get("summary"),
        "sentiment": entry.get("sentiment"),
        "confidence": entry.get("confidence"),
        "context_chunks": entry.get("context_chunks"),
        "purity_ratio": entry.get("purity_ratio"),
        "citation_count": entry.get("citation_count"),
        "evidence_count": entry.get("evidence_count"),
        "language_ok": entry.get("language_ok"),
        "decision_richness": entry.get("decision_richness"),
        "gate_pass": entry.get("gate_pass"),
        "elapsed_s": entry.get("elapsed_s"),
        "inferred_lens": entry.get("inferred_lens"),
        "inferred_horizon": entry.get("inferred_horizon"),
        "model_used": entry.get("model_used"),
        "audit": entry.get("audit"),
    }


def load_eval_dashboard(project_root: Path, *, case_limit: int = 50) -> dict:
    """Return a dict safe to serialize straight to the UI."""
    project_root = Path(project_root)

    report_path = _locate(project_root, _EVAL_REPORT_CANDIDATES)
    results_path = _locate(project_root, _QUALITY_RESULT_CANDIDATES)

    report_md = _read_text(report_path) if report_path else None
    results_raw = _read_json(results_path) if results_path else None

    cases: list[dict] = []
    if isinstance(results_raw, list):
        cases = [entry for entry in results_raw if isinstance(entry, dict)]
    elif isinstance(results_raw, dict) and isinstance(results_raw.get("cases"), list):
        cases = [entry for entry in results_raw["cases"] if isinstance(entry, dict)]

    summary = _summarize_entries(cases)

    # Cap the per-case payload so the UI payload stays modest (<50 items is
    # ample for the dashboard; a dedicated download path could expose raw).
    trimmed_cases = [_slim_entry(c) for c in cases[-case_limit:]]

    return {
        "has_report": report_path is not None,
        "has_results": results_path is not None,
        "report_path": str(report_path.relative_to(project_root)) if report_path else None,
        "results_path": str(results_path.relative_to(project_root)) if results_path and _is_under(results_path, project_root) else (str(results_path) if results_path else None),
        "report_markdown": report_md,
        "summary": summary,
        "cases": trimmed_cases,
    }


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
