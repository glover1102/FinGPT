from typing import List
from core.schemas.retrieval import RetrievalItem
from core.utils.logger import get_logger
from core.config.settings import load_settings

logger = get_logger("pipelines.retrieve")


def _parent_id(meta: dict) -> str:
    return str(meta.get("parent_doc_id") or meta.get("doc_id") or "")


def _dedupe_parent_hits(hits, max_chunks_per_parent: int):
    if max_chunks_per_parent <= 0:
        max_chunks_per_parent = 1
    counts: dict[str, int] = {}
    deduped = []
    for hit in hits:
        meta = hit.get("metadata", {}) or {}
        parent = _parent_id(meta)
        if not parent:
            deduped.append(hit)
            continue
        current = counts.get(parent, 0)
        if current >= max_chunks_per_parent:
            continue
        counts[parent] = current + 1
        deduped.append(hit)
    return deduped


def retrieve_context(ticker: str, question: str, top_k: int) -> List[RetrievalItem]:
    settings = load_settings()
    logger.info(f"Retrieving top {top_k} documents for {ticker} using query: {question}")
    
    from core.utils.qdrant_helpers import get_qdrant_client, search_documents

    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    hits = search_documents(
        client=client,
        collection_name=settings.collection_name,
        symbol=ticker,
        query_text=question,
        limit=max(top_k * 3, top_k),
    )
    hits = _dedupe_parent_hits(hits, int(getattr(settings, "max_chunks_per_parent", 1) or 1))[:top_k]
        
    result_items = []
    found_tickers = set()
    for hit in hits:
        meta = hit.get("metadata", {})
        item_ticker = meta.get("ticker", meta.get("symbol", "unknown"))
        found_tickers.add(item_ticker)
        
        result_items.append(RetrievalItem(
            source=meta.get("source", "unknown"),
            title=meta.get("title", ""),
            date=meta.get("published_at", ""),
            chunk=hit.get("document", ""),
            score=hit.get("score", 0.0),
            metadata=meta
        ))
        
    # --- Purity Diagnostics ---
    purity_ok = all(t == ticker for t in found_tickers) if found_tickers else True
    unique_tickers = list(found_tickers)
    
    logger.info(
        f"[RETRIEVAL_DIAGNOSTICS] Requested={ticker} Chunks={len(result_items)} "
        f"Found_Tickers={unique_tickers} Purity={'PASS' if purity_ok else 'FAIL'}"
    )
    
    if not purity_ok:
        logger.warning(f"[PURITY_VIOLATION] Retrieval for {ticker} contained off-ticker items: {unique_tickers}")

    return result_items
