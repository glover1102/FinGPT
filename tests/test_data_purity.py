import unittest

from core.utils.data_helpers import check_purity


class DataPurityTests(unittest.TestCase):
    def test_rejects_etf_news_when_article_is_about_another_ticker(self):
        text = (
            "Founders Capital bought Plains GP Holdings (PAGP) stock during the first quarter. "
            "PAGP shares trade near a 52-week high and remain linked to energy prices. "
            "This appeared in a feed result mentioning QQQ stock."
        )

        is_pure, reason = check_purity(text, "QQQ", "QQQ")

        self.assertFalse(is_pure)
        self.assertIn("conflicting_identity", reason)
        self.assertIn("PAGP", reason)

    def test_allows_etf_news_with_strong_fund_identity(self):
        text = (
            "Invesco QQQ Trust (QQQ) tracks the Nasdaq-100 and remains one of the most "
            "heavily traded ETFs by volume."
        )

        is_pure, reason = check_purity(text, "QQQ", "QQQ")

        self.assertTrue(is_pure)
        self.assertEqual(reason, "ticker_match")


if __name__ == "__main__":
    unittest.main()
