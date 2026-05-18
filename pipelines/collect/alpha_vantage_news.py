from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from core.utils.data_helpers import as_clean_text, extract_records, normalize_news_records
from pipelines.collect.fmp_news import filter_fresh_documents
from pipelines.collect.models import SourceCollectionResult

_NEWS_URL = "https://www.alphavantage.co/query"
_HTTP_TIMEOUT_S = 10.0


def _now() -> datetime:
    return datetime.now()


def _to_iso(value: Any) -> str:
    text = as_clean_text(value)
    if not text:
        return ""
    for fmt in ("%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return text


def _fetch_json(symbol: str, api_key: str, limit: int) -> tuple[str, Any]:
    try:
        response = httpx.get(
            _NEWS_URL,
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "limit": max(1, min(limit, 1000)),
                "apikey": api_key,
            },
            timeout=_HTTP_TIMEOUT_S,
        )
    except httpx.TimeoutException:
        return "timeout", None
    except httpx.HTTPError as exc:
        return "provider_unavailable", str(exc)

    if response.status_code in (401, 403):
        return "credentials_missing", response.text
    if response.status_code == 429:
        return "rate_limited", response.text
    if response.status_code >= 500:
        return "provider_unavailable", response.text
    if response.status_code != 200:
        return "provider_unavailable", response.text

    try:
        payload = response.json()
    except ValueError:
        return "provider_unavailable", response.text

    if isinstance(payload, dict):
        if payload.get("Information") or payload.get("Note"):
            return "rate_limited", payload.get("Information") or payload.get("Note")
        if payload.get("Error Message"):
            return "credentials_missing", payload.get("Error Message")
    return "ok", payload


def _map_record(record: Any, symbol: str) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    title = record.get("title") or ""
    summary = record.get("summary") or ""
    if not title and not summary:
        return None
    return {
        "title": title,
        "text": summary,
        "body": "",
        "published_at": _to_iso(record.get("time_published")),
        "source": record.get("source") or "Alpha Vantage",
        "url": record.get("url") or "",
        "symbol": symbol,
        "company_name": symbol,
        "provider": "alpha_vantage",
    }


def collect_news_from_alpha_vantage(
    symbol: str,
    lookback_days: int,
    api_key: str,
    *,
    limit: int = 20,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    if not api_key:
        return (
            SourceCollectionResult(
                source="news",
                status="credentials_missing",
                doc_count=0,
                elapsed_s=0.0,
                detail="ALPHA_VANTAGE_API_KEY is missing; Alpha Vantage news collection is disabled.",
            ),
            [],
        )

    started_at = _now()
    status, payload = _fetch_json(symbol, api_key, limit)
    elapsed_s = round((_now() - started_at).total_seconds(), 2)
    if status != "ok":
        return (
            SourceCollectionResult("news", status, 0, elapsed_s, f"Alpha Vantage news request returned status={status}."),
            [],
        )

    feed = payload.get("feed") if isinstance(payload, dict) else payload
    mapped_records = [
        mapped
        for mapped in (_map_record(record, symbol) for record in extract_records(feed))
        if mapped is not None
    ]
    if not mapped_records:
        return (
            SourceCollectionResult("news", "empty", 0, elapsed_s, "Alpha Vantage returned zero usable news records."),
            [],
        )

    normalized = normalize_news_records(mapped_records, symbol, company_name=symbol, source_hint="alpha_vantage")
    fresh_documents, freshness_detail = filter_fresh_documents(
        normalized,
        lookback_days,
        now=started_at,
        collected_at=started_at.isoformat(),
    )
    elapsed_s = round((_now() - started_at).total_seconds(), 2)
    if not fresh_documents:
        detail = freshness_detail or "Alpha Vantage records did not survive the freshness window."
        return SourceCollectionResult("news", "empty", 0, elapsed_s, detail), []

    return (
        SourceCollectionResult("news", "ok", len(fresh_documents), elapsed_s, "Alpha Vantage news collected."),
        fresh_documents,
    )
