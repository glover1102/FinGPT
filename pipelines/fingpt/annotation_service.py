"""Fail-open FinGPT annotation service for collected research documents."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.schemas.fingpt import FinGPTAnnotation, FinGPTTask


_TEXT_FIELDS = ("title", "summary", "content", "document", "chunk", "text")
_ID_FIELDS = ("id", "doc_id", "article_id")


@dataclass(frozen=True)
class FinGPTAnnotationResult:
    status: str
    detail: str
    documents_seen: int = 0
    annotations: list[FinGPTAnnotation] = field(default_factory=list)


def _field_value(doc: Any, field_name: str) -> Any:
    if isinstance(doc, dict):
        return doc.get(field_name)
    return getattr(doc, field_name, None)


def _document_id(doc: Any, index: int) -> str:
    for field_name in _ID_FIELDS:
        value = _field_value(doc, field_name)
        clean = " ".join(str(value or "").split()).strip()
        if clean:
            return clean
    return f"doc-{index}"


def _stringify_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_stringify_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_stringify_text(item) for item in value.values())
    return " ".join(str(value).split()).strip()


def _document_text(doc: Any) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for field_name in _TEXT_FIELDS:
        text = _stringify_text(_field_value(doc, field_name))
        if text and text not in seen:
            parts.append(text)
            seen.add(text)
    return "\n\n".join(parts)


def _document_ticker(doc: Any) -> str:
    ticker = _field_value(doc, "ticker") or _field_value(doc, "symbol")
    return " ".join(str(ticker or "").split()).strip().upper()


def _annotation_index(annotation: FinGPTAnnotation, fallback_index: int) -> int:
    article_id = str(annotation.article_id or "")
    if article_id.startswith("inline-"):
        suffix = article_id.removeprefix("inline-")
        if suffix.isdigit():
            return int(suffix)
    return fallback_index


def annotate_documents(
    documents: list[Any],
    *,
    adapter: Any,
    enabled: bool,
    tasks: list[FinGPTTask],
) -> FinGPTAnnotationResult:
    docs = list(documents or [])
    if not enabled:
        return FinGPTAnnotationResult(
            status="disabled",
            detail="FinGPT annotation disabled.",
            documents_seen=len(docs),
        )

    texts: list[str] = []
    doc_map: list[dict[str, str]] = []
    for index, doc in enumerate(docs):
        text = _document_text(doc)
        if not text:
            continue
        texts.append(text)
        doc_map.append(
            {
                "article_id": _document_id(doc, index),
                "ticker": _document_ticker(doc),
            }
        )

    if not texts:
        return FinGPTAnnotationResult(
            status="skipped",
            detail="No annotatable document text.",
            documents_seen=len(docs),
        )

    annotations: list[FinGPTAnnotation] = []
    try:
        for task in tasks or []:
            task_annotations = adapter.label_texts(task, texts)
            for fallback_index, annotation in enumerate(task_annotations):
                source_index = _annotation_index(annotation, fallback_index)
                if source_index < 0 or source_index >= len(doc_map):
                    continue
                source_doc = doc_map[source_index]
                metadata = dict(annotation.metadata or {})
                metadata["annotation_task"] = task
                annotations.append(
                    annotation.model_copy(
                        update={
                            "article_id": source_doc["article_id"],
                            "ticker": source_doc["ticker"],
                            "metadata": metadata,
                        }
                    )
                )
    except Exception as exc:  # noqa: BLE001
        return FinGPTAnnotationResult(
            status="skipped",
            detail=f"FinGPT annotation failed open: {exc}",
            documents_seen=len(docs),
        )

    return FinGPTAnnotationResult(
        status="success",
        detail=f"Annotated {len(annotations)} labels across {len(texts)} documents.",
        documents_seen=len(docs),
        annotations=annotations,
    )
