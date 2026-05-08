from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from pipelines.data_mart.storage.repository import data_health as data_mart_health
from pipelines.data_mart.storage.repository import latest_fundamentals as data_mart_latest_fundamentals
from pipelines.data_mart.storage.repository import get_prices as data_mart_get_prices


router = APIRouter(prefix="/api/v1/data", tags=["data"])

_SEC_EMPTY_IS_COVERED_TICKERS = {
    "BTC-USD",
    "ETH-USD",
    "GLD",
    "HYG",
    "QQQ",
    "SPY",
    "TLT",
    "USO",
}


def _provider_empty_is_covered(row: dict[str, Any]) -> bool:
    """Return true for empty provider rows that are valid coverage, not failures."""

    status = str(row.get("status") or "").lower()
    if status != "empty" or row.get("error_message"):
        return False
    provider = str(row.get("provider") or "").lower()
    ticker = str(row.get("ticker") or "").upper()
    if provider == "sec_filings":
        return ticker in _SEC_EMPTY_IS_COVERED_TICKERS
    if provider == "google_news_rss":
        return True
    return False


def _normalize_provider_status(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if _provider_empty_is_covered(normalized):
        normalized["raw_status"] = normalized.get("status")
        normalized["status"] = "ok"
        normalized["coverage_status"] = "covered_empty"
        normalized["coverage_note"] = (
            "Provider returned no rows, but the asset is covered by price, macro, filing, or news evidence elsewhere."
        )
    return normalized


@router.get("/health")
async def data_health() -> dict[str, Any]:
    """Structured data mart health, update history, provider status, and quality checks."""

    payload = await asyncio.to_thread(data_mart_health)
    raw_provider_rows = payload.get("recent_provider_status") or []
    provider_rows = [_normalize_provider_status(row) for row in raw_provider_rows]
    payload["recent_provider_status"] = provider_rows
    quality_rows = payload.get("recent_quality_checks") or []
    failed = [row for row in provider_rows if str(row.get("status") or "").lower() in {"failed", "error"}]
    stale = [row for row in quality_rows if str(row.get("status") or "").lower() in {"warn", "fail"}]
    covered_empty = [row for row in provider_rows if row.get("coverage_status") == "covered_empty"]
    counts = payload.get("table_counts") or {}
    fundamentals_rows = int(counts.get("fundamentals_snapshots") or 0)
    payload["summary"] = {
        "provider_rows": len(provider_rows),
        "failed_provider_rows": len(failed),
        "covered_empty_provider_rows": len(covered_empty),
        "quality_rows": len(quality_rows),
        "stale_or_failed_quality_rows": len(stale),
        "fundamentals_rows": fundamentals_rows,
        "fundamentals_available": fundamentals_rows > 0,
        "decision_status": "failed" if failed else ("partial" if stale else "ok"),
    }
    return payload


@router.get("/prices/{ticker}")
async def data_prices(ticker: str, limit: int = 252) -> dict[str, Any]:
    """Return normalized daily prices from the structured data mart."""

    clean_ticker = str(ticker or "").strip().upper()
    if not clean_ticker:
        raise HTTPException(status_code=422, detail="ticker is required")
    limit = max(1, min(int(limit or 252), 5000))
    rows = await asyncio.to_thread(data_mart_get_prices, clean_ticker, limit=limit)
    latest = rows[-1] if rows else None
    return {
        "status": "ok" if rows else "empty",
        "ticker": clean_ticker,
        "count": len(rows),
        "latest": latest,
        "items": rows,
    }


@router.get("/fundamentals/{ticker}")
async def data_fundamentals(ticker: str) -> dict[str, Any]:
    """Return normalized fundamentals, valuation, and financial snapshot data."""

    clean_ticker = str(ticker or "").strip().upper()
    if not clean_ticker:
        raise HTTPException(status_code=422, detail="ticker is required")
    item = await asyncio.to_thread(data_mart_latest_fundamentals, clean_ticker)
    if not item:
        return {
            "status": "empty",
            "ticker": clean_ticker,
            "message": "normalized fundamentals snapshot is not available yet",
        }
    return {"status": "ok", **item}
