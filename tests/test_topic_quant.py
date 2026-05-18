from __future__ import annotations

import unittest

from core.schemas.retrieval import RetrievalItem
from pipelines.analyze.topic_quant import build_topic_quant_snapshot, key_metrics_from_quant_snapshot


def _item(source: str, title: str, date: str, chunk: str, doc_id: str) -> RetrievalItem:
    return RetrievalItem(
        source=source,
        title=title,
        date=date,
        chunk=chunk,
        score=0.9,
        metadata={"doc_id": doc_id, "parent_doc_id": doc_id},
    )


class TopicQuantTests(unittest.TestCase):
    def test_tlt_quant_snapshot_builds_rates_curve_price_and_duration_metrics(self) -> None:
        context = [
            _item("FRED:DGS10", "10Y", "2026-04-20", "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity (DGS10) is 4.550 % as of 2026-04-20, changed +0.100 from 4.450 on 2026-01-20.", "dgs10"),
            _item("FRED:DGS2", "2Y", "2026-04-20", "Market Yield on U.S. Treasury Securities at 2-Year Constant Maturity (DGS2) is 4.150 % as of 2026-04-20, changed -0.050 from 4.200 on 2026-01-20.", "dgs2"),
            _item("FRED:DGS30", "30Y", "2026-04-20", "Market Yield on U.S. Treasury Securities at 30-Year Constant Maturity (DGS30) is 4.800 % as of 2026-04-20, changed +0.200 from 4.600 on 2026-01-20.", "dgs30"),
            _item("FRED:DFII10", "10Y real", "2026-04-20", "Market Yield on U.S. Treasury Securities at 10-Year Inflation-Indexed Constant Maturity (DFII10) is 2.150 % as of 2026-04-20, changed +0.050 from 2.100 on 2026-01-20.", "dfii10"),
            _item("FRED:FEDFUNDS", "Fed funds", "2026-04-20", "Effective Federal Funds Rate (FEDFUNDS) is 4.350 % as of 2026-04-20, changed -0.150 from 4.500 on 2026-01-20.", "fedfunds"),
            _item("yfinance:price", "TLT price", "2026-04-24", "TLT closed at 89.12 as of 2026-04-24, a -1.75% move over the last 30 trading days.", "tlt_price"),
        ]

        snapshot = build_topic_quant_snapshot("rates_bonds", "TLT", ["TLT"], context)
        metrics = key_metrics_from_quant_snapshot(snapshot)
        names = {item["name"] for item in metrics}

        self.assertIn("US 10Y Treasury yield", names)
        self.assertIn("US 30Y Treasury yield", names)
        self.assertIn("10Y-2Y Treasury curve", names)
        self.assertIn("TLT duration proxy", names)
        self.assertIn("Rate shock sensitivity (+/-100bp)", names)
        self.assertTrue(all(item["as_of"] for item in metrics))
        self.assertTrue(all("freshness_status" in item for item in metrics))
        self.assertEqual(snapshot["duration_or_proxy"]["value"], 16.8)
        self.assertEqual(len(snapshot["rate_shock_scenarios"]), 4)
        self.assertIn("market_structure", snapshot["substituted_buckets"])
        self.assertEqual(snapshot["as_of"], "2026-04-24")
        self.assertEqual(snapshot["source"], "deterministic_quant")
        self.assertIn(snapshot["freshness_status"], {"fresh", "stale"})
        self.assertGreaterEqual(snapshot["source_status"]["metric_count"], 5)
        self.assertTrue(snapshot["source_status"]["has_price_metrics"])
        self.assertTrue(snapshot["source_status"]["has_fred_metrics"])

    def test_credit_snapshot_uses_proxy_basket(self) -> None:
        context = [
            _item("yfinance:price", "HYG price", "2026-04-24", "HYG closed at 76.10 as of 2026-04-24, a -2.20% move over the last 30 trading days.", "hyg_price"),
            _item("yfinance:price", "LQD price", "2026-04-24", "LQD closed at 105.40 as of 2026-04-24, a -1.10% move over the last 30 trading days.", "lqd_price"),
            _item("yfinance:price", "SPY price", "2026-04-24", "SPY closed at 515.00 as of 2026-04-24, a +0.70% move over the last 30 trading days.", "spy_price"),
        ]

        snapshot = build_topic_quant_snapshot("credit", "credit risk", ["HYG", "LQD", "SPY"], context)
        metrics = key_metrics_from_quant_snapshot(snapshot)
        names = {item["name"] for item in metrics}

        self.assertEqual(snapshot["asset_class"], "credit")
        self.assertEqual(snapshot["as_of"], "2026-04-24")
        self.assertEqual(snapshot["source"], "deterministic_quant")
        self.assertIn("source_status", snapshot)
        self.assertIn("HYG price return (30 trading days)", names)
        self.assertIn("LQD price return (30 trading days)", names)
        self.assertIn("Credit duration proxy", names)

    def test_fx_crypto_and_commodity_snapshots_do_not_require_rates_docs(self) -> None:
        cases = [
            ("fx", "EURUSD=X", ["EURUSD=X"], "EURUSD=X closed at 1.08 as of 2026-04-24, a +1.20% move over the last 30 trading days."),
            ("commodity", "GLD", ["GLD"], "GLD closed at 225.50 as of 2026-04-24, a +3.40% move over the last 30 trading days."),
            ("crypto", "BTC-USD", ["BTC-USD"], "BTC-USD closed at 64000 as of 2026-04-24, a -4.80% move over the last 30 trading days."),
        ]
        for asset_class, target, related, text in cases:
            with self.subTest(asset_class=asset_class):
                snapshot = build_topic_quant_snapshot(asset_class, target, related, [_item("yfinance:price", target, "2026-04-24", text, f"{asset_class}_price")])
                self.assertEqual(snapshot["asset_class"], asset_class)
                self.assertEqual(snapshot["as_of"], "2026-04-24")
                self.assertEqual(snapshot["source"], "deterministic_quant")
                self.assertTrue(snapshot["source_status"]["has_price_metrics"])
                self.assertGreaterEqual(len(snapshot["metrics"]), 1)
                self.assertTrue(all(metric["as_of"] for metric in snapshot["metrics"]))

    def test_primary_asset_hint_prevents_gld_from_becoming_rates_snapshot(self) -> None:
        context = [
            _item("yfinance:price", "GLD price", "2026-04-24", "GLD closed at 225.50 as of 2026-04-24, a +3.40% move over the last 30 trading days.", "gld_price"),
            _item("yfinance:price", "TLT price", "2026-04-24", "TLT closed at 86.70 as of 2026-04-24, a -0.43% move over the last 30 trading days.", "tlt_price"),
        ]

        snapshot = build_topic_quant_snapshot("sector_theme", "실질금리와 달러 기준 GLD 매력도", ["GLD", "TLT"], context)

        self.assertEqual(snapshot["asset_class"], "commodity")
        self.assertEqual(snapshot["target"], "GLD")
        self.assertNotIn("duration_or_proxy", {metric.get("name") for metric in snapshot["metrics"]})


if __name__ == "__main__":
    unittest.main()
