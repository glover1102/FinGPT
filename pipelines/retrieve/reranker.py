from __future__ import annotations

from typing import Any, Iterable

from core.config.settings import load_settings
from core.utils.logger import get_logger

logger = get_logger("pipelines.retrieve.reranker")

_RERANKER_CACHE: dict[str, Any] = {}
_MIN_RERANK_CANDIDATES = 4


def get_reranker(model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2"):
    """Return a cached cross-encoder-like reranker instance.

    The runtime dependency is intentionally soft. Newer FastEmbed builds expose
    ``TextCrossEncoder`` while some environments only have sentence-transformers
    installed. If neither is available, callers fail open and keep the original
    ordering.
    """
    cached = _RERANKER_CACHE.get(model_name)
    if cached is not None:
        return cached

    try:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder  # type: ignore
        except Exception:
            from fastembed import TextCrossEncoder  # type: ignore

        model = TextCrossEncoder(model_name=model_name)
    except Exception as fastembed_exc:
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            model = CrossEncoder(model_name)
        except Exception as st_exc:
            raise RuntimeError(
                f"cross-encoder load failed for {model_name}: fastembed={fastembed_exc}; "
                f"sentence_transformers={st_exc}"
            ) from st_exc

    _RERANKER_CACHE[model_name] = model
    return model


def _candidate_text(candidate: dict[str, Any]) -> str:
    meta = candidate.get("metadata") or {}
    return " ".join(
        str(part or "").strip()
        for part in (
            meta.get("title"),
            candidate.get("document") or candidate.get("chunk") or meta.get("text") or meta.get("content"),
        )
        if str(part or "").strip()
    )


def _as_scores(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        scores: list[float] = []
        for item in value:
            if isinstance(item, dict):
                raw = item.get("score", item.get("relevance_score", 0.0))
            else:
                raw = getattr(item, "score", item)
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                scores.append(0.0)
        return scores
    try:
        return [float(value)]
    except (TypeError, ValueError):
        return []


def _score_pairs(model: Any, query: str, texts: list[str]) -> list[float]:
    pairs = [(query, text) for text in texts]

    if hasattr(model, "predict"):
        scores = _as_scores(model.predict(pairs))
        if len(scores) == len(texts):
            return scores

    if hasattr(model, "score"):
        scores = _as_scores(model.score(pairs))
        if len(scores) == len(texts):
            return scores

    if hasattr(model, "rerank"):
        result = model.rerank(query, texts)
        scores = _as_scores(result)
        if len(scores) == len(texts):
            return scores

    if callable(model):
        scores = _as_scores(model(pairs))
        if len(scores) == len(texts):
            return scores

    raise RuntimeError(f"unsupported reranker API for {type(model).__name__}")


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """Rerank retrieval hits and return the original payload shape.

    Small candidate sets are returned unchanged to avoid paying model latency
    when RRF has already produced a narrow list. Any model load/scoring failure
    is fail-open by design.
    """
    if not candidates or top_k <= 0:
        return []
    if len(candidates) < _MIN_RERANK_CANDIDATES:
        return candidates[:top_k]

    try:
        settings = load_settings()
        resolved_model = model_name or getattr(settings, "reranker_model", "Xenova/ms-marco-MiniLM-L-6-v2")
        model = get_reranker(resolved_model)
        texts = [_candidate_text(candidate) for candidate in candidates]
        scores = _score_pairs(model, query, texts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RERANKER] fail-open for query=%r: %s", query[:80], exc)
        return candidates[:top_k]

    ranked = sorted(
        enumerate(candidates),
        key=lambda pair: (scores[pair[0]], -pair[0]),
        reverse=True,
    )
    logger.info(
        "[RERANK_DIAGNOSTICS] model=%s candidates=%d returned=%d",
        resolved_model,
        len(candidates),
        min(top_k, len(candidates)),
    )
    return [candidate for _, candidate in ranked[:top_k]]
