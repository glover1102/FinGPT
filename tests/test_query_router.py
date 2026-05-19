import unittest
from unittest.mock import patch

from core.utils.symbol_registry import known_symbol_tickers
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

    def test_korean_company_names_route_to_equity_tickers_without_llm(self):
        question = "\uc0bc\uc131\uc804\uc790\uc640 \ud558\uc774\ub2c9\uc2a4\uc758 \uc8fc\uac00\ub294 \ud569\ub9ac\uc801\uc778\uac00?"
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query(question)

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "multi_ticker")
        self.assertEqual(routed.tickers[:2], ["005930.KS", "000660.KS"])

    def test_korean_company_names_override_stale_non_equity_hint(self):
        question = "\uc0bc\uc131\uc804\uc790\uc640 \ud558\uc774\ub2c9\uc2a4\uc758 \uc8fc\uac00\ub294 \ud569\ub9ac\uc801\uc778\uac00?"
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query(question, hint_ticker="TLT")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "multi_ticker")
        self.assertEqual(routed.tickers[:2], ["005930.KS", "000660.KS"])
        self.assertNotIn("TLT", routed.tickers)

    def test_kospi_inverse_question_overrides_stale_tlt_hint(self):
        question = "\uc9c0\uae08 \ucf54\uc2a4\ud53c \uc778\ubc84\uc2a4 \ub4e4\uc5b4\uac00\uae30\uc5d0 \uc801\uc808\ud55c\uac00?"
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query(question, hint_ticker="TLT")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "sector_macro")
        self.assertEqual(routed.tickers[:2], ["114800.KS", "252670.KS"])
        self.assertIn("EWY", routed.tickers)
        self.assertNotIn("TLT", routed.tickers)

    def test_topic_question_overrides_stale_non_equity_hint(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query("credit spread widening risks", hint_ticker="GLD")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "sector_macro")
        self.assertEqual(routed.tickers, ["HYG", "LQD", "TLT"])
        self.assertNotIn("GLD", routed.tickers)
        self.assertIn("stale ticker hint", routed.reasoning)

    def test_single_korean_company_name_routes_to_single_equity(self):
        with patch.object(query_router, "_call_router_model") as call_model:
            routed = query_router.route_query("\uc0bc\uc131\uc804\uc790 \uc8fc\uac00\ub294 \uc9c0\uae08 \ud569\ub9ac\uc801\uc778\uac00?")

        call_model.assert_not_called()
        self.assertEqual(routed.mode, "single_ticker")
        self.assertEqual(routed.tickers, ["005930.KS"])

    def test_symbol_universe_company_aliases_route_without_llm(self):
        cases = [
            ("NVIDIA \uc8fc\uac00\ub294 \ud569\ub9ac\uc801\uc778\uac00?", ["NVDA"]),
            ("Broadcom\uacfc Oracle\uc758 \uc2e4\uc801 \ub9ac\uc2a4\ud06c", ["AVGO", "ORCL"]),
            ("Palantir \uc804\ub9dd", ["PLTR"]),
            ("Progressive \uc2e4\uc801", ["PGR"]),
            ("\uc5d4\ube44\ub514\uc544 \uc8fc\uac00", ["NVDA"]),
            ("SK\ud558\uc774\ub2c9\uc2a4 \uc8fc\uac00", ["000660.KS"]),
        ]

        with patch.object(query_router, "_call_router_model") as call_model:
            for question, expected in cases:
                routed = query_router.route_query(question)
                self.assertEqual(routed.tickers[: len(expected)], expected)
                expected_mode = "single_ticker" if len(expected) == 1 else "multi_ticker"
                self.assertEqual(routed.mode, expected_mode)

        call_model.assert_not_called()

    def test_symbol_aliases_avoid_common_word_and_short_prefix_false_positives(self):
        self.assertEqual(query_router.extract_explicit_tickers("now what is market risk?"), [])
        self.assertEqual(query_router.extract_explicit_tickers("SK\ud558\uc774\ub2c9\uc2a4 \uc8fc\uac00"), ["000660.KS"])
        self.assertEqual(query_router.extract_explicit_tickers("NOW \uc2e4\uc801"), ["NOW"])

    def test_explicit_uppercase_tickers_outside_curated_universe_route_without_llm(self):
        cases = [
            ("CRCL \uc8fc\uac00\ub294 \ud569\ub9ac\uc801\uc778\uac00?", ["CRCL"], "single_ticker"),
            ("CRCL\uc640 IONQ \ubaa8\uba58\ud140 \ube44\uad50", ["CRCL", "IONQ"], "multi_ticker"),
            ("MSTR: \ube44\ud2b8\ucf54\uc778 \ubbfc\uac10\ub3c4", ["MSTR"], "single_ticker"),
            ("$AI \uc2e4\uc801 \ub9ac\uc2a4\ud06c", ["AI"], "single_ticker"),
        ]

        with patch.object(query_router, "_call_router_model") as call_model:
            for question, expected, mode in cases:
                routed = query_router.route_query(question)
                self.assertEqual(routed.mode, mode)
                self.assertEqual(routed.tickers[: len(expected)], expected)

        call_model.assert_not_called()

    def test_unregistered_ticker_fallback_does_not_route_macro_abbreviations(self):
        for question in [
            "AI \ubc18\ub3c4\uccb4 \uc218\uc694\ub294 \uc5b4\ub5a4\uac00?",
            "AI: \ubc18\ub3c4\uccb4 \uc218\uc694\ub294 \uc5b4\ub5a4\uac00?",
            "ETF \uc2dc\uc7a5 \ub9ac\uc2a4\ud06c",
            "GDP\uac00 \uc8fc\uc2dd\uc5d0 \ubbf8\uce58\ub294 \uc601\ud5a5",
        ]:
            self.assertEqual(query_router.extract_explicit_tickers(question), [])

        self.assertEqual(query_router.extract_explicit_tickers("7203.T \uc804\ub9dd"), ["7203.T"])

    def test_class_share_dot_ticker_normalizes_to_yahoo_dash_symbol(self):
        cases = [
            ("BRK.B: \uc7a5\uae30 \ud22c\uc790 \ub9e4\ub825", ["BRK-B"]),
            ("$BRK.B \uc7a5\uae30 \ud22c\uc790 \ub9e4\ub825", ["BRK-B"]),
            ("BRK-B \uc7a5\uae30 \ud22c\uc790 \ub9e4\ub825", ["BRK-B"]),
        ]

        with patch.object(query_router, "_call_router_model") as call_model:
            for question, expected in cases:
                routed = query_router.route_query(question)
                self.assertEqual(routed.mode, "single_ticker")
                self.assertEqual(routed.tickers, expected)

        call_model.assert_not_called()

    def test_full_symbol_universe_tickers_are_extractable(self):
        missing = [
            ticker for ticker in sorted(known_symbol_tickers())
            if ticker not in query_router.extract_explicit_tickers(f"{ticker} outlook")
        ]

        self.assertEqual(missing, [])

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
