import json
import logging
from pathlib import Path
from typing import Any
from datetime import date, datetime
import hashlib
import uuid

logger = logging.getLogger("core.utils.data_helpers")

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

import re

def as_clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        # 1. Normalize whitespace
        text = " ".join(value.split())
        # 2. Explicitly remove known LLM stop tokens that cause empty generations
        text = re.sub(r"<?\|im_end\|>?", " ", text)
        text = re.sub(r"<?\|endoftext\|>?", " ", text)
        text = re.sub(r"<?\|system\|>?", " ", text)
        text = re.sub(r"<?\|user\|>?", " ", text)
        text = re.sub(r"<?\|model\|>?", " ", text)
        # 3. Strip stray HTML/XML tags (e.g., <p>, <!--, etc.)
        # Matches <...>, but ignores common valid text symbols like < 5
        text = re.sub(r"<[^>\s][^>]*>", " ", text)
        # 4. Strip markdown tables, code fences, etc if malformed
        text = re.sub(r"```[a-zA-Z]*", " ", text)
        # 5. Strip stray brace/bracket clusters that confuse schema parsers
        text = re.sub(r"\{\{.*?\}\}", " ", text)
        return " ".join(text.split())
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

def shorten_text(text: str, max_chars: int = 500) -> str:
    cleaned = as_clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."

def extract_records(response: Any) -> list[Any]:
    if response is None: return []
    if isinstance(response, list): return response
    if isinstance(response, tuple): return list(response)
    if isinstance(response, dict):
        if isinstance(response.get("results"), list): return response["results"]
        if isinstance(response.get("data"), list): return response["data"]
        return [response]
    for attr in ("results", "data"):
        nested = getattr(response, attr, None)
        if nested is None: continue
        records = extract_records(nested)
        if records: return records
    for method_name in ("to_df", "to_dict", "model_dump", "dict"):
        method = getattr(response, method_name, None)
        if not callable(method): continue
        try: result = method()
        except Exception: continue
        if method_name == "to_df":
            try: return result.to_dict(orient="records")
            except Exception: continue
        records = extract_records(result)
        if records: return records
    return [response]

def normalize_news_records(records: list[Any], symbol: str, company_name: str = "", source_hint: str = "openbb") -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    rejected_count = 0
    for item in records:
        title = as_clean_text(safe_get(item, "title", "headline", default=""))
        excerpt = as_clean_text(safe_get(item, "excerpt", "summary", "teaser", default=""))
        body = as_clean_text(safe_get(item, "body", "content", "text", default=""))
        text = unique_text([title, excerpt, body])
        if not text: continue

        # --- Purity Check ---
        is_pure, reason = check_purity(text, symbol, company_name)
        if not is_pure:
            logger.debug(f"[PURITY_REJECT] {symbol} rejected document: {reason}")
            rejected_count += 1
            continue
        
        published_at = iso_datetime(safe_get(item, "date", "published_at", "published", "datetime"))
        source = as_clean_text(safe_get(item, "source", "publisher.name", "publisher", "provider", default=source_hint)) or source_hint
        url = as_clean_text(safe_get(item, "url", "link", "amp_url", default=""))
        seed = "|".join([symbol, title, published_at, url, text[:200]])
        doc_id = build_doc_id(symbol, "news", seed)
        documents.append({
            "doc_id": doc_id, "ticker": symbol, "symbol": symbol, "doc_type": "news", "source": source,
            "published_at": published_at, "title": title or f"{symbol} company news",
            "text": text, "url": url,
            "admitted_by": reason
        })
    
    if rejected_count > 0:
        logger.info(f"[PURITY] {symbol} news: admitted={len(documents)} rejected={rejected_count}")
        
    return deduplicate_documents(documents)

def normalize_transcript_records(records: list[Any], symbol: str, company_name: str = "", source_hint: str = "fmp") -> list[dict[str, Any]]:
    def normalize_quarter(val):
        t = as_clean_text(val).upper().replace("QUARTER", "").strip()
        if not t: return ""
        return t if t.startswith("Q") else f"Q{t}"

    documents: list[dict[str, Any]] = []
    rejected_count = 0
    for item in records:
        year = as_clean_text(safe_get(item, "year", default=""))
        quarter = normalize_quarter(safe_get(item, "quarter", default=""))
        published_at = iso_datetime(safe_get(item, "date", default=""))
        content = as_clean_text(safe_get(item, "content", "text", "body", default=""))
        if not content: continue

        # --- Purity Check ---
        # Note: Transcripts from FMP generally are pure, but we apply the tiered check for robustness
        is_pure, reason = check_purity(content, symbol, company_name)
        if not is_pure:
            logger.debug(f"[PURITY_REJECT] {symbol} transcript rejected: {reason}")
            rejected_count += 1
            continue

        title = f"{symbol} earnings call transcript {year} {quarter}".strip()
        chunks = chunk_text(content)
        total_chunks = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            seed = "|".join([symbol, year, quarter, published_at, str(index), chunk[:200]])
            doc_id = build_doc_id(symbol, "transcript", seed)
            chunk_title = title if total_chunks == 1 else f"{title} chunk {index}/{total_chunks}"
            documents.append({
                "doc_id": doc_id, "ticker": symbol, "symbol": symbol, "doc_type": "transcript",
                "source": source_hint, "published_at": published_at, "title": chunk_title,
                "text": chunk, "url": "",
                "admitted_by": reason
            })
    
    if rejected_count > 0:
        logger.info(f"[PURITY] {symbol} transcripts: admitted={len(documents)} rejected={rejected_count}")

    return deduplicate_documents(documents)


