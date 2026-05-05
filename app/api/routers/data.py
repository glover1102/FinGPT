from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from pipelines.data_mart.storage.repository import data_health as data_mart_health
from pipelines.data_mart.storage.repository import get_prices as data_mart_get_prices


router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.get("/health")
async def data_health() -> dict[str, Any]:
    """Structured data mart health, update history, provider status, and quality checks."""

    payload = await asyncio.to_thread(data_mart_health)
    provider_rows = payload.get("recent_provider_status") or []
    quality_rows = payload.get("recent_quality_checks") or []
    failed = [row for row in provider_rows if str(row.get("status") or "").lower() in {"failed", "error"}]
    stale = [row for row in quality_rows if str(row.get("status") or "").lower() in {"warn", "fail"}]
    payload["summary"] = {
        "provider_rows": len(provider_rows),
        "failed_provider_rows": len(failed),
        "quality_rows": len(quality_rows),
        "stale_or_failed_quality_rows": len(stale),
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
