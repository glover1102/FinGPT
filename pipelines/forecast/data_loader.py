from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta, timezone

from core.schemas.forecast import DataQualityResult, ForecastDatasetConfig
from pipelines.data_mart.jobs.update_macro_daily import DEFAULT_US_MACRO_SERIES, update_macro_daily
from pipelines.data_mart.jobs.update_prices_daily import update_prices_daily
from pipelines.data_mart.storage import repository
from pipelines.forecast.common import clean_ticker, price_from_row


FORECAST_MACRO_SERIES = tuple(dict.fromkeys((*DEFAULT_US_MACRO_SERIES, "VIXCLS")))


def load_price_rows(config: ForecastDatasetConfig) -> list[dict[str, Any]]:
    rows = repository.get_prices(config.ticker, limit=config.max_rows)
    rows = _filter_rows(rows, start_date=config.start_date, end_date=config.end_date)
    clean: list[dict[str, Any]] = []
    for row in rows:
        price = price_from_row(row, adjusted=config.adjusted_price)
        clean.append({**row, "price": price})
    return clean


def load_benchmark_rows(config: ForecastDatasetConfig) -> list[dict[str, Any]]:
    benchmark = clean_ticker(config.benchmark)
    if benchmark == clean_ticker(config.ticker):
        return load_price_rows(config)
    rows = repository.get_prices(benchmark, limit=config.max_rows)
    rows = _filter_rows(rows, start_date=config.start_date, end_date=config.end_date)
    return [{**row, "price": price_from_row(row, adjusted=config.adjusted_price)} for row in rows]


def preview_dataset(config: ForecastDatasetConfig) -> dict[str, Any]:
    rows = load_price_rows(config)
    benchmark_rows = load_benchmark_rows(config)
    quality = data_quality(rows, benchmark_rows=benchmark_rows, include_macro=config.include_macro)
    preview_rows = rows[-10:]
    return {
        "status": "success" if quality.status in {"ok", "partial"} else "partial",
        "ticker": config.ticker,
        "benchmark": config.benchmark,
        "rows": len(rows),
        "preview": preview_rows,
        "data_quality": quality.model_dump(mode="json"),
        "warnings": quality.warnings,
        "generated_at": "",
    }


def hydrate_dataset(
    config: ForecastDatasetConfig,
    *,
    include_benchmark: bool = True,
    include_macro: bool | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    tickers = [clean_ticker(config.ticker)]
    benchmark = clean_ticker(config.benchmark)
    if include_benchmark and benchmark and benchmark not in tickers:
        tickers.append(benchmark)
    hydrate_start = start_date or config.start_date or _default_start_date()
    hydrate_end = end_date or config.end_date
    price_result = update_prices_daily(tickers, market="us", start_date=hydrate_start, end_date=hydrate_end)
    macro_result = None
    should_hydrate_macro = config.include_macro if include_macro is None else bool(include_macro)
    if should_hydrate_macro:
        macro_result = update_macro_daily(FORECAST_MACRO_SERIES, market="us", start_date=hydrate_start, end_date=hydrate_end)
    preview = preview_dataset(config)
    return {
        "status": "success" if preview.get("data_quality", {}).get("status") in {"ok", "partial"} else "partial",
        "tickers": tickers,
        "start_date": hydrate_start,
        "end_date": hydrate_end,
        "price_update": price_result.__dict__,
        "macro_update": macro_result.__dict__ if macro_result is not None else None,
        "dataset_preview": preview,
    }


def data_quality(
    rows: list[dict[str, Any]],
    *,
    benchmark_rows: list[dict[str, Any]] | None = None,
    include_macro: bool = False,
) -> DataQualityResult:
    if not rows:
        return DataQualityResult(
            status="unavailable",
            adjusted_price_status="unknown",
            benchmark_availability="unknown",
            macro_availability="unavailable" if include_macro else "not_requested",
            warnings=["price_data_unavailable"],
        )
    price_missing = sum(1 for row in rows if row.get("price") is None)
    adjusted_missing = sum(1 for row in rows if row.get("adjusted_close") is None)
    ratio = price_missing / max(len(rows), 1)
    warnings: list[str] = []
    if len(rows) < 120:
        warnings.append("insufficient_history_for_walk_forward")
    if ratio > 0.1:
        warnings.append("excessive_missing_prices")
    benchmark_status = "ok" if benchmark_rows else "unavailable"
    if benchmark_rows is not None and len(benchmark_rows) < max(2, len(rows) // 2):
        benchmark_status = "partial" if benchmark_rows else "unavailable"
        warnings.append("benchmark_history_partial")
    adjusted_status = "ok" if adjusted_missing == 0 else ("partial" if adjusted_missing < len(rows) else "unavailable")
    status = "ok"
    if len(rows) < 80:
        status = "insufficient"
    elif ratio > 0.25:
        status = "unavailable"
    elif warnings:
        status = "partial"
    macro_status = "not_requested"
    if include_macro:
        macro_available_count = sum(1 for series_id in FORECAST_MACRO_SERIES if repository.latest_macro(series_id))
        if macro_available_count == len(FORECAST_MACRO_SERIES):
            macro_status = "ok"
        elif macro_available_count:
            macro_status = "partial"
            warnings.append("macro_context_partial")
        else:
            macro_status = "unavailable"
            warnings.append("macro_context_unavailable")
    return DataQualityResult(
        status=status,
        rows=len(rows),
        start_date=str(rows[0].get("date") or ""),
        end_date=str(rows[-1].get("date") or ""),
        missing_values=price_missing,
        missing_ratio=round(ratio, 6),
        adjusted_price_status=adjusted_status,
        benchmark_availability=benchmark_status,
        macro_availability=macro_status,
        warnings=warnings,
    )


def _filter_rows(rows: list[dict[str, Any]], *, start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        date = str(row.get("date") or "")
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        out.append(row)
    return sorted(out, key=lambda item: str(item.get("date") or ""))


def _default_start_date() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=365 * 5)).isoformat()
