from __future__ import annotations

import unittest

import pandas as pd

from core.schemas.retrieval import RetrievalItem
from core.utils.technical_indicators import (
    compute_technical_metrics_from_history,
    parse_technical_metrics_from_text,
    technical_metrics_document_text,
    technical_metrics_from_retrieval_items,
)


class TechnicalIndicatorTests(unittest.TestCase):
    def test_compute_technical_metrics_has_as_of_and_standard_indicators(self) -> None:
        index = pd.date_range("2026-01-01", periods=260, freq="B")
        close = pd.Series([100 + i * 0.25 for i in range(260)], index=index)
        volume = pd.Series([1_000_000 + i * 1000 for i in range(260)], index=index)
        history = pd.DataFrame({"Close": close, "Volume": volume})

        metrics = compute_technical_metrics_from_history(history, "SPY", evidence_doc_ids=["tech-doc"])
        names = {item["name"] for item in metrics}

        self.assertIn("SPY RSI(14)", names)
        self.assertIn("SPY MACD 히스토그램", names)
        self.assertIn("SPY SMA20 대비 가격 괴리", names)
        self.assertIn("SPY SMA200 대비 가격 괴리", names)
        self.assertIn("SPY 20일 실현 변동성", names)
        self.assertTrue(all(item["as_of"] == "2026-12-30" for item in metrics))
        self.assertTrue(all(item["evidence_doc_ids"] == ["tech-doc"] for item in metrics))

    def test_document_roundtrip_preserves_metric_schema(self) -> None:
        metrics = [
            {
                "name": "SPY RSI(14)",
                "value": "61.2",
                "unit": "index",
                "as_of": "2026-04-24",
                "context": "momentum",
                "source": "yfinance:technical",
                "freshness_status": "fresh",
                "evidence_doc_ids": ["doc-1"],
            }
        ]
        text = technical_metrics_document_text("SPY", metrics)
        parsed = parse_technical_metrics_from_text(text, doc_id="doc-1")

        self.assertEqual(parsed[0]["name"], "SPY RSI(14)")
        self.assertEqual(parsed[0]["as_of"], "2026-04-24")
        self.assertEqual(parsed[0]["evidence_doc_ids"], ["doc-1"])

    def test_retrieval_parser_dedupes_technical_metrics(self) -> None:
        metrics = [
            {
                "name": "SPY RSI(14)",
                "value": "61.2",
                "unit": "index",
                "as_of": "2026-04-24",
                "context": "momentum",
                "source": "yfinance:technical",
                "freshness_status": "fresh",
                "evidence_doc_ids": ["doc-1"],
            }
        ]
        text = technical_metrics_document_text("SPY", metrics)
        items = [
            RetrievalItem(source="yfinance:technical", title="tech", date="2026-04-24", chunk=text, score=1.0, metadata={"doc_id": "doc-1"}),
            RetrievalItem(source="yfinance:technical", title="tech", date="2026-04-24", chunk=text, score=1.0, metadata={"doc_id": "doc-1"}),
        ]

        parsed = technical_metrics_from_retrieval_items(items)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "SPY RSI(14)")


if __name__ == "__main__":
    unittest.main()
