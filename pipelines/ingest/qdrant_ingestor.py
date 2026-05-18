from typing import List, Dict, Any
from core.utils.logger import get_logger
from core.config.settings import load_settings
from pipelines.ingest.chunker import chunk_document

logger = get_logger("pipelines.ingest")

METADATA_FIELDS = [
    "doc_id", "ticker", "symbol", "doc_type", "source",
    "published_at", "title", "url", "admitted_by", "collected_at",
    "parent_doc_id", "chunk_index", "total_chunks", "char_start", "char_end",
]


def _chunk_records(documents: List[Dict[str, Any]], settings, chunking_enabled: bool) -> tuple[list[str], list[dict[str, Any]]]:
    text_documents: list[str] = []
    metadata: list[dict[str, Any]] = []
    for doc in documents:
        raw_text = str(doc.get("text", "") or "").strip()
        if not raw_text:
            continue
        parent_doc_id = str(doc.get("doc_id") or "").strip()
        if not parent_doc_id:
            continue

        if chunking_enabled:
            chunks = chunk_document(
                text=raw_text,
                doc_id=parent_doc_id,
                title=str(doc.get("title") or ""),
                target_tokens=int(getattr(settings, "ingest_chunk_tokens", 512) or 512),
                overlap_tokens=int(getattr(settings, "ingest_chunk_overlap", 64) or 64),
            )
        else:
            chunks = []

        if not chunks:
            chunks = chunk_document(
                text=raw_text,
                doc_id=parent_doc_id,
                title=str(doc.get("title") or ""),
                target_tokens=max(100000, len(raw_text.split()) + 1),
                overlap_tokens=0,
            )

        for chunk in chunks:
            record = dict(doc)
            record["doc_id"] = chunk.chunk_id if chunking_enabled else parent_doc_id
            record["parent_doc_id"] = parent_doc_id
            record["chunk_index"] = chunk.chunk_index
            record["total_chunks"] = chunk.total_chunks
            record["char_start"] = chunk.char_span[0]
            record["char_end"] = chunk.char_span[1]
            record["text"] = chunk.text
            text_documents.append(chunk.text)
            metadata.append({field: record.get(field, "") for field in METADATA_FIELDS})
    return text_documents, metadata


def ingest_documents(
    documents: List[Dict[str, Any]],
    chunking_enabled: bool | None = None,
    *,
    skip_existing_parent_docs: bool = False,
    return_stats: bool = False,
) -> List[str] | dict[str, Any]:
    settings = load_settings()
    logger.info(f"Ingesting {len(documents)} documents into Qdrant collection: {settings.collection_name}")
    
    from core.utils.qdrant_helpers import (
        add_documents_to_qdrant,
        collection_has_sparse_vectors,
        ensure_collection,
        existing_parent_doc_ids,
        get_qdrant_client,
    )

    # Fix 409: Ensure collection exists before adding documents
    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    ensure_collection(client, settings.collection_name)

    if chunking_enabled is None:
        chunking_enabled = bool(getattr(settings, "ingest_chunking_enabled", True))
    docs_to_ingest = list(documents)
    skipped_parent_doc_ids: list[str] = []
    if skip_existing_parent_docs:
        parent_doc_ids = [str(doc.get("doc_id") or "").strip() for doc in documents if str(doc.get("doc_id") or "").strip()]
        existing = existing_parent_doc_ids(client, settings.collection_name, parent_doc_ids)
        if existing:
            skipped_parent_doc_ids = sorted(existing)
            docs_to_ingest = [doc for doc in documents if str(doc.get("doc_id") or "").strip() not in existing]

    text_documents, metadata = _chunk_records(docs_to_ingest, settings, chunking_enabled)
    
    if not text_documents:
        logger.warning("No valid text documents to ingest.")
        empty_result = {
            "inserted_ids": [],
            "inserted_docs": 0,
            "requested_docs": len(documents),
            "skipped_parent_doc_ids": skipped_parent_doc_ids,
            "skipped_docs": len(skipped_parent_doc_ids),
        }
        return empty_result if return_stats else []

    add_client = client
    if bool(getattr(settings, "hybrid_search_enabled", True)) and collection_has_sparse_vectors(client, settings.collection_name) is False:
        logger.warning(
            "Collection %s has no sparse vectors; using dense-only add client for ingest.",
            settings.collection_name,
        )
        add_client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key, enable_sparse=False)

    inserted_ids = add_documents_to_qdrant(
        client=add_client,
        collection_name=settings.collection_name,
        documents=text_documents,
        metadata=metadata,
        batch_size=16,
    )
    logger.info(
        "Successfully ingested %d vectors from %d source documents (chunking=%s).",
        len(inserted_ids),
        len(docs_to_ingest),
        chunking_enabled,
    )
    if return_stats:
        return {
            "inserted_ids": inserted_ids,
            "inserted_docs": len(docs_to_ingest),
            "requested_docs": len(documents),
            "skipped_parent_doc_ids": skipped_parent_doc_ids,
            "skipped_docs": len(skipped_parent_doc_ids),
        }
    return inserted_ids
