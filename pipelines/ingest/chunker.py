from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class ChunkResult:
    chunk_id: str
    parent_doc_id: str
    chunk_index: int
    total_chunks: int
    text: str
    char_span: tuple[int, int]


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MIN_CHUNK_CHARS = 80


def _default_tokenizer(text: str) -> list[str]:
    # Conservative word approximation for bge-small's 512-token cap.
    return re.findall(r"\S+", text or "")


def _token_count(text: str, tokenizer: Callable[[str], list[str]]) -> int:
    return len(tokenizer(text))


def _split_long_segment(segment: str, max_words: int, overlap_words: int) -> list[str]:
    words = segment.split()
    if len(words) <= max_words:
        return [segment.strip()]
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + max_words)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(end - overlap_words, start + 1)
    return chunks


def _atomic_segments(text: str, max_words: int, overlap_words: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    segments: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph.split()) <= max_words:
            segments.append(paragraph)
            continue
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]
        if len(sentences) <= 1:
            segments.extend(_split_long_segment(paragraph, max_words, overlap_words))
            continue
        for sentence in sentences:
            if len(sentence.split()) <= max_words:
                segments.append(sentence)
            else:
                segments.extend(_split_long_segment(sentence, max_words, overlap_words))
    return segments


def _locate_span(text: str, chunk_text: str, start_at: int) -> tuple[int, int]:
    needle = chunk_text[: min(len(chunk_text), 120)].strip()
    if not needle:
        return start_at, start_at
    found = text.find(needle, start_at)
    if found < 0:
        found = text.find(needle)
    if found < 0:
        return start_at, min(len(text), start_at + len(chunk_text))
    return found, min(len(text), found + len(chunk_text))


def chunk_document(
    *,
    text: str,
    doc_id: str,
    target_tokens: int = 512,
    overlap_tokens: int = 64,
    tokenizer: Optional[Callable[[str], list[str]]] = None,
    title: str | None = None,
) -> list[ChunkResult]:
    """
    Split text into overlapping chunks, preferring paragraph and sentence
    boundaries before falling back to a sliding word window.
    """
    cleaned = (text or "").strip()
    if not cleaned or not str(doc_id or "").strip():
        return []

    tokenize = tokenizer or _default_tokenizer
    max_words = max(1, int(target_tokens * 0.75))
    overlap_words = max(0, int(overlap_tokens * 0.75))
    prefix = f"[{title.strip()}] " if title and title.strip() else ""
    prefix_tokens = _token_count(prefix, tokenize)
    chunk_budget = max(1, max_words - prefix_tokens)

    atoms = _atomic_segments(cleaned, chunk_budget, overlap_words)
    if not atoms:
        return []

    raw_chunks: list[tuple[str, tuple[int, int]]] = []
    current_parts: list[str] = []
    search_from = 0

    def flush() -> None:
        nonlocal current_parts, search_from
        if not current_parts:
            return
        body = "\n\n".join(current_parts).strip()
        if body:
            span = _locate_span(cleaned, current_parts[0], search_from)
            search_from = span[1]
            if len(body) >= _MIN_CHUNK_CHARS or not raw_chunks:
                raw_chunks.append((body, span))
        current_parts = []

    for atom in atoms:
        tentative = "\n\n".join([*current_parts, atom]).strip()
        if current_parts and _token_count(tentative, tokenize) > chunk_budget:
            flush()
            if overlap_words and raw_chunks:
                previous_words = raw_chunks[-1][0].split()
                overlap = " ".join(previous_words[-overlap_words:]).strip()
                if overlap:
                    current_parts = [overlap]
        current_parts.append(atom)
    flush()

    filtered = [(body, span) for body, span in raw_chunks if len(body) >= _MIN_CHUNK_CHARS or len(raw_chunks) == 1]
    total = len(filtered)
    results: list[ChunkResult] = []
    for index, (body, span) in enumerate(filtered):
        chunk_text = f"{prefix}{body}".strip()
        results.append(
            ChunkResult(
                chunk_id=f"{doc_id}__c{index:02d}",
                parent_doc_id=doc_id,
                chunk_index=index,
                total_chunks=total,
                text=chunk_text,
                char_span=span,
            )
        )
    return results
