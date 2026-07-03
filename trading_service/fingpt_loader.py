from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

_VALID_LABELS = {"positive", "negative", "neutral"}
_MAX_INPUT_LENGTH = 512


class SentimentModel:
    def __init__(self, model_name: str = "ProsusAI/finbert", hf_token: str | None = None):
        self.model_name = model_name
        self.hf_token = hf_token
        self._pipeline: Any | None = None

    def load(self) -> None:
        if self._pipeline is not None:
            return

        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("Sentiment model dependencies are not installed") from exc

        log.info("loading_sentiment_model", model=self.model_name)
        try:
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                device=-1,  # CPU
                token=self.hf_token,
            )
        except Exception as exc:
            log.error("sentiment_model_load_failed", error=str(exc))
            raise RuntimeError(f"Unable to load sentiment model: {exc}") from exc

        log.info("sentiment_model_loaded", model=self.model_name)

    def generate_sentiment(self, text: str) -> str:
        self.load()
        result = self._pipeline(text[:_MAX_INPUT_LENGTH])[0]
        label = result["label"].lower()
        if label in _VALID_LABELS:
            return label
        return "neutral"

    def is_loaded(self) -> bool:
        return self._pipeline is not None
