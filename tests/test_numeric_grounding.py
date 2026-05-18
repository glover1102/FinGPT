from core.schemas.response import KeyMetric
from core.utils.numeric_grounding import validate_key_metric, validate_key_metrics


def test_valid_metric_is_grounded():
    metric = KeyMetric(
        name="10Y Treasury Yield",
        value="4.35",
        unit="%",
        as_of="2026-05-01",
        source="FRED",
        evidence_doc_ids=["doc_1"],
    )
    checked, warnings = validate_key_metric(metric)
    assert warnings == []
    assert checked.grounding_status == "grounded"


def test_missing_unit_is_partially_grounded_warning():
    metric = KeyMetric(
        name="Revenue growth",
        value="12.0",
        as_of="2026-05-01",
        source="provider",
        evidence_doc_ids=["doc_1"],
    )
    checked, warnings = validate_key_metric(metric)
    assert any("unit missing" in warning for warning in warnings)
    assert checked.grounding_status == "partially_grounded"


def test_missing_source_and_grounding_is_ungrounded():
    metric = KeyMetric(name="EPS", value="3.2", unit="USD", as_of="2026-05-01")
    checked, warnings = validate_key_metric(metric)
    assert any("source missing" in warning for warning in warnings)
    assert any("no grounding mechanism" in warning for warning in warnings)
    assert checked.grounding_status == "ungrounded"


def test_numeric_grounding_rate_weights_partial_metrics():
    valid = KeyMetric(name="Price", value="100", unit="USD", as_of="2026-05-01", source="yfinance")
    partial = KeyMetric(name="RSI", value="70", as_of="2026-05-01", source="technical")
    _, summary, warnings = validate_key_metrics([valid, partial])
    assert warnings
    assert summary["metric_count"] == 2
    assert summary["numeric_grounding_rate"] == 0.75
