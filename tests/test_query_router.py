import unittest
from unittest.mock import patch

from pipelines.router import query_router


class QueryRouterTests(unittest.TestCase):
    def test_llm_router_payload_is_normalized(self):
        payload = {
            "mode": "multi_ticker",
            "tickers": ["aapl", "MSFT", "BADTICKER"],
            "theme": "AI comparison",
            "horizon": "unspecified",
            "reasoning": "comparison",
        }
        with patch.object(query_router, "_call_router_model", return_value=payload):
            routed = query_router.route_query("Compare AAPL and MSFT")

        self.assertEqual(routed.mode, "multi_ticker")
        self.assertEqual(routed.tickers, ["AAPL", "MSFT"])

    def test_attached_korean_suffix_ticker_routes_to_single_ticker_without_llm(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query("QQQ거시 환경을 분석했을 때 매수하기 적정한지 분석해주세요")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "single_ticker")
        self.assertEqual(routed.tickers, ["QQQ"])

    def test_explicit_ticker_overrides_llm_topic_misroute(self):
        payload = {
            "mode": "sector_macro",
            "tickers": ["QQQ", "SPY"],
            "theme": "growth stocks",
            "horizon": "medium_term",
            "reasoning": "macro topic",
        }
        with patch.object(query_router, "_call_router_model", return_value=payload) as call_model:
            routed = query_router.route_query("QQQ macro backdrop")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "single_ticker")
        self.assertEqual(routed.tickers, ["QQQ"])

    def test_non_equity_proxy_ticker_routes_to_topic_without_llm(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query(
                "TLT 거시경제를 다방면으로 분석해봤을 때 지금의 금리 수준과 채권 가격이 매력적인지 분석"
            )

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "sector_macro")
        self.assertEqual(routed.tickers, ["TLT"])
        self.assertIn("rates", routed.reasoning)

    def test_korean_rates_question_without_ticker_gets_tlt_proxy(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query("금리 수준과 장기채 매력도 분석")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "sector_macro")
        self.assertEqual(routed.tickers, ["TLT"])

    def test_korean_ai_semiconductor_topic_does_not_require_ticker(self):
        with patch.object(query_router, "_call_router_model", side_effect=RuntimeError("offline")):
            routed = query_router.route_query("AI 반도체 공급망 전망")

        self.assertEqual(routed.mode, "sector_macro")
        self.assertTrue(routed.tickers)

    def test_korean_credit_risk_question_uses_credit_proxies_without_llm(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query("현재 드러나는 신용 리스크에는 어떤 것이 있나요?")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "sector_macro")
        self.assertEqual(routed.tickers, ["HYG", "LQD", "TLT"])
        self.assertIn("credit", routed.reasoning)

    def test_clean_korean_broad_market_risk_uses_cross_asset_proxies_without_gold_false_positive(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query("지금 시장이 무시하고 있는 리스크는 어떤 것이 있는지 분석 부탁드립니다")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "sector_macro")
        self.assertEqual(routed.tickers, ["SPY", "QQQ", "HYG", "LQD", "TLT"])
        self.assertNotIn("GLD", routed.tickers)
        self.assertIn("broad market risk", routed.reasoning)

    def test_clean_korean_gold_question_still_uses_commodity_proxies(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query("금 가격과 달러를 기준으로 지금 원자재가 매력적인지 분석")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "sector_macro")
        self.assertEqual(routed.tickers[:2], ["GLD", "USO"])

    def test_clean_korean_macro_questions_route_without_llm(self):
        cases = [
            ("금리 수준과 장기채 매력도 분석", "sector_macro", ["TLT"]),
            ("현재 드러나는 신용 리스크에는 어떤 것이 있나요?", "sector_macro", ["HYG", "LQD", "TLT"]),
            ("AI 반도체 공급망 전망", "sector_macro", ["AMAT", "ASML", "KLAC"]),
            ("비트코인 유동성과 현물 ETF flow 분석", "sector_macro", ["BTC-USD"]),
        ]

        with patch.object(query_router, "_call_router_model") as call_model:
            for question, expected_mode, expected_tickers in cases:
                routed = query_router.route_query(question)
                self.assertEqual(routed.mode, expected_mode)
                self.assertEqual(routed.tickers[: len(expected_tickers)], expected_tickers)

        call_model.assert_not_called()

    def test_non_equity_hint_routes_to_topic_without_llm(self):
        cases = [
            ("TLT", "지금 매력적인지 분석", ["TLT"]),
            ("GLD", "금 가격과 실질금리를 감안해 매력적인지 분석", ["GLD", "USO"]),
            ("EURUSD=X", "달러와 유로 환율 환경을 분석", ["EURUSD=X"]),
            ("BTC-USD", "비트코인 유동성과 ETF flow를 분석", ["BTC-USD"]),
        ]

        with patch.object(query_router, "_call_router_model") as call_model:
            for hint, question, expected_prefix in cases:
                routed = query_router.route_query(question, hint_ticker=hint)
                self.assertEqual(routed.mode, "sector_macro")
                self.assertEqual(routed.tickers[: len(expected_prefix)], expected_prefix)

        call_model.assert_not_called()

    def test_regex_fallback_classifies_sample_set(self):
        cases = [
            ("What are AAPL's near-term risks?", "single_ticker"),
            ("Compare AAPL and MSFT AI catalysts", "multi_ticker"),
            ("Fed의 2026년 금리 경로가 성장주에 미치는 영향은?", "sector_macro"),
            ("반도체 후공정 업체 약세 원인은?", "sector_macro"),
            ("현재 원유 선물의 백워데이션 상태가 의미하는 바는?", "concept"),
            ("What does oil backwardation signal?", "concept"),
            ("How does the sector backdrop affect XLK?", "single_ticker"),
            ("ASML and KLAC weakness drivers", "multi_ticker"),
            ("industry margin pressure in semiconductors", "sector_macro"),
            ("Explain yield curve inversion", "concept"),
        ]

        correct = 0
        with patch.object(query_router, "_call_router_model", side_effect=RuntimeError("offline")):
            for question, expected in cases:
                routed = query_router.route_query(question)
                if routed.mode == expected:
                    correct += 1

        self.assertGreaterEqual(correct, 8)


if __name__ == "__main__":
    unittest.main()
