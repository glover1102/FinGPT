# Load normalized documents from JSON and ingest them into Qdrant with fastembed.
from __future__ import annotations

import traceback

from app.config import load_settings
from app.preflight import check_qdrant, ensure_supported_runtime
from app.pipeline import add_documents_to_qdrant, get_qdrant_client, read_documents

METADATA_FIELDS = [
    "doc_id",
    "symbol",
    "doc_type",
    "source",
    "published_at",
    "title",
    "url",
]


def main() -> None:
    ensure_supported_runtime()
    settings = load_settings()
    qdrant_check = check_qdrant(settings)
    if not qdrant_check.ok:
        print("Qdrant preflight failed:")
        print(f" - {qdrant_check.details.get('error', 'unknown error')}")
        for fix in qdrant_check.fixes:
            print(f" - fix: {fix}")
        return

    documents = read_documents(settings.raw_docs_path)
    if not documents:
        print(f"No documents found at {settings.raw_docs_path}. Run collect_openbb.py first.")
        return

    text_documents = [doc.get("text", "").strip() for doc in documents if doc.get("text", "").strip()]
    metadata = [{field: doc.get(field, "") for field in METADATA_FIELDS} for doc in documents if doc.get("text", "").strip()]
    if not text_documents:
        print("Document JSON exists, but every document has empty text. Nothing to ingest.")
        return

    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    inserted_ids = add_documents_to_qdrant(
        client=client,
        collection_name=settings.collection_name,
        documents=text_documents,
        metadata=metadata,
        batch_size=16,
    )

    print(f"Ingested {len(inserted_ids)} documents into Qdrant collection '{settings.collection_name}'.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI behavior
        print(f"ingest_qdrant.py failed: {exc}")
        traceback.print_exc()
        raise SystemExit(1) from exc
