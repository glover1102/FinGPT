from __future__ import annotations

from pipelines.data_mart.context.structured_context import (
    build_structured_context,
    structured_context_metrics,
    structured_context_to_retrieval_item,
)
from pipelines.data_mart.models import MacroObservation, PriceBar
from pipelines.data_mart.storage import repository


def test_structured_context_builds_price_macro_and_retrieval_item(tmp_path) -> None:
    db_path = tmp_path / "research_mart.db"
    repository.upsert_prices(
        [
            PriceBar(ticker="TLT", date="2026-04-30", close=90, adjusted_close=90, source="test"),
            PriceBar(ticker="TLT", date="2026-05-01", close=91, adjusted_close=91, source="test"),
        ],
        db_path=db_path,
    )
    repository.upsert_macro_observations(
        [MacroObservation(series_id="DGS10", date="2026-05-01", value=4.3, source="test")],
        db_path=db_path,
    )

    context = build_structured_context("TLT", db_path=db_path)
    item = structured_context_to_retrieval_item(context)
    metrics = structured_context_metrics(context)

    assert context["target"] == "TLT"
    assert context["price_snapshot"][0]["adjusted_close"] == 91
    assert context["macro_snapshot"][0]["series_id"] == "DGS10"
    assert item is not None
    assert item.metadata["doc_type"] == "structured_context"
    assert "Do not invent numbers" in item.chunk
    assert any(metric["name"] == "TLT data-mart adjusted close" for metric in metrics)
    assert all(metric["as_of"] for metric in metrics)


def test_structured_context_reports_no_data_without_item(tmp_path) -> None:
    context = build_structured_context("MSFT", db_path=tmp_path / "research_mart.db")

    assert context["status"] in {"partial", "no_data"}
    assert structured_context_to_retrieval_item(context) is None
