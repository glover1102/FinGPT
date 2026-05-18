import unittest
from unittest.mock import AsyncMock, patch

from core.schemas.request import DEFAULT_COLLECTION_SOURCES, UniversalRequest
from core.schemas.response import AnalysisResponse, CompareResponse
from core.schemas.topic import TopicResponse
from pipelines.orchestration.dispatch import dispatch_async
from pipelines.router.query_router import RoutedQuery


class DispatchRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_mode_with_ticker_hint_stays_on_ticker_pipeline(self):
        routed = RoutedQuery(
            mode="sector_macro",
            tickers=["QQQ", "SPY"],
            theme="macro backdrop",
            horizon="medium_term",
            reasoning="llm route",
        )
        response = AnalysisResponse(
            ticker="QQQ",
            question="macro backdrop?",
            status="success",
            summary="ok",
            sentiment="Neutral",
            conclusion="ok",
        )
        with patch("pipelines.orchestration.dispatch.route_query", return_value=routed), patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    ticker="QQQ",
                    question="macro backdrop?",
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.ticker, "QQQ")
        run_pipeline.assert_awaited_once()
        run_topic.assert_not_awaited()
        request = run_pipeline.await_args.args[0]
        self.assertEqual(request.ticker, "QQQ")
        self.assertEqual(request.sources, list(DEFAULT_COLLECTION_SOURCES))

    async def test_auto_mode_question_company_names_override_stale_ticker_hint(self):
        question = "\uc0bc\uc131\uc804\uc790\uc640 \ud558\uc774\ub2c9\uc2a4\uc758 \uc8fc\uac00\ub294 \ud569\ub9ac\uc801\uc778\uac00?"
        response = CompareResponse(
            question=question,
            tickers=["005930.KS", "000660.KS"],
            results={},
            elapsed_s=0.01,
            concurrency=1,
        )
        with patch(
            "pipelines.orchestration.dispatch._run_compare_async",
            new=AsyncMock(return_value=response),
        ) as run_compare, patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    ticker="TLT",
                    question=question,
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.tickers, ["005930.KS", "000660.KS"])
        run_compare.assert_awaited_once()
        request = run_compare.await_args.args[0]
        self.assertEqual(request.tickers[:2], ["005930.KS", "000660.KS"])
        run_pipeline.assert_not_awaited()
        run_topic.assert_not_awaited()

    async def test_auto_mode_kospi_inverse_question_drops_stale_tlt_hint(self):
        question = "\uc9c0\uae08 \ucf54\uc2a4\ud53c \uc778\ubc84\uc2a4 \ub4e4\uc5b4\uac00\uae30\uc5d0 \uc801\uc808\ud55c\uac00?"
        response = TopicResponse(
            question=question,
            theme=question,
            mode="sector_macro",
            status="partial",
            executive_summary="\ucf54\uc2a4\ud53c \uc778\ubc84\uc2a4\ub294 \ud55c\uad6d \uc99d\uc2dc \ud558\ubc29 \uc2dc\ub098\ub9ac\uc624\ub85c \ub530\ub85c \ud310\ub2e8\ud574\uc57c \ud569\ub2c8\ub2e4.",
            core_thesis="TLT\uac00 \uc544\ub2cc \ud55c\uad6d \uc778\ubc84\uc2a4 ETF\uc640 \ud55c\uad6d \uc2dc\uc7a5 proxy\ub97c \uae30\uc900\uc73c\ub85c \ubcf4\uc544\uc57c \ud569\ub2c8\ub2e4.",
        )
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    ticker="TLT",
                    question=question,
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.mode, "sector_macro")
        run_pipeline.assert_not_awaited()
        run_topic.assert_awaited_once()
        request = run_topic.await_args.args[0]
        self.assertEqual(request.related_tickers[:2], ["114800.KS", "252670.KS"])
        self.assertIn("EWY", request.related_tickers)
        self.assertNotIn("TLT", request.related_tickers)

    async def test_auto_mode_topic_question_drops_stale_proxy_hint(self):
        question = "credit spread widening risks"
        response = TopicResponse(
            question=question,
            theme=question,
            mode="sector_macro",
            status="partial",
            executive_summary="Credit conditions should be assessed with credit and rates proxies.",
            core_thesis="The stale GLD hint should not drive a credit-risk question.",
        )
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    ticker="GLD",
                    question=question,
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.mode, "sector_macro")
        run_pipeline.assert_not_awaited()
        run_topic.assert_awaited_once()
        request = run_topic.await_args.args[0]
        self.assertEqual(request.related_tickers, ["HYG", "LQD", "TLT"])
        self.assertNotIn("GLD", request.related_tickers)

    async def test_auto_mode_without_ticker_uses_explicit_ticker_in_question(self):
        response = AnalysisResponse(
            ticker="QQQ",
            question="QQQ macro backdrop?",
            status="success",
            summary="ok",
            sentiment="Neutral",
            conclusion="ok",
        )
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    question="QQQ거시 환경을 분석했을 때 매수하기 적정한지 분석해주세요",
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.ticker, "QQQ")
        run_pipeline.assert_awaited_once()
        run_topic.assert_not_awaited()
        request = run_pipeline.await_args.args[0]
        self.assertEqual(request.ticker, "QQQ")
        self.assertEqual(request.sources, list(DEFAULT_COLLECTION_SOURCES))

    async def test_topic_mode_preserves_ticker_hint_as_related_ticker(self):
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(return_value=AsyncMock()),
        ) as run_topic:
            await dispatch_async(
                UniversalRequest(
                    ticker="TLT",
                    question="금리 수준과 채권 가격이 매력적인지 분석",
                    mode_hint="topic",
                    sources=None,
                )
            )

        run_pipeline.assert_not_awaited()
        run_topic.assert_awaited_once()
        request = run_topic.await_args.args[0]
        self.assertEqual(request.related_tickers, ["TLT"])
        self.assertEqual(request.theme, "금리 수준과 채권 가격이 매력적인지 분석")
        self.assertEqual(run_topic.await_args.kwargs["mode"], "sector_macro")

    async def test_topic_mode_without_ticker_infers_broad_market_risk_proxies(self):
        response = TopicResponse(
            question="지금 시장이 무시하고 있는 리스크는 어떤 것이 있는지 분석 부탁드립니다",
            theme="지금 시장이 무시하고 있는 리스크는 어떤 것이 있는지 분석 부탁드립니다",
            mode="sector_macro",
            status="partial",
            executive_summary="시장 리스크는 주식, 신용, 금리 프록시를 함께 봐야 합니다.",
            core_thesis="SPY/QQQ/HYG/LQD/TLT를 함께 보면 equity-credit-rates divergence를 확인할 수 있습니다.",
        )
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    question="지금 시장이 무시하고 있는 리스크는 어떤 것이 있는지 분석 부탁드립니다",
                    mode_hint="topic",
                    sources=None,
                )
            )

        self.assertEqual(result.mode, "sector_macro")
        run_pipeline.assert_not_awaited()
        run_topic.assert_awaited_once()
        request = run_topic.await_args.args[0]
        self.assertEqual(request.related_tickers, ["SPY", "QQQ", "HYG", "LQD", "TLT"])
        self.assertEqual(run_topic.await_args.kwargs["mode"], "sector_macro")

    async def test_auto_mode_with_tlt_hint_uses_topic_pipeline(self):
        response = TopicResponse(
            question="금리와 채권 가격이 매력적인지 분석",
            theme="금리와 채권 가격이 매력적인지 분석",
            mode="sector_macro",
            status="success",
            executive_summary="장기채 판단은 금리 경로가 핵심입니다.",
            core_thesis="중장기 관점에서는 금리 하락 여지가 중요합니다.",
        )
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    ticker="TLT",
                    question="금리와 채권 가격이 매력적인지 분석",
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.mode, "sector_macro")
        run_pipeline.assert_not_awaited()
        run_topic.assert_awaited_once()
        request = run_topic.await_args.args[0]
        self.assertEqual(request.related_tickers, ["TLT"])

    async def test_ticker_mode_without_ticker_returns_validation_failure(self):
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    question="MSFT 리스크를 분석",
                    mode_hint="ticker",
                    sources=None,
                )
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.ticker, "TICKER_REQUIRED")
        self.assertIn("ticker", result.error_metadata)
        run_pipeline.assert_not_awaited()
        run_topic.assert_not_awaited()

    async def test_auto_mode_without_ticker_routes_rates_question_to_topic(self):
        response = TopicResponse(
            question="금리 수준과 장기채 매력도 분석",
            theme="금리 수준과 장기채 매력도 분석",
            mode="sector_macro",
            status="partial",
            executive_summary="장기금리와 듀레이션이 핵심입니다.",
            core_thesis="근거가 일부 부족해도 채권 playbook으로 분석합니다.",
        )
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    question="금리 수준과 장기채 매력도 분석",
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.mode, "sector_macro")
        run_pipeline.assert_not_awaited()
        run_topic.assert_awaited_once()
        request = run_topic.await_args.args[0]
        self.assertIn("TLT", request.related_tickers)

    async def test_auto_mode_without_ticker_routes_credit_risk_to_topic(self):
        response = TopicResponse(
            question="현재 드러나는 신용 리스크에는 어떤 것이 있나요?",
            theme="현재 드러나는 신용 리스크에는 어떤 것이 있나요?",
            mode="sector_macro",
            status="partial",
            executive_summary="크레딧 스프레드와 회사채 ETF가 핵심 근거입니다.",
            core_thesis="신용 리스크는 HYG/LQD/TLT proxy로 분석합니다.",
        )
        with patch(
            "pipelines.orchestration.dispatch.run_pipeline_async",
            new=AsyncMock(),
        ) as run_pipeline, patch(
            "pipelines.orchestration.dispatch.run_topic_pipeline_async",
            new=AsyncMock(return_value=response),
        ) as run_topic:
            result = await dispatch_async(
                UniversalRequest(
                    question="현재 드러나는 신용 리스크에는 어떤 것이 있나요?",
                    mode_hint="auto",
                    sources=None,
                )
            )

        self.assertEqual(result.mode, "sector_macro")
        run_pipeline.assert_not_awaited()
        run_topic.assert_awaited_once()
        request = run_topic.await_args.args[0]
        self.assertEqual(request.related_tickers[:3], ["HYG", "LQD", "TLT"])


if __name__ == "__main__":
    unittest.main()
