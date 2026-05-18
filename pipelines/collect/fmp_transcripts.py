from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from core.utils.data_helpers import extract_records, normalize_transcript_records
from pipelines.collect.models import SourceCollectionResult

_TRANSCRIPT_DATES_URL = "https://financialmodelingprep.com/stable/earning-call-transcript-dates"
_TRANSCRIPT_BODY_URL = "https://financialmodelingprep.com/stable/earning-call-transcript"
_HTTP_TIMEOUT_S = 8.0


def _normalize_quarter(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text.startswith("Q"):
        text = text[1:]
    try:
        quarter = int(text)
    except ValueError:
        return None
    if 1 <= quarter <= 4:
        return quarter
    return None


def _quarter_from_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def _previous_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year, quarter - 1) if quarter > 1 else (year - 1, 4)


def _candidate_periods(lookback_days: int) -> set[tuple[int, int]]:
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    start_pair = (start.year, _quarter_from_month(start.month))
    end_pair = (end.year, _quarter_from_month(end.month))
    return {start_pair, end_pair, _previous_quarter(*start_pair)}


def _fetch_json(url: str, *, params: dict[str, Any]) -> tuple[str, Any]:
    try:
        response = httpx.get(url, params=params, timeout=_HTTP_TIMEOUT_S)
    except httpx.TimeoutException:
        return "timeout", None
    except httpx.HTTPError as exc:
        return "provider_unavailable", str(exc)

    if response.status_code in (401, 403):
        return "credentials_missing", None
    if response.status_code == 402:
        return "entitlement_required", response.text
    if response.status_code == 429:
        return "rate_limited", None
    if response.status_code >= 500:
        return "provider_unavailable", response.text
    if response.status_code == 404:
        return "no_data_in_window", None
    if response.status_code != 200:
        return "provider_unavailable", response.text

    try:
        return "ok", response.json()
    except ValueError:
        return "provider_unavailable", response.text


def _available_periods(rows: list[Any]) -> set[tuple[int, int]]:
    periods: set[tuple[int, int]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        year = row.get("year") or row.get("fiscalYear")
        quarter = row.get("quarter") or row.get("fiscalQuarter")
        try:
            normalized_year = int(year)
        except (TypeError, ValueError):
            continue
        normalized_quarter = _normalize_quarter(quarter)
        if normalized_quarter is None:
            continue
        periods.add((normalized_year, normalized_quarter))
    return periods


def collect_transcripts_from_fmp(symbol: str, lookback_days: int, fmp_api_key: str) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    if not fmp_api_key:
        return (
            SourceCollectionResult(
                source="transcript",
                status="credentials_missing",
                doc_count=0,
                elapsed_s=0.0,
                detail="FMP_API_KEY is missing; transcript collection is disabled.",
            ),
            [],
        )

    started_at = datetime.now()
    status, payload = _fetch_json(
        _TRANSCRIPT_DATES_URL,
        params={"symbol": symbol, "apikey": fmp_api_key},
    )
    elapsed_s = round((datetime.now() - started_at).total_seconds(), 2)
    if status != "ok":
        return (
            SourceCollectionResult(
                source="transcript",
                status=status,
                doc_count=0,
                elapsed_s=elapsed_s,
                detail=f"Transcript dates request returned status={status}.",
            ),
            [],
        )

    rows = extract_records(payload)
    candidate_periods = _candidate_periods(lookback_days)
    matching_periods = sorted(_available_periods(rows) & candidate_periods, reverse=True)
    if not matching_periods:
        return (
            SourceCollectionResult(
                source="transcript",
                status="no_data_in_window",
                doc_count=0,
                elapsed_s=elapsed_s,
                detail="No transcript periods were available inside the requested lookback window.",
            ),
            [],
        )

    documents: list[dict[str, Any]] = []
    worst_status: str | None = None

    for year, quarter in matching_periods:
        body_started_at = datetime.now()
        body_status, body_payload = _fetch_json(
            _TRANSCRIPT_BODY_URL,
            params={"symbol": symbol, "year": year, "quarter": quarter, "apikey": fmp_api_key},
        )
        elapsed_s += round((datetime.now() - body_started_at).total_seconds(), 2)

        if body_status == "ok":
            normalized = normalize_transcript_records(extract_records(body_payload), symbol)
            documents.extend(normalized)
            continue

        if worst_status is None or worst_status == "no_data_in_window":
            worst_status = body_status

    if documents:
        detail = f"Collected transcripts for {len(matching_periods)} candidate period(s)."
        return (
            SourceCollectionResult(
                source="transcript",
                status="ok",
                doc_count=len(documents),
                elapsed_s=round(elapsed_s, 2),
                detail=detail,
            ),
            documents,
        )

    final_status = worst_status or "no_data_in_window"
    if final_status == "no_data_in_window":
        detail = "Transcript periods were available, but no transcript body fell inside the requested window."
    elif final_status == "timeout":
        detail = "Transcript provider timed out."
    elif final_status == "rate_limited":
        detail = "Transcript provider rate-limited the request."
    elif final_status == "credentials_missing":
        detail = "Transcript provider rejected the FMP credentials."
    elif final_status == "entitlement_required":
        detail = "Transcript provider requires FMP account/API entitlement."
    else:
        detail = "Transcript provider was unavailable."

    return (
        SourceCollectionResult(
            source="transcript",
            status=final_status,
            doc_count=0,
            elapsed_s=round(elapsed_s, 2),
            detail=detail,
        ),
        [],
    )
