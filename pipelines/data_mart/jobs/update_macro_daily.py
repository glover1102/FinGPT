from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from pipelines.data_mart.models import MacroObservation, ProviderFetchResult, UpdateRunResult
from pipelines.data_mart.providers.fred_provider import fetch_macro_series
from pipelines.data_mart.storage import repository

MacroFetcher = Callable[..., ProviderFetchResult]


DEFAULT_US_MACRO_SERIES = ("DGS2", "DGS10", "T10Y2Y", "DFF", "CPIAUCSL", "DTWEXBGS")


def update_macro_daily(
    series_ids: Iterable[str] = DEFAULT_US_MACRO_SERIES,
    *,
    market: str = "us",
    start_date: str | None = None,
    end_date: str | None = None,
    dry_run: bool = False,
    db_path: str | Path | None = None,
    fetcher: MacroFetcher = fetch_macro_series,
) -> UpdateRunResult:
    series_ids = [str(s).upper().strip() for s in series_ids if str(s).strip()]
    if dry_run:
        return UpdateRunResult(run_id="dry-run", status="dry_run", market=market, provider="fred")

    run_id = repository.start_update_run(market=market, provider="fred", db_path=db_path)
    result = fetcher(series_ids, start_date=start_date, end_date=end_date)
    rows_inserted = 0
    rows_updated = 0
    try:
        if result.records:
            counts = repository.upsert_macro_observations(
                [record for record in result.records if isinstance(record, MacroObservation)],
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
        final_status = "success" if result.status in {"ok", "partial", "credentials_missing"} else "failed"
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
