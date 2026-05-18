from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from core.schemas.macro import MacroDataQuality, MacroObservation, MacroSeriesDefinition, MacroSeriesResponse


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def evaluate_series_quality(
    definition: MacroSeriesDefinition,
    observations: list[MacroObservation],
    provider_quality: MacroDataQuality,
    *,
    transform_errors: Iterable[str] = (),
) -> MacroDataQuality:
    errors = [item for item in provider_quality.errors if item]
    errors.extend([item for item in transform_errors if item])
    notes = list(provider_quality.notes)
    if not observations:
        return MacroDataQuality(
            status="unavailable",
            provider=provider_quality.provider,
            last_updated=provider_quality.last_updated,
            missing_series=[definition.series_id],
            errors=errors,
            notes=notes or ["No observations are available."],
        )

    latest = observations[-1]
    latest_dt = _parse_date(latest.date)
    stale_series: list[str] = []
    status = "ok"
    if latest_dt is None:
        status = "partial"
        errors.append(f"invalid latest date for {definition.series_id}: {latest.date}")
    else:
        age_days = (datetime.now(timezone.utc) - latest_dt).days
        if age_days > definition.stale_after_days:
            status = "stale"
            stale_series.append(definition.series_id)
            notes.append(f"{definition.series_id} latest observation is {age_days} days old.")
    if errors and status == "ok":
        status = "partial"
    if provider_quality.status == "partial" and status == "ok":
        status = "partial"
    return MacroDataQuality(
        status=status,
        provider=provider_quality.provider,
        last_updated=provider_quality.last_updated or latest.metadata.get("collected_at") or latest.date,
        stale_series=stale_series,
        errors=errors,
        notes=notes,
    )


def aggregate_quality(items: list[MacroDataQuality | MacroSeriesResponse], *, provider: str = "mixed") -> MacroDataQuality:
    qualities = [item.data_quality if isinstance(item, MacroSeriesResponse) else item for item in items]
    if not qualities:
        return MacroDataQuality(status="unavailable", provider=provider, notes=["No macro quality inputs."])
    statuses = [quality.status for quality in qualities]
    available = [status for status in statuses if status != "unavailable"]
    if not available:
        status = "unavailable"
    elif any(status == "partial" for status in statuses) or any(status == "unavailable" for status in statuses):
        status = "partial"
    elif any(status == "stale" for status in statuses):
        status = "stale"
    else:
        status = "ok"
    missing: list[str] = []
    stale: list[str] = []
    errors: list[str] = []
    notes: list[str] = []
    last_updated: str | None = None
    for quality in qualities:
        missing.extend(quality.missing_series)
        stale.extend(quality.stale_series)
        errors.extend(quality.errors)
        notes.extend(quality.notes)
        if quality.last_updated and (last_updated is None or quality.last_updated > last_updated):
            last_updated = quality.last_updated
    return MacroDataQuality(
        status=status,
        provider=provider,
        last_updated=last_updated,
        missing_series=sorted(set(missing)),
        stale_series=sorted(set(stale)),
        errors=sorted(set(errors)),
        notes=sorted(set(notes)),
    )
