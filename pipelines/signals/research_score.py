from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def coerce_research_score(payload: dict[str, Any] | None, *, max_age_days: int = 7) -> tuple[float | None, list[str]]:
    """Return a bounded fresh research score, or diagnostics explaining absence.

    The Quant Lab treats research as a confirmation input only. Missing, stale,
    or malformed research never blocks deterministic factor/backtest work.
    """

    if not payload:
        return None, ["research_score_unavailable"]
    diagnostics: list[str] = []
    try:
        score = float(payload.get("score"))
    except (TypeError, ValueError):
        return None, ["research_score_invalid"]
    score = max(-1.0, min(1.0, score))
    as_of = str(payload.get("as_of") or "").strip()
    if as_of:
        try:
            observed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).days
            if age_days > int(max_age_days):
                return None, [f"research_score_stale:{age_days}d"]
        except ValueError:
            diagnostics.append("research_score_as_of_unparseable")
    else:
        diagnostics.append("research_score_as_of_missing")
    evidence_ids = payload.get("evidence_ids") or payload.get("evidence_doc_ids") or []
    if not evidence_ids:
        diagnostics.append("research_score_evidence_sparse")
    return score, diagnostics


def evaluate_research_score(payload: dict[str, Any] | None, *, max_age_days: int = 7) -> dict[str, Any]:
    score, diagnostics = coerce_research_score(payload, max_age_days=max_age_days)
    status = "fresh"
    if not payload:
        status = "unavailable"
    elif any(item.startswith("research_score_stale") for item in diagnostics):
        status = "expired"
    elif any(item in {"research_score_invalid", "research_score_as_of_unparseable"} for item in diagnostics):
        status = "invalid"
    elif "research_score_evidence_sparse" in diagnostics:
        status = "sparse_evidence"
    expiry = ""
    as_of = str((payload or {}).get("as_of") or "").strip()
    if as_of:
        try:
            observed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            expiry = (observed.astimezone(timezone.utc) + timedelta(days=int(max_age_days))).isoformat()
        except ValueError:
            expiry = ""
    return {
        "status": status,
        "score": score,
        "diagnostics": diagnostics,
        "run_id": (payload or {}).get("run_id") or "",
        "as_of": as_of,
        "expires_at": expiry,
        "model": (payload or {}).get("model") or "",
        "prompt_version": (payload or {}).get("prompt_version") or "unknown",
        "evidence_doc_ids": list((payload or {}).get("evidence_ids") or (payload or {}).get("evidence_doc_ids") or []),
    }
