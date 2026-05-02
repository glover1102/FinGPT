import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipelines.collect.models import SourceCollectionResult
from pipelines.collect import topic_collector


class TopicCollectorTests(unittest.TestCase):
    def test_clean_korean_theme_terms_infer_related_tickers(self):
        self.assertEqual(topic_collector._infer_theme_tickers("금리와 장기채 매력도", [])[:1], ["TLT"])
        self.assertIn("SOXX", topic_collector._infer_theme_tickers("AI 반도체 공급망", []))
        self.assertIn("HYG", topic_collector._infer_theme_tickers("신용 리스크", []))

    def test_related_bond_etf_uses_asset_macro_and_etf_profile_collectors(self):
        settings = SimpleNamespace(
            fred_api_key="fred-key",
            macro_price_lookback_days=90,
            raw_dir=Path("."),
        )
        macro_doc = {
            "doc_id": "tlt_macro",
            "ticker": "TLT",
            "symbol": "TLT",
            "doc_type": "macro",
            "source": "FRED:DGS30",
            "published_at": "2026-04-20",
            "title": "30Y Treasury yield",
            "text": "30Y Treasury yield moved higher.",
        }
        etf_doc = {
            "doc_id": "tlt_profile",
            "ticker": "TLT",
            "symbol": "TLT",
            "doc_type": "etf_profile",
            "source": "issuer:iShares",
            "published_at": "2026-04-20",
            "title": "TLT profile",
            "text": "TLT is a long-duration Treasury ETF.",
        }

        with patch.object(topic_collector, "load_settings", return_value=settings), \
             patch.object(topic_collector, "_collect_macro_series", return_value=(SourceCollectionResult("topic_macro", "empty", 0, 0.0, ""), [])), \
             patch.object(topic_collector, "_collect_google_topic_news", return_value=(SourceCollectionResult("topic_news", "empty", 0, 0.0, ""), [])), \
             patch.object(topic_collector, "collect_macro_bundle", return_value=(SourceCollectionResult("macro", "ok", 1, 0.1, "ok"), [macro_doc], [])) as macro, \
             patch.object(topic_collector, "collect_etf_profile", return_value=(SourceCollectionResult("etf_profile", "ok", 1, 0.1, "ok"), [etf_doc])), \
             patch.object(topic_collector, "write_documents"):
            outcome = topic_collector.collect_topic_bundle(
                "금리 수준과 채권 가격이 매력적인지 분석",
                "금리와 채권 ETF",
                ["TLT"],
                60,
            )

        self.assertGreaterEqual(macro.call_count, 1)
        self.assertEqual(macro.call_args_list[0].args[0].ticker, "TLT")
        self.assertEqual({doc["doc_id"] for doc in outcome.documents}, {"tlt_macro", "tlt_profile"})
        self.assertIn("tlt_macro", outcome.current_doc_ids)
        self.assertTrue(any(result.source == "topic_asset:TLT" for result in outcome.source_results))


if __name__ == "__main__":
    unittest.main()
