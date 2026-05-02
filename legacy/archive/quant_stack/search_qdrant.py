# Search Qdrant for symbol-specific market documents and print the highest-scoring matches.
from __future__ import annotations

import argparse
import json
import traceback

from app.config import DEFAULT_SEARCH_QUERY, load_settings
from app.preflight import check_qdrant, ensure_supported_runtime
from app.pipeline import get_qdrant_client, search_documents, shorten_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search normalized market documents in Qdrant.")
    parser.add_argument("--query", default=None, help="Search question. Defaults to a short-term risk/catalyst query.")
    parser.add_argument("--limit", type=int, default=5, help="Number of search hits to print.")
    return parser.parse_args()


def main() -> None:
    ensure_supported_runtime()
    args = parse_args()
    settings = load_settings()
    query_text = args.query or DEFAULT_SEARCH_QUERY.replace("AAPL", settings.symbol)

    qdrant_check = check_qdrant(settings)
    if not qdrant_check.ok:
        print("Qdrant preflight failed:")
        print(f" - {qdrant_check.details.get('error', 'unknown error')}")
        for fix in qdrant_check.fixes:
            print(f" - fix: {fix}")
        return

    client = get_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    hits = search_documents(
        client=client,
        collection_name=settings.collection_name,
        symbol=settings.symbol,
        query_text=query_text,
        limit=args.limit,
    )

    if not hits:
        print(
            f"No search results found for symbol={settings.symbol} in collection='{settings.collection_name}'. "
            "Run ingest_qdrant.py first or confirm that Qdrant is reachable."
        )
        return

    print(f"Query: {query_text}")
    print(f"Returned {len(hits)} hits for symbol={settings.symbol}")
    for index, hit in enumerate(hits, start=1):
        print("=" * 80)
        print(f"Rank: {index}")
        print(f"Score: {hit['score']:.4f}")
        print("Metadata:")
        print(json.dumps(hit["metadata"], ensure_ascii=False, indent=2))
        print("Document Preview:")
        print(shorten_text(hit["document"], 700))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI behavior
        print(f"search_qdrant.py failed: {exc}")
        traceback.print_exc()
        raise SystemExit(1) from exc
