"""Risk engine backed by the optional FinGPT task adapter."""
from __future__ import annotations

import asyncio
from typing import Any

from core.interfaces.risk import BaseRiskEngine, RiskEvaluationResult
from core.utils.logger import get_logger
from pipelines.fingpt.task_adapter import FinGPTTaskAdapter, FinGPTTaskUnavailable

logger = get_logger("pipelines.fingpt.risk_engine")


_BULLISH_LABELS = {"positive", "bullish", "bull", "label_2"}
_BEARISH_LABELS = {"negative", "bearish", "bear", "label_0"}


def _clean_points(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _normalize_sentiment_label(label: str) -> str:
    normalized = str(label or "").strip().lower()
    if normalized in _BULLISH_LABELS:
        return "positive"
    if normalized in _BEARISH_LABELS:
        return "negative"
    return "neutral"


class FinGPTRiskEngine(BaseRiskEngine):
    """Use FinGPT task labels to bucket legacy ``risk_flags``."""

    def __init__(self, adapter: FinGPTTaskAdapter) -> None:
        self.adapter = adapter

    async def evaluate_risk(self, raw_output: dict) -> RiskEvaluationResult:
        bull_points = _clean_points(raw_output.get("bull_points", []))
        bear_points = _clean_points(raw_output.get("bear_points", []))

        if bull_points or bear_points:
            return RiskEvaluationResult(bull_points=bull_points, bear_points=bear_points)

        risk_flags = raw_output.get("risk_flags", []) or []
        flag_texts = [" ".join(str(flag or "").split()).strip() for flag in risk_flags]
        flag_texts = [text for text in flag_texts if text]
        if not flag_texts:
            return RiskEvaluationResult()

        try:
            annotations = await asyncio.to_thread(self.adapter.label_texts, "sentiment", flag_texts)
        except FinGPTTaskUnavailable as exc:
            logger.warning("[FINGPT_RISK] task adapter unavailable (%s); returning empty risk result", exc)
            return RiskEvaluationResult()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[FINGPT_RISK] classification failed (%s); returning empty risk result", exc)
            return RiskEvaluationResult()

        for text, annotation in zip(flag_texts, annotations):
            label = _normalize_sentiment_label(annotation.label)
            if label == "positive":
                bull_points.append(text)
            elif label == "negative":
                bear_points.append(text)

        return RiskEvaluationResult(bull_points=bull_points, bear_points=bear_points)
