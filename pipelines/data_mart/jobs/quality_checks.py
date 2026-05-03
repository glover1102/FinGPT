from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pipelines.data_mart.storage import repository
from pipelines.data_mart.storage.db import connect, init_db

_MACRO_STALE_DAYS_BY_SERIES = {
    # CPI is released monthly with a normal publication lag.
    "CPIAUCSL": 95,
    # Broad dollar index is weekly and may lag by more than one trading week.
    "DTWEXBGS": 14,
}


def _parse_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def run_data_quality_checks(
    *,
    db_path: str | Path | None = None,
    run_id: str | None = None,
    stale_price_days: int = 5,
    stale_macro_days: int = 7,
) -> list[dict[str, Any]]:
    init_db(db_path)
    checks: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    with connect(db_path) as conn:
        duplicate_rows = conn.execute(
            """
            SELECT ticker, date, source, COUNT(*) AS c
            FROM prices_daily
            GROUP BY ticker, date, source
            HAVING c > 1
            """
        ).fetchall()
        _append_check(
            checks,
            "prices_no_duplicate_dates",
            "pass" if not duplicate_rows else "fail",
            "price",
            "",
            0 if not duplicate_rows else len(duplicate_rows),
            0,
            "No duplicate price rows by ticker/date/source." if not duplicate_rows else "Duplicate price rows detected.",
        )

        price_rows = conn.execute(
            "SELECT ticker, MAX(date) AS latest_date FROM prices_daily GROUP BY ticker"
        ).fetchall()
        for row in price_rows:
            latest = _parse_date(row["latest_date"])
            age = (today - latest).days if latest else 9999
            _append_check(
                checks,
                "prices_freshness",
                "pass" if age <= stale_price_days else "warn",
                "ticker",
                row["ticker"],
                age,
                stale_price_days,
                f"{row['ticker']} latest price age is {age} days.",
            )

        invalid_close_rows = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM prices_daily
            WHERE close IS NULL
            """
        ).fetchone()["c"]
        _append_check(
            checks,
            "prices_close_not_null",
            "pass" if invalid_close_rows == 0 else "warn",
            "price",
            "",
            invalid_close_rows,
            0,
            "All stored price rows have close values." if invalid_close_rows == 0 else "Some stored price rows have missing close values.",
        )

        missing_adjusted = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM prices_daily
            WHERE close IS NOT NULL AND adjusted_close IS NULL AND (ticker NOT LIKE '%.KS')
            """
        ).fetchone()["c"]
        _append_check(
            checks,
            "prices_adjusted_close_not_null_for_us_equities",
            "pass" if missing_adjusted == 0 else "warn",
            "price",
            "",
            missing_adjusted,
            0,
            "US equity adjusted_close fields are populated." if missing_adjusted == 0 else "Some US-like tickers have missing adjusted_close.",
        )

        macro_rows = conn.execute(
            "SELECT series_id, MAX(date) AS latest_date FROM macro_observations GROUP BY series_id"
        ).fetchall()
        for row in macro_rows:
            latest = _parse_date(row["latest_date"])
            age = (today - latest).days if latest else 9999
            threshold = _macro_stale_days(str(row["series_id"]), stale_macro_days)
            _append_check(
                checks,
                "macro_series_freshness",
                "pass" if age <= threshold else "warn",
                "macro_series",
                row["series_id"],
                age,
                threshold,
                f"{row['series_id']} latest observation age is {age} days; threshold is {threshold} days.",
            )

    for check in checks:
        repository.record_quality_check(
            run_id=run_id,
            check_name=check["check_name"],
            status=check["status"],
            entity_type=check["entity_type"],
            entity_id=check["entity_id"],
            observed_value=check["observed_value"],
            threshold_value=check["threshold_value"],
            message=check["message"],
            db_path=db_path,
        )
    return checks


def _macro_stale_days(series_id: str, default_days: int) -> int:
    return int(_MACRO_STALE_DAYS_BY_SERIES.get(series_id.upper().strip(), default_days))


def _append_check(
    checks: list[dict[str, Any]],
    check_name: str,
    status: str,
    entity_type: str,
    entity_id: str,
    observed_value: float | int,
    threshold_value: float | int,
    message: str,
) -> None:
    checks.append(
        {
            "check_name": check_name,
            "status": status,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "observed_value": float(observed_value),
            "threshold_value": float(threshold_value),
            "message": message,
        }
    )
