"""
Multi-query retrieval wrapper for the Qdrant-backed context fetcher.

The LLM's final answer quality is bottlenecked on the **recall** of the
evidence we expose it to. A single semantic search over the user question tends
to cluster around one facet of that question (e.g. it drifts toward
"guidance" when the user asks a broad "risks and catalysts?" prompt).

This module fans the one user question out into three semantically distinct
sub-queries:

1. the raw question (captures whatever the user actually asked for);
2. an explicit *risk / downside* reformulation;
3. an explicit *catalyst / upside* reformulation.

Each sub-query hits Qdrant with the same ticker filter, and the hits are
merged with a lightweight **Reciprocal Rank Fusion (RRF)** so items that
appear high in multiple sub-queries are boosted over single-query hits. The
final deduplicated list is trimmed to the caller-provided ``limit``.

The fan-out is free-of-charge for the LLM budget — it only affects the Qdrant
side — so we can afford to use it for every run. A single-query fallback is
used when one sub-query fails; if all fail the caller sees the original error.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Sequence

from core.schemas.retrieval import RetrievalItem
from core.utils.logger import get_logger
from core.utils.qdrant_helpers import get_qdrant_client, search_documents
from core.config.settings import load_settings
from pipelines.retrieve.reranker import rerank

logger = get_logger("pipelines.retrieve.multi_query")


# Reformulations that have empirically surfaced distinct document clusters
# without drifting off-ticker. They are appended to the user question so the
# base query intent is preserved (important for narrow, thesis-style prompts).
_RISK_LENS = "Downside risks, headwinds, regulatory issues, litigation, margin pressure, competitive threats and guidance cuts relevant to: {question}"
_CATALYST_LENS = "Upside catalysts, new product launches, partnerships, demand acceleration, margin expansion, buybacks and guidance raises relevant to: {question}"


def _build_subqueries(question: str) -> List[str]:
    q = (question or "").strip()
    if not q:
        return []
    return [
        q,
        _RISK_LENS.format(question=q),
        _CATALYST_LENS.format(question=q),
    ]


def _extract_doc_id(hit: Dict[str, Any]) -> str:
    meta = hit.get("metadata") or {}
    doc_id = meta.get("doc_id")
    if doc_id:
        return str(doc_id)
    # Fall back to a stable composite so RRF can still dedupe hits that
    # don't carry a doc_id (legacy payloads).
    return f"{meta.get('source','')}::{meta.get('title','')}::{meta.get('published_at','')}"


def _extract_parent_id(hit: Dict[str, Any]) -> str:
    meta = hit.get("metadata") or {}
    parent = meta.get("parent_doc_id") or meta.get("doc_id")
    if parent:
        return str(parent)
    return _extract_doc_id(hit)


def _dedupe_by_parent(ordered: Sequence[Dict[str, Any]], max_chunks_per_parent: int = 1) -> List[Dict[str, Any]]:
    if max_chunks_per_parent <= 0:
        max_chunks_per_parent = 1
    counts: Dict[str, int] = {}
    deduped: List[Dict[str, Any]] = []
    for hit in ordered:
        parent = _extract_parent_id(hit)
        current = counts.get(parent, 0)
        if current >= max_chunks_per_parent:
            continue
        counts[parent] = current + 1
        deduped.append(hit)
    return deduped


def _rrf_merge(
    ranked_lists: Iterable[Sequence[Dict[str, Any]]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion across multiple ranked result lists.

    See: Cormack, Clarke, Büttcher (2009), "Reciprocal Rank Fusion
    outperforms Condorcet and individual Rank Learning Methods". The constant
    ``k`` dampens the contribution of low-ranked items so the top-1 from each
    sub-query dominates, while duplicates across lists accumulate.
    """
    scores: Dict[str, float] = {}
    records: Dict[str, Dict[str, Any]] = {}
    for hits in ranked_lists:
        for rank, hit in enumerate(hits):
            doc_id = _extract_doc_id(hit)
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            # Keep the richest record (highest score attribute from Qdrant)
            # so the downstream RetrievalItem carries meaningful ranking info.
            existing = records.get(doc_id)
            if existing is None or float(hit.get("score", 0.0)) > float(existing.get("score", 0.0)):
                records[doc_id] = hit
    ordered = sorted(records.values(), key=lambda h: scores[_extract_doc_id(h)], reverse=True)
    try:
        max_per_parent = int(getattr(load_settings(), "max_chunks_per_parent", 1) or 1)
    except Exception:
        max_per_parent = 1
    return _dedupe_by_parent(ordered, max_per_parent)


def retrieve_context_multi(ticker: str, question: str, top_k: int) -> List[RetrievalItem]:
    """Fan-out retrieval with RRF fusion.

    Behaves like ``retrieve_context`` but issues three sub-queries per call.
    Returns at most ``top_k`` items. If every sub-query fails the exception is
    propagated so the orchestrator can fall back to its existing recovery
    branch.
    """
    settings = load_settings()
    subqueries = _build_subqueries(question)
    if not subqueries:
        return []

    # Each sub-query draws a slightly larger window so RRF has room to rerank.
    # We cap at 25 to keep Qdrant latency bounded on a single workstation.
    per_query_limit = max(top_k * 3, 15)
    per_query_limit = min(per_query_limit, 25)

    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    ranked_lists: List[List[Dict[str, Any]]] = []
    failures = 0
    for sub in subqueries:
        try:
            hits = search_documents(
                client=client,
                collection_name=settings.collection_name,
                symbol=ticker,
                query_text=sub,
                limit=per_query_limit,
            )
            ranked_lists.append(hits)
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            failures += 1
            logger.warning("[MULTI_QUERY] Sub-query failed (%s): %s", sub[:60], exc)

    if not ranked_lists:
        raise RuntimeError(
            f"Multi-query retrieval failed for ticker={ticker}; all {len(subqueries)} sub-queries errored out."
        )

    fused = _rrf_merge(ranked_lists)
    candidate_floor = int(getattr(settings, "reranker_candidate_pool", 30) or 30)
    candidate_pool = fused[: max(top_k * 3, candidate_floor)]
    if bool(getattr(settings, "reranker_enabled", True)):
        trimmed = rerank(
            question,
            candidate_pool,
            top_k=top_k,
            model_name=getattr(settings, "reranker_model", None),
        )
    else:
        trimmed = candidate_pool[:top_k]

    result_items: List[RetrievalItem] = []
    found_tickers: set[str] = set()
    for hit in trimmed:
        meta = hit.get("metadata", {}) or {}
        item_ticker = meta.get("ticker") or meta.get("symbol") or "unknown"
        found_tickers.add(str(item_ticker))
        result_items.append(
            RetrievalItem(
                source=meta.get("source", "unknown"),
                title=meta.get("title", ""),
                date=meta.get("published_at", ""),
                chunk=hit.get("document", ""),
                score=float(hit.get("score", 0.0)),
                metadata=meta,
            )
        )

    purity_ok = all(t == ticker for t in found_tickers) if found_tickers else True
    logger.info(
        "[MULTI_QUERY_DIAGNOSTICS] Requested=%s Sub-queries=%d Failures=%d Chunks=%d Purity=%s",
        ticker,
        len(subqueries),
        failures,
        len(result_items),
        "PASS" if purity_ok else "FAIL",
    )
    if not purity_ok:
        logger.warning("[PURITY_VIOLATION] Multi-query retrieval for %s contained off-ticker items: %s", ticker, found_tickers)
    return result_items
