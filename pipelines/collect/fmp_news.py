from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from core.utils.data_helpers import as_clean_text, extract_records, normalize_news_records
from pipelines.collect.models import SourceCollectionResult

_STOCK_NEWS_URL = "https://financialmodelingprep.com/stable/news/stock"
_HTTP_TIMEOUT_S = 8.0


def _now() -> datetime:
    return datetime.now()


def _parse_datetime(value: Any) -> datetime | None:
    text = as_clean_text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def freshness_cutoff(lookback_days: int, *, now: datetime | None = None) -> datetime:
    return (now or _now()) - timedelta(days=lookback_days)


def filter_fresh_documents(
    documents: list[dict[str, Any]],
    lookback_days: int,
    *,
    now: datetime | None = None,
    collected_at: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    cutoff = freshness_cutoff(lookback_days, now=now)
    retained: list[dict[str, Any]] = []
    missing_or_unparseable = 0
    old = 0
    collected = collected_at or (now or _now()).isoformat()

    for document in documents:
        published_at = _parse_datetime(document.get("published_at"))
        if published_at is None:
            missing_or_unparseable += 1
            continue
        if published_at < cutoff:
            old += 1
            continue
        with_collection_time = dict(document)
        with_collection_time["collected_at"] = collected
        retained.append(with_collection_time)

    if retained:
        return retained, ""
    if missing_or_unparseable and missing_or_unparseable >= len(documents):
        return [], "all records missing usable published_at"
    if old and old >= len(documents):
        return [], "all records older than lookback window"
    return [], "all records missing usable published_at or older than lookback window"


def _fetch_json(symbol: str, fmp_api_key: str, limit: int) -> tuple[str, Any]:
    try:
        response = httpx.get(
            _STOCK_NEWS_URL,
            params={"symbols": symbol, "limit": limit, "apikey": fmp_api_key},
            timeout=_HTTP_TIMEOUT_S,
        )
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
        return "empty", None
    if response.status_code != 200:
        return "provider_unavailable", response.text

    try:
        return "ok", response.json()
    except ValueError:
        return "provider_unavailable", response.text


def _map_fmp_record(record: Any, symbol: str) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    title = record.get("title") or record.get("headline") or ""
    text = record.get("text") or record.get("summary") or record.get("content") or record.get("snippet") or ""
    if not title and not text:
        return None
    return {
        "title": title,
        "text": text,
        "published_at": record.get("publishedDate") or record.get("date") or record.get("published_at") or "",
        "source": record.get("site") or record.get("publisher") or "FMP Stock News",
        "url": record.get("url") or record.get("link") or "",
        "symbol": record.get("symbol") or symbol,
    }


def collect_stock_news_from_fmp(
    symbol: str,
    lookback_days: int,
    fmp_api_key: str,
    limit: int = 20,
) -> tuple[SourceCollectionResult, list[dict[str, Any]]]:
    if not fmp_api_key:
        return (
            SourceCollectionResult(
                source="news",
                status="credentials_missing",
                doc_count=0,
                elapsed_s=0.0,
                detail="FMP_API_KEY is missing; FMP stock news collection is disabled.",
            ),
            [],
        )

    started_at = _now()
    status, payload = _fetch_json(symbol, fmp_api_key, limit)
    elapsed_s = round((_now() - started_at).total_seconds(), 2)
    if status != "ok":
        if status == "entitlement_required":
            detail = "FMP stock news endpoint returned entitlement_required; check account plan/API entitlement."
        else:
            detail = f"FMP stock news request returned status={status}."
        return (
            SourceCollectionResult("news", status, 0, elapsed_s, detail),
            [],
        )

    mapped_records = [
        mapped
        for mapped in (_map_fmp_record(record, symbol) for record in extract_records(payload))
        if mapped is not None
    ]
    if not mapped_records:
        return (
            SourceCollectionResult("news", "empty", 0, elapsed_s, "FMP stock news returned zero usable records."),
            [],
        )

    normalized = normalize_news_records(mapped_records, symbol, source_hint="fmp_stock_news")
    fresh_documents, freshness_detail = filter_fresh_documents(
        normalized,
        lookback_days,
        now=started_at,
        collected_at=started_at.isoformat(),
    )
    elapsed_s = round((_now() - started_at).total_seconds(), 2)

    if not fresh_documents:
        detail = freshness_detail or "FMP stock news returned records, but none survived normalization."
        return (
            SourceCollectionResult("news", "empty", 0, elapsed_s, detail),
            [],
        )

    return (
        SourceCollectionResult("news", "ok", len(fresh_documents), elapsed_s, "FMP stock news collected."),
        fresh_documents,
    )
