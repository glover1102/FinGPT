# Shared normalization, storage, Qdrant, and prompt helpers for quant_stack.
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from .config import EMBEDDING_MODEL

HIDDEN_DOCUMENT_KEY = "_document"


def read_documents(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}, got {type(data).__name__}.")
    return [item for item in data if isinstance(item, dict)]


def write_documents(path: Path, documents: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(documents, handle, ensure_ascii=False, indent=2)


def safe_get(item: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = _get_key(item, key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, tuple, set, dict)) and not value:
            continue
        return value
    return default


def _get_key(item: Any, key: str) -> Any:
    current = item
    for part in key.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def as_clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (list, tuple, set)):
        parts = [as_clean_text(part) for part in value]
        return " ".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(value)
    return " ".join(str(value).split())


def unique_text(parts: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        cleaned = as_clean_text(part)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return "\n\n".join(ordered)


def iso_datetime(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat()
    text = as_clean_text(value)
    if not text:
        return ""
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return text


def build_doc_id(symbol: str, doc_type: str, seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"{symbol.lower()}_{doc_type}_{digest}"


def doc_id_to_point_id(doc_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))


def chunk_text(text: str, chunk_size: int = 2200, overlap: int = 250) -> list[str]:
    cleaned = as_clean_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        if end < len(cleaned):
            boundary = cleaned.rfind(" ", start, end)
            if boundary > start + 200:
                end = boundary
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_records(response: Any) -> list[Any]:
    if response is None:
        return []

    if isinstance(response, list):
        return response
    if isinstance(response, tuple):
        return list(response)
    if isinstance(response, dict):
        if isinstance(response.get("results"), list):
            return response["results"]
        if isinstance(response.get("data"), list):
            return response["data"]
        return [response]

    for attr in ("results", "data"):
        nested = getattr(response, attr, None)
        if nested is None:
            continue
        records = extract_records(nested)
        if records:
            return records

    for method_name in ("to_df", "to_dict", "model_dump", "dict"):
        method = getattr(response, method_name, None)
        if not callable(method):
            continue
        try:
            result = method()
        except Exception:
            continue
        if method_name == "to_df":
            try:
                return result.to_dict(orient="records")
            except Exception:
                continue
        records = extract_records(result)
        if records:
            return records

    return [response]


def normalize_news_records(records: list[Any], symbol: str, source_hint: str = "openbb") -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for item in records:
        title = as_clean_text(safe_get(item, "title", "headline", default=""))
        excerpt = as_clean_text(safe_get(item, "excerpt", "summary", "teaser", default=""))
        body = as_clean_text(safe_get(item, "body", "content", "text", default=""))
        text = unique_text([title, excerpt, body])
        if not text:
            continue

        published_at = iso_datetime(safe_get(item, "date", "published_at", "published", "datetime"))
        source = as_clean_text(
            safe_get(item, "source", "publisher.name", "publisher", "provider", default=source_hint)
        ) or source_hint
        url = as_clean_text(safe_get(item, "url", "link", "amp_url", default=""))
        seed = "|".join([symbol, title, published_at, url, text[:200]])
        doc_id = build_doc_id(symbol, "news", seed)
        documents.append(
            {
                "doc_id": doc_id,
                "symbol": symbol,
                "doc_type": "news",
                "source": source,
                "published_at": published_at,
                "title": title or f"{symbol} company news",
                "text": text,
                "url": url,
            }
        )

    return deduplicate_documents(documents)


def normalize_transcript_records(records: list[Any], symbol: str, source_hint: str = "fmp") -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for item in records:
        year = as_clean_text(safe_get(item, "year", default=""))
        quarter = normalize_quarter(safe_get(item, "quarter", default=""))
        published_at = iso_datetime(safe_get(item, "date", default=""))
        content = as_clean_text(safe_get(item, "content", "text", "body", default=""))
        if not content:
            continue

        title = f"{symbol} earnings call transcript {year} {quarter}".strip()
        chunks = chunk_text(content)
        total_chunks = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            seed = "|".join([symbol, year, quarter, published_at, str(index), chunk[:200]])
            doc_id = build_doc_id(symbol, "transcript", seed)
            chunk_title = title if total_chunks == 1 else f"{title} chunk {index}/{total_chunks}"
            documents.append(
                {
                    "doc_id": doc_id,
                    "symbol": symbol,
                    "doc_type": "transcript",
                    "source": source_hint,
                    "published_at": published_at,
                    "title": chunk_title,
                    "text": chunk,
                    "url": "",
                }
            )

    return deduplicate_documents(documents)


def normalize_quarter(value: Any) -> str:
    text = as_clean_text(value).upper().replace("QUARTER", "").strip()
    if not text:
        return ""
    return text if text.startswith("Q") else f"Q{text}"


def deduplicate_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for document in documents:
        doc_id = document.get("doc_id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        deduped.append(document)
    return deduped


def get_qdrant_client(
    qdrant_url: str | None = None,
    api_key: str | None = None,
    *,
    location: str | None = None,
    enable_embeddings: bool = True,
):
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RuntimeError(
            "qdrant-client is not installed. Install it with: pip install -r quant_stack/requirements-quant-stack.txt "
            "-c quant_stack/constraints-quant-stack.txt"
        ) from exc

    client = QdrantClient(location=location) if location is not None else QdrantClient(url=qdrant_url, api_key=api_key or None)
    if enable_embeddings:
        configure_embedding_model(client)
    return client


def configure_embedding_model(client: Any) -> None:
    set_model = getattr(client, "set_model", None)
    if callable(set_model):
        client.set_model(EMBEDDING_MODEL)


def build_symbol_filter(symbol: str):
    from qdrant_client import models

    return models.Filter(
        must=[models.FieldCondition(key="symbol", match=models.MatchValue(value=symbol))]
    )


def build_storage_metadata(metadata: list[dict[str, Any]], documents: list[str]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item, document in zip(metadata, documents):
        payload = dict(item)
        payload[HIDDEN_DOCUMENT_KEY] = document
        enriched.append(payload)
    return enriched


def ensure_collection_exists(client: Any, collection_name: str) -> None:
    from qdrant_client import models

    collection_exists = getattr(client, "collection_exists", None)
    if callable(collection_exists) and collection_exists(collection_name):
        return

    vector_size = 384
    get_embedding_size = getattr(client, "get_embedding_size", None)
    if callable(get_embedding_size):
        try:
            vector_size = int(get_embedding_size())
        except Exception:
            vector_size = 384

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def add_documents_to_qdrant(
    client: Any,
    collection_name: str,
    documents: list[str],
    metadata: list[dict[str, Any]],
    *,
    batch_size: int = 16,
) -> list[str]:
    if len(documents) != len(metadata):
        raise ValueError("documents and metadata must have the same length.")

    point_ids = [doc_id_to_point_id(item["doc_id"]) for item in metadata]
    payload = build_storage_metadata(metadata, documents)
    add = getattr(client, "add", None)
    if callable(add):
        try:
            inserted = add(
                collection_name=collection_name,
                documents=documents,
                metadata=payload,
                ids=point_ids,
                batch_size=batch_size,
            )
            return [str(item) for item in inserted]
        except Exception:
            pass

    ensure_collection_exists(client, collection_name)
    upload_collection = getattr(client, "upload_collection", None)
    if callable(upload_collection):
        from qdrant_client import models

        upload_collection(
            collection_name=collection_name,
            vectors=[models.Document(text=text, model=EMBEDDING_MODEL) for text in documents],
            payload=payload,
            ids=point_ids,
            batch_size=batch_size,
            wait=True,
        )
        return point_ids

    raise RuntimeError("Installed qdrant-client version does not expose a supported add/upload API.")


def search_documents(client: Any, collection_name: str, symbol: str, query_text: str, limit: int = 5) -> list[dict[str, Any]]:
    collection_exists = getattr(client, "collection_exists", None)
    if callable(collection_exists) and not collection_exists(collection_name):
        return []

    query_filter = build_symbol_filter(symbol)
    query = getattr(client, "query", None)
    if callable(query):
        try:
            results = query(
                collection_name=collection_name,
                query_text=query_text,
                query_filter=query_filter,
                limit=limit,
            )
            return [normalize_search_hit(hit) for hit in results or []]
        except Exception:
            pass

    query_points = getattr(client, "query_points", None)
    if callable(query_points):
        from qdrant_client import models

        response = query_points(
            collection_name=collection_name,
            query=models.Document(text=query_text, model=EMBEDDING_MODEL),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [normalize_search_hit(hit) for hit in getattr(response, "points", []) or []]

    raise RuntimeError("Installed qdrant-client version does not expose client.query() or client.query_points().")


def normalize_search_hit(hit: Any) -> dict[str, Any]:
    raw_metadata = safe_get(hit, "metadata", "payload", default={}) or {}
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {"value": as_clean_text(raw_metadata)}

    document = as_clean_text(safe_get(hit, "document", default=""))
    if not document and isinstance(metadata, dict):
        document = as_clean_text(metadata.pop(HIDDEN_DOCUMENT_KEY, ""))
    elif isinstance(metadata, dict):
        metadata.pop(HIDDEN_DOCUMENT_KEY, None)

    return {
        "score": float(safe_get(hit, "score", default=0.0) or 0.0),
        "metadata": metadata,
        "document": document,
    }


def build_event_extraction_prompt(symbol: str, user_question: str, hits: list[dict[str, Any]]) -> str:
    schema = {
        "symbol": symbol,
        "event_type": "string",
        "sentiment": "positive|negative|neutral|mixed",
        "importance": "low|medium|high|critical",
        "confidence": 0.0,
        "horizon": "immediate|days|weeks|months|unclear",
        "uncertainty": "string",
        "summary": "string",
        "risk_flags": ["string"],
        "cited_doc_ids": ["string"],
    }

    context_blocks: list[str] = []
    for index, hit in enumerate(hits, start=1):
        metadata = hit["metadata"]
        doc_id = metadata.get("doc_id", f"doc_{index}")
        title = metadata.get("title", "")
        doc_type = metadata.get("doc_type", "")
        published_at = metadata.get("published_at", "")
        source = metadata.get("source", "")
        url = metadata.get("url", "")
        snippet = shorten_text(hit["document"], 1400)
        context_blocks.append(
            "\n".join(
                [
                    f"[{doc_id}]",
                    f"title={title}",
                    f"type={doc_type}",
                    f"published_at={published_at}",
                    f"source={source}",
                    f"url={url}",
                    "text:",
                    snippet,
                ]
            )
        )

    joined_context = "\n\n".join(context_blocks) if context_blocks else "No supporting documents were retrieved."
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)

    return (
        "You are FinGPT performing financial event extraction.\n"
        "Do not give investment advice, price targets, or buy/sell recommendations.\n"
        "Read the retrieved documents, identify the single most important near-term event for the target symbol, "
        "and return exactly one JSON object.\n"
        "Return JSON only. Do not wrap it in markdown fences.\n\n"
        f"Target symbol: {symbol}\n"
        f"User question: {user_question}\n\n"
        "Required JSON schema:\n"
        f"{schema_json}\n\n"
        "Field guidance:\n"
        "- event_type should be a concise event label such as earnings, guidance, product, legal, supply_chain, regulation, analyst, or macro.\n"
        "- confidence must be a float between 0 and 1.\n"
        "- risk_flags must be a JSON array of short strings.\n"
        "- cited_doc_ids must only contain document ids from the provided context.\n"
        "- If evidence is weak or conflicting, explain that in uncertainty and lower confidence.\n\n"
        "Retrieved context:\n"
        f"{joined_context}\n"
    )


def shorten_text(text: str, max_chars: int = 500) -> str:
    cleaned = as_clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def extract_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("Model output does not contain a JSON object.")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "\"":
                in_string = False
            continue

        if char == "\"":
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("Model output ended before a complete JSON object was found.")
