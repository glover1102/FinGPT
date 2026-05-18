from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Sequence

from core.config.settings import load_settings
from core.schemas.retrieval import RetrievalItem
from core.utils.logger import get_logger
from core.utils.qdrant_helpers import get_qdrant_client, search_documents
from pipelines.retrieve.reranker import rerank

logger = get_logger("pipelines.retrieve.topic")


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9=\-./]{1,}|[\uac00-\ud7a3]{2,}", str(text or "").lower())
    return {token for token in tokens if token}


def _doc_id(hit: Dict[str, Any]) -> str:
    meta = hit.get("metadata") or {}
    return str(meta.get("doc_id") or f"{meta.get('source','')}::{meta.get('title','')}::{meta.get('published_at','')}")


def _parent_id(hit: Dict[str, Any]) -> str:
    meta = hit.get("metadata") or {}
    return str(meta.get("parent_doc_id") or meta.get("doc_id") or _doc_id(hit))


def _subqueries(
    question: str,
    theme: str | None,
    *,
    asset_class: str | None = None,
    related_tickers: list[str] | None = None,
) -> list[str]:
    base = (question or theme or "").strip()
    if not base:
        return []
    ticker_hint = ", ".join(related_tickers or [])
    queries = [base]
    if asset_class == "rates_bonds":
        queries.append(f"historical rates, term premium, and long-duration bond context for {base} {ticker_hint}".strip())
    elif asset_class == "commodity":
        queries.append(f"supply demand curve and market structure for {base} {ticker_hint}".strip())
    elif asset_class == "fx":
        queries.append(f"rate differential, dollar liquidity, and positioning for {base} {ticker_hint}".strip())
    elif asset_class == "crypto":
        queries.append(f"liquidity, ETF flows, and risk sentiment for {base} {ticker_hint}".strip())
    elif asset_class == "sector_theme":
        queries.append(f"sector cycle, valuation, and competitive dynamics for {base} {ticker_hint}".strip())
    return queries[:2]


def _rrf(lists: Iterable[Sequence[Dict[str, Any]]], k: int = 60) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    records: dict[str, dict[str, Any]] = {}
    for hits in lists:
        for rank, hit in enumerate(hits):
            doc_id = _doc_id(hit)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            existing = records.get(doc_id)
            if existing is None or float(hit.get("score", 0.0)) > float(existing.get("score", 0.0)):
                records[doc_id] = hit
    ordered = sorted(records.values(), key=lambda h: scores[_doc_id(h)], reverse=True)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for hit in ordered:
        parent = _parent_id(hit)
        if parent in seen:
            continue
        seen.add(parent)
        deduped.append(hit)
    return deduped


def _doc_relevance_score(doc: dict[str, Any], query_tokens: set[str], ticker_hints: set[str]) -> float:
    title = str(doc.get("title") or "")
    text = str(doc.get("text") or "")
    source = str(doc.get("source") or "").lower()
    ticker = str(doc.get("ticker") or doc.get("symbol") or "").upper()
    doc_tokens = _tokenize(f"{title} {text}")
    overlap = len(query_tokens & doc_tokens)
    score = float(overlap)
    if ticker and ticker in ticker_hints:
        score += 5.0
    if source.startswith("fred"):
        score += 4.0
    elif "yfinance:technical" in source or str(doc.get("doc_type") or "") == "technical_snapshot":
        score += 3.8
    elif "yfinance:price" in source or "history" in source or "price" in source:
        score += 3.0
    elif "issuer:" in source or str(doc.get("doc_type") or "") == "etf_profile":
        score += 2.5
    elif "google" in source or "news" in source:
        score += 1.5
    return score


def rank_topic_context_fast(
    documents: list[dict[str, Any]],
    question: str,
    theme: str,
    related_tickers: list[str],
    top_k: int,
) -> list[RetrievalItem]:
    query_tokens = _tokenize(f"{question} {theme} {' '.join(related_tickers)}")
    ticker_hints = {str(t or "").upper().strip() for t in related_tickers if str(t or "").strip()}
    scored = sorted(documents, key=lambda doc: _doc_relevance_score(doc, query_tokens, ticker_hints), reverse=True)
    items: list[RetrievalItem] = []
    seen: set[str] = set()
    for doc in scored:
        text = str(doc.get("text") or "").strip()
        if not text:
            continue
        doc_id = str(doc.get("doc_id") or "")
        if doc_id and doc_id in seen:
            continue
        if doc_id:
            seen.add(doc_id)
        items.append(
            RetrievalItem(
                source=str(doc.get("source") or "current_run"),
                title=str(doc.get("title") or "Current-run document"),
                date=str(doc.get("published_at") or ""),
                chunk=text,
                score=_doc_relevance_score(doc, query_tokens, ticker_hints),
                metadata={
                    "doc_id": doc_id,
                    "parent_doc_id": doc_id,
                    "ticker": doc.get("ticker") or doc.get("symbol") or "",
                    "doc_type": doc.get("doc_type") or "topic",
                    "source": doc.get("source") or "current_run",
                    "published_at": doc.get("published_at") or "",
                    "url": doc.get("url") or "",
                    "asset_class": doc.get("asset_class") or "",
                    "bucket": doc.get("bucket") or "",
                    "retrieval_mode": "fast_current_documents",
                },
            )
        )
        if len(items) >= top_k:
            break
    logger.info("[TOPIC_FAST_RETRIEVAL] docs=%d returned=%d", len(documents), len(items))
    return items


def retrieve_topic_context(
    question: str,
    theme: str | None = None,
    top_k: int = 12,
    *,
    asset_class: str | None = None,
    related_tickers: list[str] | None = None,
    use_reranker: bool | None = None,
) -> list[RetrievalItem]:
    settings = load_settings()
    queries = _subqueries(question, theme, asset_class=asset_class, related_tickers=related_tickers)
    if not queries:
        return []
    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    ranked_lists: list[list[dict[str, Any]]] = []
    limit = max(top_k * 2, 12)
    for query in queries:
        try:
            ranked_lists.append(
                search_documents(
                    client=client,
                    collection_name=settings.collection_name,
                    symbol=None,
                    query_text=query,
                    limit=limit,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[TOPIC_RETRIEVAL] query failed (%s): %s", query[:80], exc)
    if not ranked_lists:
        return []
    fused = _rrf(ranked_lists)
    rerank_enabled = bool(getattr(settings, "reranker_enabled", True)) if use_reranker is None else bool(use_reranker)
    if rerank_enabled:
        fused = rerank(
            question,
            fused[: max(top_k * 2, 16)],
            top_k=top_k,
            model_name=getattr(settings, "reranker_model", None),
        )
    else:
        fused = fused[:top_k]

    items: list[RetrievalItem] = []
    for hit in fused[:top_k]:
        meta = hit.get("metadata", {}) or {}
        metadata = dict(meta)
        metadata.setdefault("retrieval_mode", "deep_qdrant")
        items.append(
            RetrievalItem(
                source=meta.get("source", "unknown"),
                title=meta.get("title", ""),
                date=meta.get("published_at", ""),
                chunk=hit.get("document", ""),
                score=float(hit.get("score", 0.0)),
                metadata=metadata,
            )
        )
    logger.info(
        "[TOPIC_DEEP_RETRIEVAL] queries=%d chunks=%d reranker=%s",
        len(queries),
        len(items),
        rerank_enabled,
    )
    return items
