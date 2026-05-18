from __future__ import annotations

from datetime import date
from math import isfinite

from core.schemas.macro import MacroObservation, MacroSeriesDefinition


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _periods_per_year(frequency: str) -> int:
    freq = str(frequency or "").lower()
    if "quarter" in freq:
        return 4
    if "week" in freq:
        return 52
    if "daily" in freq:
        return 252
    return 12


def clean_observations(observations: list[MacroObservation]) -> list[MacroObservation]:
    clean: list[MacroObservation] = []
    for obs in observations:
        if not obs.date:
            continue
        value = obs.raw_value if obs.raw_value is not None else obs.value
        if value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if not isfinite(num):
            continue
        clean.append(obs.model_copy(update={"value": num, "raw_value": num}))
    return sorted(clean, key=lambda item: item.date)


def apply_transform(
    definition: MacroSeriesDefinition,
    observations: list[MacroObservation],
) -> tuple[list[MacroObservation], list[str]]:
    raw = clean_observations(observations)
    transform = str(definition.transform or "level").lower()
    if transform == "level":
        return raw, []
    if transform == "yoy_percent":
        period = _periods_per_year(definition.frequency)
        transformed: list[MacroObservation] = []
        for index in range(period, len(raw)):
            current = raw[index]
            prior = raw[index - period]
            current_value = current.raw_value if current.raw_value is not None else current.value
            prior_value = prior.raw_value if prior.raw_value is not None else prior.value
            if current_value is None or prior_value in (None, 0):
                continue
            value = (float(current_value) / float(prior_value) - 1.0) * 100.0
            transformed.append(
                current.model_copy(
                    update={
                        "value": value,
                        "metadata": {
                            **current.metadata,
                            "transform": "yoy_percent",
                            "comparison_date": prior.date,
                            "comparison_raw_value": prior_value,
                        },
                    }
                )
            )
        if not transformed and raw:
            return [], [f"insufficient history for yoy_percent transform: {definition.series_id}"]
        return transformed, []
    return raw, [f"unknown transform {definition.transform}; returned level values"]


def compute_changes(observations: list[MacroObservation]) -> dict[str, float | str | None]:
    clean = clean_observations(observations)
    if not clean:
        return {
            "latest_date": None,
            "latest_value": None,
            "previous_date": None,
            "change_1_period": None,
            "change_3_period": None,
            "change_12_period": None,
            "percent_change_1_period": None,
        }
    latest = clean[-1]

    def diff(periods: int) -> float | None:
        if len(clean) <= periods:
            return None
        prior = clean[-1 - periods]
        if latest.value is None or prior.value is None:
            return None
        return float(latest.value) - float(prior.value)

    def pct(periods: int) -> float | None:
        if len(clean) <= periods:
            return None
        prior = clean[-1 - periods]
        if latest.value is None or prior.value in (None, 0):
            return None
        return (float(latest.value) / float(prior.value) - 1.0) * 100.0

    previous = clean[-2] if len(clean) >= 2 else None
    return {
        "latest_date": latest.date,
        "latest_value": latest.value,
        "previous_date": previous.date if previous else None,
        "change_1_period": diff(1),
        "change_3_period": diff(3),
        "change_12_period": diff(12),
        "percent_change_1_period": pct(1),
    }
