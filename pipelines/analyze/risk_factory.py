"""Factory for the pluggable risk engine.

The pipeline calls ``get_risk_engine()`` once per run. The resolution order is:

1. Explicit ``engine_name`` argument (tests / CLI override).
2. ``settings.risk_engine`` (env-driven ``RISK_ENGINE=...`` in ``.env``).
3. Default: ``heuristic``.

Unknown engine names are logged and fall back to heuristic, never crash; the
risk engine is a downstream refinement, not a hard prerequisite for producing
an answer.
"""
from __future__ import annotations

from core.config.settings import Settings, load_settings
from core.interfaces.risk import BaseRiskEngine
from core.utils.logger import get_logger
from pipelines.analyze.risk_analysis import HeuristicRiskEngine

logger = get_logger("pipelines.analyze.risk_factory")


_VALID_ENGINES = {"heuristic", "finbert", "fingpt"}


def get_risk_engine(
    engine_name: str | None = None,
    *,
    settings: Settings | None = None,
) -> BaseRiskEngine:
    """Return the risk engine configured for this run. Always returns something."""
    settings = settings or load_settings()
    name = (engine_name or getattr(settings, "risk_engine", "heuristic") or "heuristic").strip().lower()

    if name not in _VALID_ENGINES:
        logger.warning("[RISK_ENGINE] unknown engine '%s'; falling back to heuristic", name)
        return HeuristicRiskEngine()

    if name == "heuristic":
        return HeuristicRiskEngine()

    if name == "finbert":
        try:
            # Lazy import so the heuristic path never pays transformers' cost.
            from pipelines.analyze.finbert_risk_engine import (
                FinBertRiskEngine,
                FinBertUnavailable,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[RISK_ENGINE] finbert module unavailable (%s); falling back to heuristic",
                exc,
            )
            return HeuristicRiskEngine()

        try:
            engine = FinBertRiskEngine(model_name=getattr(settings, "finbert_model_name", "ProsusAI/finbert"))
            # Eagerly materialize the classifier. If weights are missing we
            # want to know *now* (and fall back) rather than silently break
            # the analyze stage mid-request.
            engine._load_classifier()  # type: ignore[attr-defined]
            logger.info("[RISK_ENGINE] active=finbert")
            return engine
        except FinBertUnavailable as exc:
            logger.warning("[RISK_ENGINE] finbert unavailable (%s); falling back to heuristic", exc)
            return HeuristicRiskEngine()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RISK_ENGINE] finbert load failed (%s); falling back to heuristic", exc)
            return HeuristicRiskEngine()

    if name == "fingpt":
        try:
            from pipelines.fingpt.risk_engine import FinGPTRiskEngine
            from pipelines.fingpt.task_adapter import FinGPTTaskAdapter
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[RISK_ENGINE] fingpt module unavailable (%s); falling back to heuristic",
                exc,
            )
            return HeuristicRiskEngine()

        if not getattr(settings, "fingpt_task_model_enabled", False):
            logger.warning("[RISK_ENGINE] fingpt task model disabled; falling back to heuristic")
            return HeuristicRiskEngine()

        adapter = FinGPTTaskAdapter(
            enabled=True,
            model_name=getattr(settings, "fingpt_task_model_name", "FinGPT/fingpt-mt_llama3-8b_lora"),
        )
        logger.info("[RISK_ENGINE] active=fingpt")
        return FinGPTRiskEngine(adapter)

    return HeuristicRiskEngine()
