from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Iterable

from pipelines.data_mart.models import MacroObservation, ProviderFetchResult, UpdateRunResult, utc_now_iso
from pipelines.data_mart.providers.fred_provider import fetch_macro_series
from pipelines.data_mart.storage import repository
from pipelines.macro.providers.ecos import EcosProvider
from pipelines.macro.providers.oecd import OecdProvider
from pipelines.macro.providers.worldbank import WorldBankProvider
from pipelines.macro.providers.yahoo import YahooFinanceProvider
from pipelines.macro.series_registry import get_series_definition, list_macro_series

MacroFetcher = Callable[..., ProviderFetchResult]

DEFAULT_US_MACRO_SERIES = tuple(
    item.provider_series_id
    for item in list_macro_series()
    if item.enabled and item.provider == "fred"
)
DEFAULT_MACRO_PLATFORM_SERIES = tuple(item.series_id for item in list_macro_series())
DEFAULT_MACRO_REFRESH_LOOKBACK_DAYS = 365 * 5
_LIVE_PROVIDER_FACTORIES = MappingProxyType(
    {
        "ecos": EcosProvider,
        "oecd": OecdProvider,
        "worldbank": WorldBankProvider,
        "yahoo": YahooFinanceProvider,
    }
)


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


def _default_start_date(lookback_days: int) -> str:
    days = max(1, int(lookback_days or DEFAULT_MACRO_REFRESH_LOOKBACK_DAYS))
    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


def _selected_definitions(
    series_ids: Iterable[str] | None,
    *,
    providers: Iterable[str] | None = None,
    include_disabled: bool = False,
):
    provider_filter = {str(item or "").strip().lower() for item in (providers or []) if str(item or "").strip()}
    if series_ids:
        definitions = []
        for raw in series_ids:
            key = str(raw or "").upper().strip()
            if not key:
                continue
            definition = get_series_definition(key)
            if definition.enabled or include_disabled:
                definitions.append(definition)
    else:
        definitions = list_macro_series(include_disabled=include_disabled)
    if provider_filter:
        definitions = [item for item in definitions if str(item.provider or "").lower() in provider_filter]
    return definitions


def _stored_observations(definition, result) -> list[MacroObservation]:
    out: list[MacroObservation] = []
    for item in result.observations:
        if item.value is None:
            continue
        collected_at = str((item.metadata or {}).get("collected_at") or "")
        out.append(
            MacroObservation(
                series_id=definition.series_id,
                date=item.date,
                value=item.value,
                source=item.source or result.provider,
                title=definition.display_name,
                units=definition.unit,
                frequency=definition.frequency,
                collected_at=collected_at or utc_now_iso(),
            )
        )
    return out


def _provider_fetch_result(provider: str, status: str, *, rows: int = 0, error: str | None = None, detail: dict | None = None) -> ProviderFetchResult:
    return ProviderFetchResult(
        provider=provider,
        status=status,
        rows=rows,
        records=[],
        error=error,
        detail=detail or {},
    )


