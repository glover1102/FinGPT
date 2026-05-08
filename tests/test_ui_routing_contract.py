from pathlib import Path
import re
import unittest


APP_JS = Path(__file__).resolve().parents[1] / "app" / "web" / "app.js"
INDEX_HTML = Path(__file__).resolve().parents[1] / "app" / "web" / "index.html"
STYLES_CSS = Path(__file__).resolve().parents[1] / "app" / "web" / "styles.css"


class UiRoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_JS.read_text(encoding="utf-8")

    def test_non_compare_runs_use_universal_stream(self):
        match = re.search(r"async function runAnalysis\(e\) \{(?P<body>.*?)\n\}\n\n// ---------- Compare mode", self.source, re.S)
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("runStreamAnalysis(API.universalStream, payload, payload)", body)
        self.assertNotIn("API.stream", body)
        self.assertNotIn("useUniversal", body)

    def test_fingpt_status_ui_contract(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="fingptStatus"', html)
        self.assertIn("function renderFinGPTStatus", self.source)
        self.assertIn("renderFinGPTStatus(state.config)", self.source)
        self.assertIn("FinGPT 보조 기능 비활성 · 기본 분석 경로에는 영향 없음", self.source)
        self.assertIn("FinGPT 보조 기능 활성:", self.source)
        self.assertIn("is-enabled", self.source)

    def test_intent_normalizer_preserves_tickerless_topic_path(self):
        self.assertIn("function normalizeResearchIntent", self.source)
        self.assertIn("auto_topic", self.source)
        self.assertIn("extracted_ticker", self.source)
        self.assertIn("ticker 없이 질의 가능", self.source)

    def test_question_ticker_inference_supports_explicit_universe_fallback(self):
        self.assertIn("function matchExplicitTickerPrefix", self.source)
        self.assertIn("function isSupportedExplicitTickerToken", self.source)
        self.assertIn("UNREGISTERED_TICKER_STOPWORDS", self.source)
        self.assertIn('source: "explicit_prefix"', self.source)
        self.assertIn("classShare", self.source)
        self.assertIn("[A-Z]{3,5}", self.source)
        self.assertIn("\\d{6}\\.(?:KS|KQ)", self.source)

    def test_every_declared_progress_stage_exists_in_dom(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        stage_match = re.search(r"const STAGES = \[(?P<items>.*?)\];", self.source, re.S)
        self.assertIsNotNone(stage_match)
        stages = re.findall(r'"([^"]+)"', stage_match.group("items"))
        dom_stages = set(re.findall(r'data-stage="([^"]+)"', html))
        self.assertTrue(stages)
        self.assertEqual(set(stages), dom_stages)

    def test_progress_stage_helpers_are_null_safe(self):
        self.assertIn("function progressNode(stage)", self.source)
        self.assertIn("if (!node) return", self.source)

    def test_quant_backtest_workbench_uses_artifact_endpoint(self):
        match = re.search(r"async function runHomeBacktest\(\) \{(?P<body>.*?)\n\}\n\nasync function loadQuantRunHistory", self.source, re.S)
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("fetch(API.quantBacktest", body)
        self.assertIn("attachBenchmarkComparison(data", body)
        self.assertIn("renderQuantBacktestResult(enriched", body)
        self.assertIn("renderQuantDiagnosticsPanel(data)", self.source)
        self.assertIn("loadQuantRunHistory(true)", body)
        self.assertNotIn("fetch(API.backtestRun", body)

    def test_financial_curve_charts_have_axes_hover_tooltips_and_larger_canvas(self):
        css = STYLES_CSS.read_text(encoding="utf-8")
        self.assertIn("function renderChartYAxis", self.source)
        self.assertIn("function initChartTooltips", self.source)
        self.assertIn("data-chart-tooltip", self.source)
        self.assertIn("formatCurveReturn", self.source)
        self.assertIn("const width = 620;", self.source)
        self.assertIn("const height = 190;", self.source)
        self.assertIn("const width = 760;", self.source)
        self.assertIn("const height = 230;", self.source)
        self.assertIn(".chart-y-label", css)
        self.assertIn(".chart-tooltip", css)
        self.assertIn("height: 170px;", css)
        self.assertIn("height: 220px;", css)
        self.assertIn("height: 190px;", css)

    def test_asset_detail_supports_date_view_and_return_curve_controls(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        css = STYLES_CSS.read_text(encoding="utf-8")
        for marker in [
            'id="assetDetailRange"',
            'id="assetDetailStartDate"',
            'id="assetDetailEndDate"',
            'id="assetDetailView"',
            'id="assetDetailBenchmark"',
            'id="assetDetailBenchmarkCompare"',
        ]:
            self.assertIn(marker, html)
        for marker in [
            "function assetDetailOptionsFromControls",
            "function filterPriceRowsByAssetOptions",
            "function renderAssetReturnLineChart",
            "function renderAssetBenchmarkComparison",
            "function renderAssetDetailSections",
            'renderDecisionLineChart(curve, "return", "수익률 곡선"',
            "renderNormalizedComparisonChart",
        ]:
            self.assertIn(marker, self.source)
        self.assertIn(".asset-detail-form", css)
        self.assertIn(".asset-detail-chart-grid", css)

    def test_quant_run_history_can_reopen_artifacts(self):
        self.assertIn("API.quantBacktestBundle", self.source)
        self.assertIn("function loadQuantBacktestArtifact", self.source)
        self.assertIn("data-quant-run-id", self.source)

    def test_market_heatmap_has_manual_refresh_and_display_limit(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="homeHeatmapRefresh"', html)
        self.assertIn("HEATMAP_DISPLAY_MAX", self.source)
        self.assertIn("loadDashboardEquityHeatmap(true)", self.source)
        self.assertIn("표시 ${escapeHtml(_fmtNumber(displayItems.length))}", self.source)

    def _symbol_list_count(self, const_name: str) -> int:
        match = re.search(rf"const {const_name} = symbolList\(`(?P<body>.*?)`\);", self.source, re.S)
        self.assertIsNotNone(match, const_name)
        return len([token for token in match.group("body").split() if token])

    def test_quant_symbol_catalog_expanded_universe_contract(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertEqual(self._symbol_list_count("US_LARGE_CAP_SYMBOLS"), 200)
        self.assertEqual(self._symbol_list_count("ETF_CORE_SYMBOLS"), 100)
        self.assertEqual(self._symbol_list_count("KOSPI200_SYMBOLS"), 200)
        self.assertEqual(self._symbol_list_count("KOSDAQ100_SYMBOLS"), 100)
        self.assertIn('const CRYPTO_SYMBOLS = ["BTC-USD", "ETH-USD"];', self.source)
        self.assertIn('id="symbolPickerSummary"', html)
        self.assertIn('id="symbolPickerAddFiltered"', html)
        self.assertIn('id="symbolPickerRemoveFiltered"', html)
        self.assertIn("data-symbol-select-all", self.source)
        self.assertIn("data-symbol-scope", self.source)
        self.assertIn('value="kr_kospi200"', html)
        self.assertIn('value="kr_kosdaq100"', html)
        self.assertIn('maxlength="12000"', html)
        self.assertIn("삼성전자 (005930 · KOSPI 200)", self.source)
        self.assertIn("에코프로비엠 (247540 · KOSDAQ 100)", self.source)
        self.assertIn("Microsoft Corporation", self.source)
        self.assertIn("iShares MSCI ACWI ETF", self.source)

    def test_symbol_picker_selection_does_not_filter_by_price_availability(self):
        match = re.search(
            r"async function addFilteredSymbolsToBacktestUniverse\(\) \{(?P<body>.*?)\n\}",
            self.source,
            re.S,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("setBacktestUniverse([...selectedBacktestUniverse(), ...symbols])", body)
        self.assertNotIn("resolveBacktestUniverseAvailability", body)
        self.assertIn("state.lastUniverseResolution = null", self.source)

    def test_quant_universe_resolve_hydrates_missing_prices_before_execution(self):
        self.assertIn("hydrate_missing", self.source)
        self.assertIn("가격 이력 ${_fmtNumber(hydratedCount)}개 자동 보강", self.source)
        self.assertIn("누락된 가격 이력은 자동 보강하는 중입니다", self.source)
        self.assertIn("numberInputValue(els.backtestLongWindow", self.source)

    def test_strategy_editor_is_code_only_not_universe_editor(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("function strategyCodeOnlyPayload", self.source)
        self.assertIn("delete clean.universe", self.source)
        self.assertIn("delete clean.benchmark", self.source)
        self.assertNotIn("universe: request.tickers.length", self.source)
        self.assertIn("API.quantStrategyGenerate", self.source)
        self.assertIn("function runQuantStrategyGenerate", self.source)
        self.assertIn("function renderStrategyPromptReview", self.source)
        self.assertIn("API.quantUniverseResolve", self.source)
        self.assertIn("function resolveBacktestUniverseAvailability", self.source)
        self.assertIn('id="strategyPromptInput"', html)
        self.assertIn('id="quantStrategyGenerate"', html)
        self.assertIn('id="strategyPromptReviewSurface"', html)
        self.assertIn("Strategy definition JSON only", html)
        self.assertIn("Python 코드가 아니며", html)

    def test_dashboard_tab_switching_is_url_addressable_and_verified(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="homeDashboardTabs"', html)
        self.assertIn('data-dashboard-tab="quant"', html)
        self.assertIn('data-dashboard-tab="ai-portfolio"', html)
        self.assertIn("function dashboardTabFromLocation", self.source)
        self.assertIn("hashchange", self.source)
        self.assertIn('"#quant-lab"', self.source)
        self.assertIn('"#ai-portfolio"', self.source)
        self.assertIn("setDashboardTab(nextTab", self.source)

    def test_ai_portfolio_static_ui_contract(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        css = STYLES_CSS.read_text(encoding="utf-8")
        for marker in [
            'id="aiPortfolioTab"',
            'id="aiPortfolioSurface"',
            'id="aiPortfolioInvestmentTypes"',
            'id="aiPortfolioUniverse"',
            'id="aiPortfolioCustomUniverse"',
            'id="aiPortfolioUniverseStatus"',
            'id="aiPortfolioPolicyForm"',
            'id="aiPortfolioGenerate"',
            'id="aiPortfolioRecommendationSurface"',
            'id="aiPortfolioPerformanceSurface"',
            'id="aiPortfolioComplianceSurface"',
            'id="aiPortfolioRebalanceSurface"',
            'id="aiPortfolioReportsSurface"',
            'id="aiPortfolioHistorySurface"',
            'id="aiPortfolioApproveRebalance"',
            'id="aiPortfolioRejectRebalance"',
            'id="aiPortfolioDeferRebalance"',
        ]:
            self.assertIn(marker, html)
        for marker in [
            "API.aiPortfolioInvestmentTypes",
            "API.aiPortfolioUniverses",
            "API.aiPortfolioGenerate",
            "function syncAiPortfolioUniverseMode",
            "function loadAiPortfolio",
            "function runAiPortfolioGenerate",
            "function checkAiPortfolioRebalance",
            "function generateAiPortfolioReport",
            "state.aiPortfolioPolicy",
        ]:
            self.assertIn(marker, self.source)
        self.assertIn(".ai-portfolio-surface", css)
        self.assertIn('[data-dashboard-tab="ai-portfolio"]', css)

    def test_quant_lab_visual_flow_keeps_history_after_portfolio(self):
        css = STYLES_CSS.read_text(encoding="utf-8")
        expected_orders = {
            "asset-detail-card": "1",
            "feature-card": "2",
            "signal-card": "3",
            "strategy-governance-card": "4",
            "backtest-card": "5",
            "portfolio-card": "6",
            "quant-run-history-card": "7",
        }
        for class_name, order in expected_orders.items():
            pattern = rf'\.dashboard-surface-grid\[data-dashboard-tab="quant"\] \.{class_name} \{{(?P<body>.*?)\}}'
            match = re.search(pattern, css, re.S)
            self.assertIsNotNone(match, class_name)
            self.assertIn(f"order: {order};", match.group("body"))


if __name__ == "__main__":
    unittest.main()
