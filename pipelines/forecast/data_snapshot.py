from __future__ import annotations

from typing import Any

from core.schemas.forecast import ForecastDatasetConfig
from pipelines.data_mart.storage import repository
from pipelines.forecast.common import stable_hash
from pipelines.forecast.data_loader import FORECAST_MACRO_SERIES


def build_data_snapshot(
    *,
    dataset_config: ForecastDatasetConfig,
    price_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    feature_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feature_names = list((feature_payload or {}).get("feature_names") or [])
    base = {
        "schema_version": "forecast_data_snapshot_v1",
        "ticker": dataset_config.ticker,
        "benchmark": dataset_config.benchmark,
        "data_source": dataset_config.data_source,
        "adjusted_price": dataset_config.adjusted_price,
        "frequency": dataset_config.frequency,
        "requested_range": {
            "start_date": dataset_config.start_date,
            "end_date": dataset_config.end_date,
            "max_rows": dataset_config.max_rows,
        },
        "price_coverage": _series_coverage(price_rows),
        "benchmark_coverage": _series_coverage(benchmark_rows),
        "macro_coverage": _macro_coverage() if dataset_config.include_macro else {"status": "not_requested", "series": []},
        "feature_schema": {
            "feature_count": len(feature_names),
            "feature_names": feature_names,
            "feature_schema_hash": stable_hash(feature_names, length=24),
        },
    }
    base["source_coverage_hash"] = stable_hash(
        {
            "price": _compact_market_rows(price_rows),
            "benchmark": _compact_market_rows(benchmark_rows),
            "macro": base["macro_coverage"],
            "feature_schema_hash": base["feature_schema"]["feature_schema_hash"],
        },
        length=32,
    )
    base["data_snapshot_id"] = f"ds_{stable_hash(base, length=20)}"
    return base


def _series_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "unavailable",
            "rows": 0,
            "start_date": "",
            "end_date": "",
            "source_counts": {},
            "coverage_hash": stable_hash([], length=24),
        }
    sorted_rows = sorted(rows, key=lambda item: str(item.get("date") or ""))
    source_counts: dict[str, int] = {}
    for row in sorted_rows:
        source = str(row.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    return {
        "status": "ok",
        "rows": len(sorted_rows),
        "start_date": str(sorted_rows[0].get("date") or ""),
        "end_date": str(sorted_rows[-1].get("date") or ""),
        "source_counts": source_counts,
        "coverage_hash": stable_hash(_compact_market_rows(sorted_rows), length=24),
    }


def _macro_coverage() -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    for series_id in FORECAST_MACRO_SERIES:
        latest = repository.latest_macro(series_id)
        if not latest:
            series.append({"series_id": series_id, "status": "unavailable", "latest_date": "", "source": ""})
            continue
        series.append(
            {
                "series_id": series_id,
                "status": "ok",
                "latest_date": str(latest.get("date") or ""),
                "source": str(latest.get("source") or "unknown"),
            }
        )
    available = sum(1 for item in series if item["status"] == "ok")
    status = "ok" if available == len(series) else "partial" if available else "unavailable"
    return {
        "status": status,
        "available": available,
        "total": len(series),
        "series": series,
        "coverage_hash": stable_hash(series, length=24),
    }


def _compact_market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ticker": row.get("ticker"),
            "date": row.get("date"),
            "price": row.get("price"),
            "close": row.get("close"),
            "adjusted_close": row.get("adjusted_close"),
            "source": row.get("source"),
        }
        for row in rows
    ]