def update_macro_platform_data(
    series_ids: Iterable[str] | None = None,
    *,
    providers: Iterable[str] | None = None,
    include_disabled: bool = False,
    market: str = "global",
    start_date: str | None = None,
    end_date: str | None = None,
    lookback_days: int = DEFAULT_MACRO_REFRESH_LOOKBACK_DAYS,
    dry_run: bool = False,
    db_path: str | Path | None = None,
) -> UpdateRunResult:
    """Refresh every enabled Macro tab series into the local data mart.

    The legacy ``update_macro_daily`` path is FRED-only. This job follows the
    Macro registry and stores FRED economic releases plus Yahoo market proxies
    under their UI-facing series ids so the Macro tab can read a coherent cache.
    """

    definitions = _selected_definitions(series_ids, providers=providers, include_disabled=include_disabled)
    if not definitions:
        return UpdateRunResult(
            run_id="dry-run" if dry_run else "no-series",
            status="dry_run" if dry_run else "empty",
            market=market,
            provider="macro_platform",
            providers=[_provider_fetch_result("macro_platform", "empty", detail={"reason": "no series selected"})],
        )
    effective_start = start_date or _default_start_date(lookback_days)
    if dry_run:
        return UpdateRunResult(
            run_id="dry-run",
            status="dry_run",
            market=market,
            provider="macro_platform",
            providers=[
                _provider_fetch_result(
                    "macro_platform",
                    "dry_run",
                    rows=len(definitions),
                    detail={
                        "series": [item.series_id for item in definitions],
                        "providers": sorted({item.provider for item in definitions}),
                        "start_date": effective_start,
                        "end_date": end_date,
                    },
                )
            ],
        )

    run_id = repository.start_update_run(market=market, provider="macro_platform", db_path=db_path)
    rows_inserted = 0
    rows_updated = 0
    provider_results: list[ProviderFetchResult] = []
    try:
        fred_definitions = [item for item in definitions if item.provider == "fred"]
        if fred_definitions:
            by_provider_id = {item.provider_series_id.upper(): item for item in fred_definitions}
            fred_result = fetch_macro_series(
                [item.provider_series_id for item in fred_definitions],
                start_date=effective_start,
                end_date=end_date,
                allow_csv_fallback=True,
            )
            records: list[MacroObservation] = []
            for record in fred_result.records:
                if not isinstance(record, MacroObservation):
                    continue
                definition = by_provider_id.get(record.series_id.upper())
                if definition is None:
                    continue
                records.append(
                    MacroObservation(
                        series_id=definition.series_id,
                        date=record.date,
                        value=record.value,
                        source=record.source or fred_result.provider,
                        title=definition.display_name,
                        units=definition.unit,
                        frequency=definition.frequency,
                        collected_at=record.collected_at,
                    )
                )
            counts = repository.upsert_macro_observations(records, db_path=db_path) if records else {"inserted": 0, "updated": 0}
            rows_inserted += counts["inserted"]
            rows_updated += counts["updated"]
            repository.record_provider_status(
                run_id,
                provider=fred_result.provider,
                status=fred_result.status,
                market=market,
                rows_inserted=counts["inserted"],
                rows_updated=counts["updated"],
                error_message=fred_result.error,
                details={
                    **fred_result.detail,
                    "series_count": len(fred_definitions),
                    "stored_series": sorted({record.series_id for record in records}),
                },
                started_at=fred_result.started_at,
                finished_at=fred_result.finished_at,
                db_path=db_path,
            )
            provider_results.append(
                _provider_fetch_result(
                    fred_result.provider,
                    fred_result.status,
                    rows=len(records),
                    error=fred_result.error,
                    detail={**fred_result.detail, "series_count": len(fred_definitions)},
                )
            )

        for definition in [item for item in definitions if item.provider != "fred"]:
            provider_factory = _LIVE_PROVIDER_FACTORIES.get(definition.provider)
            provider_name = definition.provider or "unknown"
            if provider_factory is None:
                status = "unavailable"
                error = f"provider_not_configured:{provider_name}"
                repository.record_provider_status(
                    run_id,
                    provider=provider_name,
                    status=status,
                    market=market,
                    ticker=definition.series_id,
                    error_message=error,
                    details={"series_id": definition.series_id},
                    db_path=db_path,
                )
                provider_results.append(_provider_fetch_result(provider_name, status, error=error, detail={"series_id": definition.series_id}))
                continue
            provider = provider_factory()
            if not provider.is_available():
                status = "unavailable"
                error = f"{provider.provider_name}_unavailable"
                repository.record_provider_status(
                    run_id,
                    provider=provider.provider_name,
                    status=status,
                    market=market,
                    ticker=definition.series_id,
                    error_message=error,
                    details={"series_id": definition.series_id},
                    db_path=db_path,
                )
                provider_results.append(_provider_fetch_result(provider.provider_name, status, error=error, detail={"series_id": definition.series_id}))
                continue
            result = provider.fetch_series(definition, start_date=effective_start, end_date=end_date)
            records = _stored_observations(definition, result)
            counts = repository.upsert_macro_observations(records, db_path=db_path) if records else {"inserted": 0, "updated": 0}
            rows_inserted += counts["inserted"]
            rows_updated += counts["updated"]
            status = result.data_quality.status if records else "unavailable"
            error = "; ".join(result.data_quality.errors) or None
            repository.record_provider_status(
                run_id,
                provider=result.provider,
                status=status,
                market=market,
                ticker=definition.series_id,
                rows_inserted=counts["inserted"],
                rows_updated=counts["updated"],
                error_message=error,
                details={
                    "series_id": definition.series_id,
                    "provider_series_id": definition.provider_series_id,
                    "latest_date": records[-1].date if records else None,
                    "quality": result.data_quality.model_dump(mode="json"),
                },
                db_path=db_path,
            )
            provider_results.append(
                _provider_fetch_result(
                    result.provider,
                    status,
                    rows=len(records),
                    error=error,
                    detail={"series_id": definition.series_id, "latest_date": records[-1].date if records else None},
                )
            )

        total_rows = rows_inserted + rows_updated
        statuses = {item.status for item in provider_results}
        problematic = statuses - {"ok", "partial"}
        final_status = "success" if total_rows and not problematic else ("partial" if total_rows else "failed")
        repository.finish_update_run(
            run_id,
            status=final_status,
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            error_message="; ".join(sorted({item.error or item.status for item in provider_results if item.status not in {"ok", "partial"}})) or None,
            db_path=db_path,
        )
        return UpdateRunResult(
            run_id=run_id,
            status=final_status,
            market=market,
            provider="macro_platform",
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            providers=provider_results,
        )
    except Exception as exc:  # noqa: BLE001
        repository.finish_update_run(run_id, status="failed", error_message=str(exc), db_path=db_path)
        raise
