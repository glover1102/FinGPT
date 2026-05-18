from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from pipelines.data_mart.jobs.update_prices_daily import PriceFetcher, update_prices_daily
from pipelines.data_mart.storage.repository import price_availability


def _clean_tickers(tickers: Iterable[str]) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        ticker = str(raw or "").upper().strip()
        if ticker and ticker not in seen:
            clean.append(ticker)
            seen.add(ticker)
    return clean


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    chunk_size = max(1, int(size or 1))
    for idx in range(0, len(items), chunk_size):
        yield items[idx : idx + chunk_size]


def _hydration_start_date(start_date: str | None, min_rows: int) -> str | None:
    if start_date:
        return start_date
    row_target = max(252, min(5000, int(min_rows or 2)))
    calendar_days = min(365 * 20, max(365, int(row_target * 1.75) + 45))
    return (date.today() - timedelta(days=calendar_days)).isoformat()


def ensure_price_history(
    tickers: Iterable[str],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    min_rows: int = 2,
    hydrate_missing: bool = True,
    max_hydrate_assets: int = 750,
    batch_size: int = 40,
    db_path: str | Path | None = None,
    fetcher: PriceFetcher | None = None,
) -> dict[str, Any]:
    clean = _clean_tickers(tickers)
    before = price_availability(clean, start_date=start_date, end_date=end_date, min_rows=min_rows, db_path=db_path)
    missing = [ticker for ticker in clean if not before.get(ticker, {}).get("available")]
    hydration: dict[str, Any] = {
        "enabled": bool(hydrate_missing),
        "attempted": False,
        "requested_count": len(clean),
        "candidate_count": len(missing),
        "fetched_count": 0,
        "skipped_count": 0,
        "hydrated": [],
        "hydrated_count": 0,
        "still_unavailable": list(missing),
        "still_unavailable_count": len(missing),
        "failed_tickers": {},
        "run_ids": [],
        "rows_inserted": 0,
        "rows_updated": 0,
        "start_date": start_date,
        "end_date": end_date,
        "min_rows": max(1, int(min_rows or 1)),
    }
    if not hydrate_missing or not missing:
        return {"availability": before, "hydration": hydration}

    limit = max(0, int(max_hydrate_assets or 0))
    candidates = missing[:limit] if limit else []
    skipped = missing[limit:] if limit and len(missing) > limit else missing if not limit else []
    hydration["attempted"] = bool(candidates)
    hydration["fetched_count"] = len(candidates)
    hydration["skipped_count"] = len(skipped)
    hydration["skipped"] = skipped
    fetch_start = _hydration_start_date(start_date, int(min_rows or 2))
    hydration["start_date"] = fetch_start
    for batch in _chunks(candidates, batch_size):
        update_kwargs: dict[str, Any] = {
            "market": "mixed",
            "start_date": fetch_start,
            "end_date": end_date,
            "db_path": db_path,
        }
        if fetcher is not None:
            update_kwargs["fetcher"] = fetcher
        result = update_prices_daily(batch, **update_kwargs)
        hydration["run_ids"].append(result.run_id)
        hydration["rows_inserted"] += int(result.rows_inserted or 0)
        hydration["rows_updated"] += int(result.rows_updated or 0)
        for provider in result.providers:
            failed = provider.detail.get("failed_tickers") if isinstance(provider.detail, dict) else None
            if isinstance(failed, dict):
                hydration["failed_tickers"].update({str(k).upper(): str(v) for k, v in failed.items()})

    after = price_availability(clean, start_date=start_date, end_date=end_date, min_rows=min_rows, db_path=db_path)
    hydrated = [ticker for ticker in missing if after.get(ticker, {}).get("available")]
    still_unavailable = [ticker for ticker in missing if not after.get(ticker, {}).get("available")]
    hydration["hydrated"] = hydrated
    hydration["hydrated_count"] = len(hydrated)
    hydration["still_unavailable"] = still_unavailable
    hydration["still_unavailable_count"] = len(still_unavailable)
    return {"availability": after, "hydration": hydration}
