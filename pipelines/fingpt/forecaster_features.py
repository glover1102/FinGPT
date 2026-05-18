"""Deterministic metadata-only Forecaster-style signals from FinGPT labels."""
from __future__ import annotations

from typing import Any

from core.schemas.fingpt import FinGPTForecasterSignal


POSITIVE_LABELS = {"positive", "price_up", "up", "bullish"}
NEGATIVE_LABELS = {"negative", "price_down", "down", "bearish"}


def _score_annotation(annotation: Any) -> float:
    label = _annotation_value(annotation, "label")
    try:
        confidence = float(_annotation_value(annotation, "confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if str(label or "").strip().lower() in POSITIVE_LABELS:
        return confidence
    if str(label or "").strip().lower() in NEGATIVE_LABELS:
        return -confidence
    return 0.0


def build_forecaster_signal(
    *,
    ticker: str,
    annotations: list[Any],
    structured_metrics: dict[str, Any],
    horizon: str = "1w",
) -> FinGPTForecasterSignal:
    label_items = list(annotations or [])
    total = sum(_score_annotation(annotation) for annotation in label_items)
    total += _price_return_score(structured_metrics)
    direction = "neutral"
    if total > 0.25:
        direction = "up"
    elif total < -0.25:
        direction = "down"
    confidence = min(0.95, max(0.1, abs(total) / max(1.0, len(label_items))))
    return FinGPTForecasterSignal(
        ticker=str(ticker or "").strip().upper(),
        horizon=str(horizon or "1w").strip() or "1w",
        direction=direction,
        confidence=round(confidence, 3),
        rationale=f"Auxiliary FinGPT-style signal from {len(label_items)} labels and structured metrics.",
        evidence_doc_ids=_evidence_doc_ids(label_items),
    )


def _price_return_score(structured_metrics: dict[str, Any] | None) -> float:
    metrics = structured_metrics if isinstance(structured_metrics, dict) else {}
    try:
        value = float(metrics.get("price_return_20d"))
    except (TypeError, ValueError):
        return 0.0
    if value > 0.02:
        return 0.2
    if value < -0.02:
        return -0.2
    return 0.0


def _evidence_doc_ids(annotations: list[Any]) -> list[str]:
    ids: list[str] = []
    for annotation in annotations:
        clean = str(_annotation_value(annotation, "article_id") or "").strip()
        if clean:
            ids.append(clean)
        if len(ids) >= 10:
            break
    return ids


def _annotation_value(annotation: Any, key: str) -> Any:
    if isinstance(annotation, dict):
        return annotation.get(key)
    return getattr(annotation, key, None)
