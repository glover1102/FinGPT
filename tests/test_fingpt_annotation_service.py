from __future__ import annotations

from core.schemas.fingpt import FinGPTAnnotation
from pipelines.fingpt.annotation_service import (
    _document_id,
    _document_text,
    annotate_documents,
)


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def label_texts(self, task, texts):
        self.calls.append((task, list(texts)))
        return [
            FinGPTAnnotation(
                article_id=f"inline-{index}",
                task=task,
                label=f"{task}-label-{index}",
                confidence=0.7 + index / 10,
                source="fake-fingpt",
                model_id="fake-model",
                metadata={"rank": index},
            )
            for index, _text in enumerate(texts)
        ]


class FailingAdapter:
    def label_texts(self, task, texts):  # noqa: ANN001
        raise RuntimeError("adapter offline")


def test_document_id_prefers_stable_article_identifiers() -> None:
    assert _document_id({"id": "provider-id", "doc_id": "doc-id", "article_id": "article-id"}, 0) == "provider-id"
    assert _document_id({"doc_id": "doc-id", "article_id": "article-id"}, 1) == "doc-id"
    assert _document_id({"article_id": "article-id"}, 2) == "article-id"
    assert _document_id({"title": "No ID"}, 3) == "doc-3"


def test_document_text_extracts_title_and_body_fields() -> None:
    text = _document_text(
        {
            "title": "Strong earnings",
            "summary": "Revenue accelerated.",
            "text": "Collected news body uses text.",
            "content": "Detailed body.",
        }
    )

    assert "Strong earnings" in text
    assert "Revenue accelerated." in text
    assert "Collected news body uses text." in text
    assert "Detailed body." in text


def test_annotate_documents_maps_inline_results_to_original_ids_tickers_and_metadata() -> None:
    adapter = FakeAdapter()
    docs = [
        {"doc_id": "doc-a", "ticker": "msft", "title": "MSFT headline", "text": "MSFT body"},
        {"article_id": "article-b", "symbol": "aapl", "summary": "AAPL summary"},
        {"doc_id": "doc-empty", "ticker": "tsla"},
    ]

    result = annotate_documents(docs, adapter=adapter, enabled=True, tasks=["sentiment", "headline"])

    assert result.status == "success"
    assert result.documents_seen == 3
    assert len(result.annotations) == 4
    assert [call[0] for call in adapter.calls] == ["sentiment", "headline"]
    assert [annotation.article_id for annotation in result.annotations[:2]] == ["doc-a", "article-b"]
    assert [annotation.ticker for annotation in result.annotations[:2]] == ["MSFT", "AAPL"]
    assert result.annotations[0].metadata == {"rank": 0, "annotation_task": "sentiment"}
    assert result.annotations[2].metadata == {"rank": 0, "annotation_task": "headline"}
    assert result.annotations[0].source == "fake-fingpt"
    assert result.annotations[0].model_id == "fake-model"


def test_disabled_and_no_text_paths_skip_without_annotations() -> None:
    disabled = annotate_documents(
        [{"doc_id": "doc-a", "text": "body"}],
        adapter=FakeAdapter(),
        enabled=False,
        tasks=["sentiment"],
    )
    assert disabled.status == "disabled"
    assert disabled.documents_seen == 1
    assert disabled.annotations == []
    assert "disabled" in disabled.detail.lower()

    skipped = annotate_documents(
        [{"doc_id": "doc-a", "ticker": "MSFT"}],
        adapter=FakeAdapter(),
        enabled=True,
        tasks=["sentiment"],
    )
    assert skipped.status == "skipped"
    assert skipped.detail == "No annotatable document text."
    assert skipped.documents_seen == 1
    assert skipped.annotations == []


def test_adapter_exception_fails_open() -> None:
    result = annotate_documents(
        [{"doc_id": "doc-a", "ticker": "MSFT", "text": "body"}],
        adapter=FailingAdapter(),
        enabled=True,
        tasks=["sentiment"],
    )

    assert result.status == "skipped"
    assert "FinGPT annotation failed open:" in result.detail
    assert "adapter offline" in result.detail
    assert result.documents_seen == 1
    assert result.annotations == []
