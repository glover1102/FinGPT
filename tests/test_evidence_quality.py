from core.schemas.retrieval import RetrievalItem
from core.utils.evidence_quality import score_evidence_item


def _item(source: str, title: str, date: str, chunk: str) -> RetrievalItem:
    return RetrievalItem(source=source, title=title, date=date, chunk=chunk, score=0.9, metadata={"doc_id": "doc_1"})


def test_fred_source_scores_high_reliability():
    item = _item("FRED", "10Y Treasury Yield", "2026-05-01", "TLT yield metric 4.35% as of 2026-05-01")
    score = score_evidence_item(item, ticker="TLT", question="TLT 금리")
    assert score.source_type == "fred"
    assert score.reliability_score == 0.95
    assert score.overall_score > 0.75


def test_unknown_source_scores_low_reliability():
    item = _item("random blog", "Market thoughts", "2026-05-01", "generic commentary")
    score = score_evidence_item(item, ticker="AAPL", question="AAPL 리스크")
    assert score.source_type == "unknown"
    assert score.reliability_score == 0.30


def test_old_document_has_low_freshness():
    item = _item("Google News RSS", "AAPL old news", "2020-01-01", "AAPL revenue event")
    score = score_evidence_item(item, ticker="AAPL", question="AAPL revenue")
    assert score.freshness_score < 0.30


def test_specific_ticker_metric_date_scores_high_specificity():
    item = _item("CNBC", "MSFT earnings", "2026-05-01", "MSFT margin was 43% on 2026-05-01")
    score = score_evidence_item(item, ticker="MSFT", question="MSFT margin")
    assert score.specificity_score >= 0.80
