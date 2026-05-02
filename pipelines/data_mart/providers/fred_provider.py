from __future__ import annotations

from datetime import date
from typing import Any, Callable, Iterable

import httpx

from core.config.settings import load_settings
from pipelines.data_mart.models import MacroObservation, ProviderFetchResult, utc_now_iso

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _clean_float(value: Any) -> float | None:
    if value in (None, "", "."):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_macro_series(
    series_ids: Iterable[str],
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    api_key: str | None = None,
    http_get: Callable[[str, dict[str, Any]], Any] | None = None,
) -> ProviderFetchResult:
    provider = "fred"
    started = utc_now_iso()
    key = api_key if api_key is not None else getattr(load_settings(), "fred_api_key", "")
    if not key:
        return ProviderFetchResult(
            provider=provider,
            status="credentials_missing",
            error="FRED_API_KEY is missing.",
            started_at=started,
            finished_at=utc_now_iso(),
        )

    records: list[MacroObservation] = []
    failed: dict[str, str] = {}
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
        detail={"failed_series": failed, "requested_series": [str(s).upper().strip() for s in series_ids if str(s).strip()]},
        started_at=started,
        finished_at=utc_now_iso(),
    )
