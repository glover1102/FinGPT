from __future__ import annotations

from pipelines.fingpt.forecaster_features import build_forecaster_signal


def test_build_forecaster_signal_uses_sentiment_majority():
    signal = build_forecaster_signal(
        ticker="MSFT",
        annotations=[
            {"task": "sentiment", "label": "positive", "confidence": 0.9, "article_id": "a1"},
            {"task": "headline", "label": "price_up", "confidence": 0.8, "article_id": "a2"},
        ],
        structured_metrics={"price_return_20d": 0.04},
    )
    assert signal.ticker == "MSFT"
    assert signal.direction == "up"
    assert signal.confidence >= 0.5
    assert signal.evidence_doc_ids == ["a1", "a2"]


def test_build_forecaster_signal_is_neutral_when_evidence_is_mixed():
    signal = build_forecaster_signal(
        ticker="AAPL",
        annotations=[
            {"task": "sentiment", "label": "positive", "confidence": 0.7, "article_id": "a1"},
            {"task": "sentiment", "label": "negative", "confidence": 0.7, "article_id": "a2"},
        ],
        structured_metrics={},
    )
    assert signal.direction == "neutral"


def test_build_forecaster_signal_tolerates_malformed_confidence_and_metrics():
    signal = build_forecaster_signal(
        ticker="tsla",
        annotations=[
            {"task": "sentiment", "label": "bullish", "confidence": "bad", "article_id": "a1"},
            {"task": "headline", "label": "price_down", "confidence": None, "article_id": "a2"},
        ],
        structured_metrics={"price_return_20d": "bad"},
    )
    assert signal.ticker == "TSLA"
    assert signal.direction == "neutral"
    assert signal.confidence == 0.1
    assert signal.evidence_doc_ids == ["a1", "a2"]
