import json
from typing import List, Dict, Any

def shorten_text(text: str, max_chars: int = 500) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."

def build_event_extraction_prompt(symbol: str, user_question: str, hits: List[Dict[str, Any]]) -> str:
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

    context_blocks = []
    for index, hit in enumerate(hits, start=1):
        metadata = hit["metadata"]
        doc_id = metadata.get("doc_id", f"doc_{index}")
        snippet = shorten_text(hit["document"], 1400)
        context_blocks.append(f"[{doc_id}]\ntitle={metadata.get('title', '')}\ntype={metadata.get('doc_type', '')}\npublished_at={metadata.get('published_at', '')}\ntext:\n{snippet}")

    joined_context = "\n\n".join(context_blocks) if context_blocks else "No supporting documents were retrieved."
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)

    return (
        "You are FinGPT performing financial event extraction.\n"
        "Return exactly one JSON object. Do not wrap it in markdown fences.\n\n"
        f"Target symbol: {symbol}\n"
        f"User question: {user_question}\n\n"
        "Required JSON schema:\n"
        f"{schema_json}\n\n"
        "Retrieved context:\n"
        f"{joined_context}\n"
    )

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
