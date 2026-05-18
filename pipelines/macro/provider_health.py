from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from core.schemas.macro import MacroProviderHealthItem, MacroProviderHealthResponse
from pipelines.macro import macro_service


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _macro_job_providers(scheduler_status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    last_result = scheduler_status.get("last_result")
    if not isinstance(last_result, dict):
        return {}
    jobs = last_result.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    macro_job = jobs.get("macro_platform_data")
    if not isinstance(macro_job, dict):
        return {}
    providers = macro_job.get("providers")
    if not isinstance(providers, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in providers:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip().lower()
        if provider:
            out[provider] = item
    return out


def _safe_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _provider_items(health: dict[str, Any], scheduler_status: dict[str, Any]) -> list[MacroProviderHealthItem]:
    configured = {
        str(provider or "").strip().lower(): bool(is_available)
        for provider, is_available in dict(health.get("providers") or {}).items()
    }
    latest = _macro_job_providers(scheduler_status)
    names = sorted({*configured.keys(), *latest.keys()})
    items: list[MacroProviderHealthItem] = []
    for name in names:
        latest_item = latest.get(name, {})
        detail = latest_item.get("detail") if isinstance(latest_item.get("detail"), dict) else {}
        items.append(
            MacroProviderHealthItem(
                provider=name,
                enabled=name in configured,
                configured=bool(configured.get(name, False)),
                latest_status=str(latest_item.get("status") or "unknown"),
                latest_rows=latest_item.get("rows") if isinstance(latest_item.get("rows"), int) else None,
                latest_error=_safe_optional_string(latest_item.get("error")),
                detail=detail,
            )
        )
    return items


def _series_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": row.get("series_id"),
        "display_name": row.get("display_name"),
        "status": row.get("status"),
        "latest_date": row.get("latest_date"),
        "provider": row.get("provider"),
        "errors": row.get("errors") or [],
        "notes": row.get("notes") or [],
    }


def _series_by_status(quality_payload: dict[str, Any], status: str) -> list[dict[str, Any]]:
    rows = [dict(row or {}) for row in quality_payload.get("series", [])]
    return [_series_summary(row) for row in rows if str(row.get("status") or "").lower() == status]


def _stale_series(quality_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = {str(row.get("series_id")): dict(row or {}) for row in quality_payload.get("series", []) if isinstance(row, dict)}
    ids = [str(item) for item in quality_payload.get("data_quality", {}).get("stale_series") or []]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for series_id in ids:
        seen.add(series_id)
        out.append(_series_summary(rows.get(series_id, {"series_id": series_id, "status": "stale"})))
    for item in _series_by_status(quality_payload, "stale"):
        series_id = str(item.get("series_id") or "")
        if series_id not in seen:
            seen.add(series_id)
            out.append(item)
    for status in ("unavailable", "partial"):
        for item in _series_by_status(quality_payload, status):
            series_id = str(item.get("series_id") or "")
            if series_id not in seen:
                seen.add(series_id)
                out.append(item)
    return out


def build_macro_provider_health(*, scheduler_status: dict[str, Any] | None = None) -> MacroProviderHealthResponse:
    scheduler = scheduler_status or {"enabled": False}
    health = macro_service.get_health()
    quality_payload = macro_service.get_data_quality()
    quality = dict(quality_payload.get("data_quality") or {})
    providers = _provider_items(health, scheduler)
    stale_series = _stale_series(quality_payload)
    unavailable_series = _series_by_status(quality_payload, "unavailable")
    partial_series = _series_by_status(quality_payload, "partial")
    warnings: list[str] = []
    if quality.get("status") != "ok":
        warnings.append(f"Macro data quality is {quality.get('status') or 'unavailable'}.")
    unavailable_providers = [item.provider for item in providers if not item.configured]
    if unavailable_providers:
        warnings.append(f"Providers not configured or unavailable: {', '.join(unavailable_providers)}.")
    return MacroProviderHealthResponse(
        status=quality.get("status") or "unavailable",
        generated_at=_now_iso(),
        providers=providers,
        scheduler=scheduler,
        stale_series=stale_series,
        unavailable_series=unavailable_series,
        partial_series=partial_series,
        data_quality=quality,
        warnings=warnings,
    )