def check_purity(text: str, ticker: str, company_name: str) -> tuple[bool, str]:
    """
    Tiered identity check to prevent ticker cross-contamination.
    Returns (is_pure, reason).
    """
    if not text:
        return False, "empty_text"

    import re
    text_lower = text.lower()
    ticker_lower = ticker.lower()

    def parenthetical_tickers(value: str) -> set[str]:
        noise = {
            "adr", "ads", "aum", "cfo", "ceo", "eps", "etf", "ev", "fy",
            "gaap", "nav", "non", "pe", "qoq", "sec", "ttm", "usd", "yoy",
        }
        matches = re.findall(r"\(([a-z]{1,5}(?:\.[a-z]{1,2})?)\)", value)
        return {match for match in matches if match not in noise}

    def has_strong_etf_identity(value: str) -> bool:
        try:
            from core.utils.asset_classifier import classify

            profile = classify(ticker)
        except Exception:
            profile = None

        if not getattr(profile, "is_etf", False):
            return False

        issuer = str(getattr(profile, "issuer", "") or "").strip().lower()
        strong_patterns = [
            f"${ticker_lower}",
            f"({ticker_lower})",
            f":{ticker_lower}",
            f"{ticker_lower} etf",
            f"{ticker_lower} trust",
            f"{ticker_lower} fund",
            f"{ticker_lower} shares",
        ]
        if issuer:
            strong_patterns.append(f"{issuer} {ticker_lower}")
        if ticker_lower == "qqq":
            strong_patterns.extend(["invesco qqq", "nasdaq-100", "nasdaq 100"])
        return any(pattern in value for pattern in strong_patterns)

    try:
        from core.utils.asset_classifier import classify

        profile = classify(ticker)
    except Exception:
        profile = None

    if getattr(profile, "is_etf", False):
        conflicts = parenthetical_tickers(text_lower) - {ticker_lower}
        if conflicts and not has_strong_etf_identity(text_lower):
            found = ", ".join(sorted(conflicts)).upper()
            return False, f"conflicting_identity (found={found})"

    # 1. Exact Ticker Match (wrapped in boundaries or common patterns)
    # Pattern looks for $TICKER, (TICKER), or TICKER as a standalone word
    ticker_patterns = [
        f"${ticker_lower}",
        f"({ticker_lower})",
        f": {ticker_lower}",
        f" {ticker_lower} ",
        f" {ticker_lower}.",
        f" {ticker_lower},"
    ]
    if any(p in text_lower for p in ticker_patterns):
        return True, "ticker_match"

    # 2. Normalized Company Name Match
    # Clean company name: removal of Inc, Corp, Ltd, etc.
    def clean_name(name: str) -> str:
        name = name.lower()
        suffixes = ["inc.", "inc", "corp.", "corp", "ltd.", "ltd", "co.", "co", "corporation", "incorporated", "limited", "plc", "a.g.", "sa"]
        for s in suffixes:
            if name.endswith(" " + s):
                name = name[:-(len(s)+1)].strip()
            elif name.endswith("," + s):
                name = name[:-(len(s)+1)].strip()
            elif name.endswith("," + " " + s):
                name = name[:-(len(s)+2)].strip()
        return name.strip(",. ")

    base_name = clean_name(company_name)
    if base_name and len(base_name) > 3:
        if base_name in text_lower:
            return True, "company_name_match"

    # 3. Conflict Detection (Short circuit if other major ticker/name is the primary subject)
    # This is a precision rule. If we see common stock markers like (NASDAQ:XXX) or (NYSE:XXX) 
    # and it DOES NOT match the requested ticker, we flag it as an identity conflict.
    exchange_matches = re.findall(r"\((nasdaq|nyse|otc|otcqx):\s?([a-z.]+)\)", text_lower)
    for _, found_ticker in exchange_matches:
        if found_ticker != ticker_lower:
            return False, f"conflicting_identity (found={found_ticker.upper()})"

    return False, "no_identity_match"
