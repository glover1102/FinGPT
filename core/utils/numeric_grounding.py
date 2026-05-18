from __future__ import annotations

import re
from typing import Iterable

from core.schemas.response import KeyMetric


_NUMBER_RE = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?")


def _has_parseable_value(value: object) -> bool:
    if isinstance(value, (int, float)):
        return True
    text = str(value or "").strip()
    if not text or text.lower() in {"unknown", "n/a", "none", "null", "—", "-"}:
        return False
    return bool(_NUMBER_RE.search(text))


def _copy_metric(metric: KeyMetric | dict) -> KeyMetric:
    if isinstance(metric, KeyMetric):
        return metric.model_copy(deep=True)
    return KeyMetric(**dict(metric))


def validate_key_metric(metric: KeyMetric | dict) -> tuple[KeyMetric, list[str]]:
    checked = _copy_metric(metric)
    warnings: list[str] = []

    if not str(checked.name or "").strip():
        warnings.append("metric name missing")
    if not _has_parseable_value(checked.value):
        warnings.append(f"{checked.name or 'metric'} value missing or not parseable")
    if not str(checked.unit or "").strip():
        warnings.append(f"{checked.name or 'metric'} unit missing")
    if not str(checked.as_of or "").strip() or str(checked.as_of).lower() == "unknown":
        warnings.append(f"{checked.name or 'metric'} as_of missing")
    if not str(checked.source or "").strip():
        warnings.append(f"{checked.name or 'metric'} source missing")

    grounded = bool(
        checked.evidence_doc_ids
        or str(checked.source or "").strip()
        or str(checked.calculation_method or "").strip()
        or checked.is_deterministic
    )
    if not grounded:
        warnings.append(f"{checked.name or 'metric'} has no grounding mechanism")

    required_ok = not warnings
    if required_ok:
        checked.grounding_status = "grounded"
    elif grounded and _has_parseable_value(checked.value):
        checked.grounding_status = "partially_grounded"
    else:
        checked.grounding_status = "ungrounded"
    return checked, warnings


def validate_key_metrics(metrics: Iterable[KeyMetric | dict]) -> tuple[list[KeyMetric], dict[str, float | int], list[str]]:
    validated: list[KeyMetric] = []
    warnings: list[str] = []
    for metric in metrics or []:
        checked, metric_warnings = validate_key_metric(metric)
        validated.append(checked)
        warnings.extend(metric_warnings)

    total = len(validated)
    grounded = sum(1 for metric in validated if metric.grounding_status == "grounded")
    partial = sum(1 for metric in validated if metric.grounding_status == "partially_grounded")
    rate = (grounded + (partial * 0.5)) / total if total else 0.0
    return validated, {
        "metric_count": total,
        "grounded_count": grounded,
        "partially_grounded_count": partial,
        "numeric_grounding_rate": round(rate, 4),
    }, warnings


def numeric_grounding_rate(metrics: Iterable[KeyMetric | dict]) -> float:
    _, summary, _ = validate_key_metrics(metrics)
    return float(summary["numeric_grounding_rate"])
