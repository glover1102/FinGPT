"""FinBERT-backed risk engine (opt-in).

Motivation
----------
The default ``HeuristicRiskEngine`` relies on the LLM's structured output for
bull/bear bucketing, with a string-keyword fallback (``growth``, ``catalyst``,
...) that misclassifies anything outside its narrow vocabulary. When the LLM
emits only a generic ``risk_flags`` list (older prompts, fallback model, or
truncated JSON), the keyword path is easy to fool.

This engine classifies each risk flag with FinBERT (``ProsusAI/finbert``) —
a financial-domain sentiment classifier that knows the difference between
"margin expansion" and "margin compression" without pattern matching.

Design constraints
------------------
- **Lazy import** of ``transformers`` / ``torch``: they are large, and the
  default install path avoids them. We only import inside ``_load_classifier``
  so that tooling that never instantiates this engine does not pay the cost.
- **Graceful degradation**: if the imports fail, the engine raises
  ``FinBertUnavailable`` so the factory can fall back to heuristic.
- **Event-loop safety**: FinBERT inference is CPU/GPU-bound synchronous work,
  so we wrap it in ``asyncio.to_thread`` — same guardrail the ``BaseRiskEngine``
  interface docstring calls out.
- **Structured output passthrough**: if the LLM already emitted high-quality
  ``bull_points`` / ``bear_points``, we respect them and only invoke FinBERT
  when we have to reinterpret ``risk_flags``.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

from core.interfaces.risk import BaseRiskEngine, RiskEvaluationResult
from core.utils.logger import get_logger

logger = get_logger("pipelines.analyze.finbert")


class FinBertUnavailable(RuntimeError):
    """Raised when transformers/torch/model weights cannot be loaded."""


class FinBertRiskEngine(BaseRiskEngine):
    """FinBERT-backed sentiment bucketing for risk flags."""

    _classifier = None
    _classifier_lock = threading.Lock()

    def __init__(self, *, model_name: str = "ProsusAI/finbert") -> None:
        self._model_name = model_name

    def _load_classifier(self):
        """Singleton-load the Hugging Face pipeline. Heavy, so do it once."""
        if FinBertRiskEngine._classifier is not None:
            return FinBertRiskEngine._classifier
        with FinBertRiskEngine._classifier_lock:
            if FinBertRiskEngine._classifier is not None:
                return FinBertRiskEngine._classifier
            try:
                # Lazy imports — keeps the default install path light.
                from transformers import pipeline  # type: ignore[import-not-found]
            except Exception as exc:  # noqa: BLE001
                raise FinBertUnavailable(
                    f"transformers not installed: {exc}. "
                    "Run `pip install transformers torch` and re-enable RISK_ENGINE=finbert."
                ) from exc
            try:
                logger.info("[FINBERT] loading classifier model=%s", self._model_name)
                FinBertRiskEngine._classifier = pipeline(
                    "text-classification",
                    model=self._model_name,
                    top_k=None,
                    device=-1,  # CPU — users with CUDA can override via HF_DEVICE.
                )
            except Exception as exc:  # noqa: BLE001
                raise FinBertUnavailable(
                    f"failed to load FinBERT weights ({self._model_name}): {exc}"
                ) from exc
            return FinBertRiskEngine._classifier

    def _classify_sync(self, texts: list[str]) -> list[str]:
        """Return a list of sentiment labels aligned with ``texts``. Blocking."""
        if not texts:
            return []
        classifier = self._load_classifier()
        outputs = classifier(texts, truncation=True, max_length=256)
        labels: list[str] = []
        # ``top_k=None`` returns a list of dicts per input (all classes sorted).
        for out in outputs:
            if isinstance(out, list) and out:
                best = max(out, key=lambda x: x.get("score", 0.0))
                labels.append(str(best.get("label", "neutral")).lower())
            elif isinstance(out, dict):
                labels.append(str(out.get("label", "neutral")).lower())
            else:
                labels.append("neutral")
        return labels

    async def evaluate_risk(self, raw_output: dict) -> RiskEvaluationResult:
        bull_points = list(raw_output.get("bull_points", []) or [])
        bear_points = list(raw_output.get("bear_points", []) or [])

        # Respect the LLM's structured output whenever it exists — FinBERT's
        # job here is to *rescue* the legacy path, not second-guess the model.
        if bull_points or bear_points:
            return RiskEvaluationResult(
                bull_points=[str(p) for p in bull_points],
                bear_points=[str(p) for p in bear_points],
            )

        risk_flags: list[Any] = raw_output.get("risk_flags", []) or []
        flag_texts = [str(f) for f in risk_flags if str(f).strip()]
        if not flag_texts:
            return RiskEvaluationResult(bull_points=[], bear_points=[])

        try:
            labels = await asyncio.to_thread(self._classify_sync, flag_texts)
        except FinBertUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("[FINBERT] classification failed: %s", exc)
            raise FinBertUnavailable(str(exc)) from exc

        for text, label in zip(flag_texts, labels):
            if label == "positive":
                bull_points.append(text)
            elif label == "negative":
                bear_points.append(text)
            # Neutral labels are intentionally dropped — they add noise to the
            # bull/bear thesis without aiding the decision.

        logger.info(
            "[FINBERT] classified flags=%d → bull=%d bear=%d",
            len(flag_texts), len(bull_points), len(bear_points),
        )
        return RiskEvaluationResult(
            bull_points=[str(p) for p in bull_points],
            bear_points=[str(p) for p in bear_points],
        )
