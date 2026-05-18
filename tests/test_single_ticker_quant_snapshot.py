from __future__ import annotations

from core.schemas.response import KeyMetric
from pipelines.orchestration.research_pipeline import _single_ticker_quant_snapshot


def test_single_ticker_quant_snapshot_is_traceable_and_regime_aware() -> None:
    metrics = [
        KeyMetric(
            name="MSFT latest close",
            value="424.62",
            unit="price",
            as_of="2026-04-24",
            context="reference close",
            source="yfinance:technical",
            freshness_status="fresh",
            evidence_doc_ids=["tech-doc"],
        ),
        KeyMetric(
            name="MSFT 1m price momentum",
            value="+16.03",
            unit="%",
            as_of="2026-04-24",
            context="20 trading day momentum",
            source="yfinance:technical",
            freshness_status="fresh",
            evidence_doc_ids=["tech-doc"],
        ),
        KeyMetric(
            name="MSFT SMA20 distance",
            value="+8.33",
            unit="%",
            as_of="2026-04-24",
            context="price versus SMA20",
            source="yfinance:technical",
            freshness_status="fresh",
            evidence_doc_ids=["tech-doc"],
        ),
        KeyMetric(
            name="MSFT SMA50 distance",
            value="+7.76",
            unit="%",
            as_of="2026-04-24",
            context="price versus SMA50",
            source="yfinance:technical",
            freshness_status="fresh",
            evidence_doc_ids=["tech-doc"],
        ),
        KeyMetric(
            name="MSFT RSI(14)",
            value="65.0",
            unit="index",
            as_of="2026-04-24",
            context="momentum oscillator",
            source="yfinance:technical",
            freshness_status="fresh",
            evidence_doc_ids=["tech-doc"],
        ),
    ]

    snapshot = _single_ticker_quant_snapshot("MSFT", metrics, [], [{"name": "MSFT RSI(14)"}])

    assert snapshot["asset_class"] == "single_ticker"
    assert snapshot["target"] == "MSFT"
    assert snapshot["as_of"] == "2026-04-24"
    assert snapshot["source"] == "deterministic_quant"
    assert snapshot["source_status"]["technical_metrics_present"] is True
    assert len(snapshot["metrics"]) == len(metrics)
    assert snapshot["metrics"][0]["evidence_doc_ids"] == ["tech-doc"]
    assert snapshot["regime"]["decision_bias"]
    assert snapshot["regime"]["confirming_signals"]
