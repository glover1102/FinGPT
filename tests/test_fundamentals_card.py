import concurrent.futures
import unittest
from unittest.mock import patch

from pipelines.collect import fundamentals_card


class FundamentalsCardTests(unittest.TestCase):
    def test_yfinance_info_maps_to_card_fields(self):
        info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 3100000000000,
            "currentPrice": 213.55,
            "fiftyTwoWeekHigh": 237.23,
            "fiftyTwoWeekLow": 164.08,
            "trailingPE": 32.1,
            "forwardPE": 28.4,
            "priceToBook": 47.2,
            "profitMargins": 0.263,
            "revenueGrowth": 0.051,
            "earningsGrowth": 0.074,
            "dividendYield": 0.0045,
            "beta": 1.25,
            "recommendationMean": 2.1,
            "targetMeanPrice": 225.0,
            "numberOfAnalystOpinions": 35,
        }

        with patch.object(fundamentals_card, "_fetch_info", return_value=info):
            card = fundamentals_card.collect_fundamentals_card("aapl", timeout_s=1.0)

        self.assertIsNotNone(card)
        self.assertEqual(card.ticker, "AAPL")
        self.assertEqual(card.name, "Apple Inc.")
        self.assertEqual(card.market_cap, 3100000000000.0)
        self.assertEqual(card.forward_pe, 28.4)
        self.assertEqual(card.num_analysts, 35)

    def test_missing_optional_fields_remain_none(self):
        with patch.object(fundamentals_card, "_fetch_info", return_value={"longName": "Apple Inc."}):
            card = fundamentals_card.collect_fundamentals_card("AAPL", timeout_s=1.0)

        self.assertIsNotNone(card)
        self.assertIsNone(card.forward_pe)
        self.assertIsNone(card.market_cap)

    def test_timeout_returns_none(self):
        with patch.object(
            fundamentals_card,
            "_run_with_timeout",
            side_effect=concurrent.futures.TimeoutError(),
        ):
            card = fundamentals_card.collect_fundamentals_card("AAPL", timeout_s=0.01)

        self.assertIsNone(card)

    def test_etf_skips_card(self):
        with patch.object(fundamentals_card, "_fetch_info", side_effect=AssertionError("should not fetch")):
            card = fundamentals_card.collect_fundamentals_card("SPY", timeout_s=1.0)

        self.assertIsNone(card)


if __name__ == "__main__":
    unittest.main()
