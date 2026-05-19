from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from pipelines.data_mart.models import PriceBar, ProviderFetchResult, UpdateRunResult
from pipelines.data_mart.providers.yfinance_provider import fetch_daily_prices
from pipelines.data_mart.storage import repository


PriceFetcher = Callable[..., ProviderFetchResult]


def update_prices_daily(
    tickers: Iterable[str],
    *,
    market: str = "us",
    start_date: str | None = None,
    end_date: str | None = None,
    dry_run: bool = False,
    db_path: str | Path | None = None,
    fetcher: PriceFetcher = fetch_daily_prices,
) -> UpdateRunResult:
    tickers = [str(t).upper().strip() for t in tickers if str(t).strip()]
    if dry_run:
        return UpdateRunResult(run_id="dry-run", status="dry_run", market=market, provider="yfinance")

    run_id = repository.start_update_run(market=market, provider="yfinance", db_path=db_path)
    result = fetcher(tickers, start_date=start_date, end_date=end_date)
    rows_inserted = 0
    rows_updated = 0
    try:
        if result.records:
            repository.ensure_assets(tickers, market=market, source=result.provider, db_path=db_path)
            counts = repository.upsert_prices(
                [record for record in result.records if isinstance(record, PriceBar)],
                db_path=db_path,
            )
            rows_inserted = counts["inserted"]
            rows_updated = counts["updated"]
        repository.record_provider_status(
            run_id,
            provider=result.provider,
            status=result.status,
            market=market,
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            error_message=result.error,
            details=result.detail,
            started_at=result.started_at,
            finished_at=result.finished_at,
            db_path=db_path,
        )
        final_status = "success" if result.status in {"ok", "partial"} else "failed"
        repository.finish_update_run(
            run_id,
            status=final_status,
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            error_message=result.error,
            db_path=db_path,
        )
        return UpdateRunResult(
            run_id=run_id,
            status=final_status,
            market=market,
            provider=result.provider,
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            error_message=result.error,
            providers=[result],
        )
    except Exception as exc:  # noqa: BLE001
        repository.finish_update_run(run_id, status="failed", error_message=str(exc), db_path=db_path)
        raise
