from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any, Callable, Iterable

import httpx

from core.config.settings import load_settings
from pipelines.data_mart.models import MacroObservation, ProviderFetchResult, utc_now_iso

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _clean_float(value: Any) -> float | None:
    if value in (None, "", "."):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_text(value: str | date | None) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "").strip()


def _in_window(date_text: str, start_date: str | date | None, end_date: str | date | None) -> bool:
    start = _date_text(start_date)
    end = _date_text(end_date)
    if start and date_text < start:
        return False
    if end and date_text > end:
        return False
    return True


def _fetch_macro_series_csv(
    series_ids: Iterable[str],
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    http_get: Callable[[str, dict[str, Any]], Any] | None = None,
) -> ProviderFetchResult:
    provider = "fred_csv"
    started = utc_now_iso()
    records: list[MacroObservation] = []
    failed: dict[str, str] = {}
    client: httpx.Client | None = None
    try:
        if http_get is None:
            client = httpx.Client(timeout=12.0)
            http_get = lambda url, params: client.get(url, params=params)  # noqa: E731
        for raw in series_ids:
            series_id = str(raw or "").upper().strip()
            if not series_id:
                continue
            try:
                response = http_get(_FRED_CSV_BASE, {"id": series_id})
            except Exception as exc:  # noqa: BLE001
                failed[series_id] = str(exc)
                continue
            status_code = int(getattr(response, "status_code", 200))
            if status_code == 429:
                failed[series_id] = "rate_limited"
                continue
            if status_code != 200:
                failed[series_id] = f"HTTP {status_code}"
                continue
            text = str(getattr(response, "text", "") or "")
            reader = csv.DictReader(StringIO(text))
            fieldnames = [str(item or "").strip() for item in (reader.fieldnames or [])]
            value_field = series_id if series_id in fieldnames else (fieldnames[1] if len(fieldnames) > 1 else "")
            if not value_field:
                failed[series_id] = "csv_missing_value_column"
                continue
            row_count = 0
            for row in reader:
                date_value = str(row.get("observation_date") or row.get("DATE") or "").strip()
                if not date_value or not _in_window(date_value, start_date, end_date):
                    continue
                value = _clean_float(row.get(value_field))
                if value is None:
                    continue
                row_count += 1
                records.append(
                    MacroObservation(
                        series_id=series_id,
                        date=date_value,
                        value=value,
                        source=provider,
                        collected_at=utc_now_iso(),
                    )
                )
            if not row_count:
                failed[series_id] = "empty"
    finally:
        if client is not None:
            client.close()

    if records:
        status = "partial" if failed else "ok"
    else:
        status = "empty" if not failed else "failed"
    return ProviderFetchResult(
        provider=provider,
        status=status,
        rows=len(records),
        records=records,
        error="; ".join(f"{sid}: {msg}" for sid, msg in sorted(failed.items())) or None,
        detail={
            "failed_series": failed,
            "requested_series": [str(s).upper().strip() for s in series_ids if str(s).strip()],
            "source_endpoint": _FRED_CSV_BASE,
        },
        started_at=started,
        finished_at=utc_now_iso(),
    )


def fetch_macro_series(
    series_ids: Iterable[str],
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    api_key: str | None = None,
    allow_csv_fallback: bool = False,
    http_get: Callable[[str, dict[str, Any]], Any] | None = None,
) -> ProviderFetchResult:
    provider = "fred"
    started = utc_now_iso()
    key = api_key if api_key is not None else getattr(load_settings(), "fred_api_key", "")
    if not key:
        if allow_csv_fallback:
            return _fetch_macro_series_csv(series_ids, start_date=start_date, end_date=end_date, http_get=http_get)
        return ProviderFetchResult(
            provider=provider,
            status="credentials_missing",
            error="FRED_API_KEY is missing.",
            started_at=started,
            finished_at=utc_now_iso(),
        )

    records: list[MacroObservation] = []
    failed: dict[str, str] = {}
    fallback_recovered: set[str] = set()
    fallback_provider: str | None = None
    external_http_get = http_get is not None
    client: httpx.Client | None = None
    try:
        if http_get is None:
            client = httpx.Client(timeout=8.0)
            http_get = lambda url, params: client.get(url, params=params)  # noqa: E731
        for raw in series_ids:
            series_id = str(raw or "").upper().strip()
            if not series_id:
                continue
            params: dict[str, Any] = {
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
            }
            if start_date:
                params["observation_start"] = str(start_date)
            if end_date:
                params["observation_end"] = str(end_date)
            try:
                response = http_get(_FRED_BASE, params)
            except Exception as exc:  # noqa: BLE001
                failed[series_id] = str(exc)
                continue
            status_code = int(getattr(response, "status_code", 200))
            if status_code in {401, 403}:
                failed[series_id] = "credentials_missing"
                continue
            if status_code == 429:
                failed[series_id] = "rate_limited"
                continue
            if status_code != 200:
                failed[series_id] = f"HTTP {status_code}"
                continue
            try:
                payload = response.json()
            except Exception as exc:  # noqa: BLE001
                failed[series_id] = f"json parse failed: {exc}"
                continue
            observations = payload.get("observations") if isinstance(payload, dict) else []
            for row in observations or []:
                if not isinstance(row, dict):
                    continue
                value = _clean_float(row.get("value"))
                date_text = str(row.get("date") or "")
                if not date_text or value is None:
                    continue
                records.append(
                    MacroObservation(
                        series_id=series_id,
                        date=date_text,
                        value=value,
                        source=provider,
                        collected_at=utc_now_iso(),
                    )
                )
            if not observations:
                failed[series_id] = "empty"
    finally:
        if client is not None:
            client.close()

    if failed and allow_csv_fallback:
        fallback_result = _fetch_macro_series_csv(
            failed.keys(),
            start_date=start_date,
            end_date=end_date,
            http_get=http_get if external_http_get else None,
        )
        fallback_provider = fallback_result.provider
        fallback_recovered = {record.series_id.upper() for record in fallback_result.records if isinstance(record, MacroObservation)}
        if fallback_result.records:
            records.extend(fallback_result.records)
        for series_id in fallback_recovered:
            failed.pop(series_id, None)
        fallback_detail = fallback_result.detail if isinstance(fallback_result.detail, dict) else {}
        fallback_failed = fallback_detail.get("failed_series")
        if isinstance(fallback_failed, dict):
            for series_id, message in fallback_failed.items():
                failed[str(series_id).upper()] = f"csv_fallback:{message}"
        elif fallback_result.error:
            for series_id in failed:
                failed[series_id] = f"{failed[series_id]}; csv_fallback:{fallback_result.error}"

    if records:
        status = "partial" if failed else "ok"
    else:
        status = "empty" if not failed else "failed"
    return ProviderFetchResult(
        provider=provider,
        status=status,
        rows=len(records),
        records=records,
        error="; ".join(f"{sid}: {msg}" for sid, msg in sorted(failed.items())) or None,
        detail={
            "failed_series": failed,
            "requested_series": [str(s).upper().strip() for s in series_ids if str(s).strip()],
            "fallback_recovered_series": sorted(fallback_recovered),
            "fallback_provider": fallback_provider,
        },
        started_at=started,
        finished_at=utc_now_iso(),
    )
