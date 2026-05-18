"""Optional FinGPT task-model adapter.

This module must stay cheap to import. Heavy ML dependencies are imported only
inside ``_load_pipeline`` so the default local path can run without
transformers/torch installed.
"""
from __future__ import annotations

import threading
from typing import Any

from core.schemas.fingpt import FinGPTAnnotation, FinGPTTask


class FinGPTTaskUnavailable(RuntimeError):
    """Raised when the optional FinGPT task model cannot be used."""


class FinGPTTaskAdapter:
    """Lazy Hugging Face pipeline wrapper for FinGPT-style task labels."""

    _pipeline_cache: dict[tuple[str, int], Any] = {}
    _pipeline_lock = threading.Lock()

    def __init__(self, enabled: bool, model_name: str, device: int = -1) -> None:
        self.enabled = enabled
        self.model_name = model_name
        self.device = device

    def _load_pipeline(self):
        """Load and cache a text-classification pipeline for this model/device."""
        if not self.enabled:
            raise FinGPTTaskUnavailable("FinGPT task model is disabled")

        cache_key = (self.model_name, self.device)
        cached = FinGPTTaskAdapter._pipeline_cache.get(cache_key)
        if cached is not None:
            return cached

        with FinGPTTaskAdapter._pipeline_lock:
            cached = FinGPTTaskAdapter._pipeline_cache.get(cache_key)
            if cached is not None:
                return cached
            try:
                from transformers import pipeline  # type: ignore[import-not-found]
            except Exception as exc:  # noqa: BLE001
                raise FinGPTTaskUnavailable(f"transformers not installed: {exc}") from exc

            try:
                classifier = pipeline(
                    "text-classification",
                    model=self.model_name,
                    device=self.device,
                )
            except Exception as exc:  # noqa: BLE001
                raise FinGPTTaskUnavailable(
                    f"failed to load FinGPT task model ({self.model_name}): {exc}"
                ) from exc
            FinGPTTaskAdapter._pipeline_cache[cache_key] = classifier
            return classifier

    @staticmethod
    def _best_label(output: Any) -> tuple[str, float]:
        if isinstance(output, list) and output:
            candidates = [item for item in output if isinstance(item, dict)]
            if candidates:
                best = max(candidates, key=lambda item: float(item.get("score") or 0.0))
                return str(best.get("label") or "unknown").lower(), float(best.get("score") or 0.0)
        if isinstance(output, dict):
            return str(output.get("label") or "unknown").lower(), float(output.get("score") or 0.0)
        return "unknown", 0.0

    @classmethod
    def _align_outputs(cls, outputs: Any, expected_count: int) -> list[Any]:
        if expected_count == 1 and isinstance(outputs, dict):
            return [outputs]
        if expected_count == 1 and isinstance(outputs, list):
            if not outputs:
                return [[]]
            if all(isinstance(item, dict) for item in outputs):
                return [outputs]
        if isinstance(outputs, list):
            return outputs[:expected_count]
        return [outputs]

    def label_texts(self, task: FinGPTTask, texts: list[str]) -> list[FinGPTAnnotation]:
        clean_texts = [" ".join(str(text or "").split()).strip() for text in texts]
        clean_texts = [text for text in clean_texts if text]
        if not clean_texts:
            return []

        classifier = self._load_pipeline()
        outputs = classifier(clean_texts, truncation=True, max_length=256)
        aligned_outputs = self._align_outputs(outputs, len(clean_texts))

        annotations: list[FinGPTAnnotation] = []
        for index, (text, output) in enumerate(zip(clean_texts, aligned_outputs)):
            label, confidence = self._best_label(output)
            annotations.append(
                FinGPTAnnotation(
                    article_id=f"inline-{index}",
                    task=task,
                    label=label,
                    confidence=max(0.0, min(1.0, confidence)),
                    source="fingpt-task-adapter",
                    model_id=self.model_name,
                    metadata={"text_preview": text[:160]},
                )
            )
        return annotations
