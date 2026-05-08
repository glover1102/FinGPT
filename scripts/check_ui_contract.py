from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import server as api_server


REQUIRED_UI_MARKERS: dict[str, str] = {
    "analysis form": 'id="analysisForm"',
    "ticker input": 'id="ticker"',
    "question textarea": 'id="question"',
    "result view": 'id="resultView"',
    "home dashboard": 'id="emptyState"',
    "dashboard tabs": 'id="homeDashboardTabs"',
    "market dashboard tab": 'id="marketDashboardTab"',
    "market dashboard tab testid": 'data-testid="market-dashboard-tab"',
    "macro dashboard tab": 'id="macroDashboardTab"',
    "macro dashboard tab testid": 'data-testid="macro-dashboard-tab"',
    "quant lab tab": 'id="quantLabTab"',
    "quant lab tab testid": 'data-testid="quant-lab-tab"',
    "ai portfolio tab": 'id="aiPortfolioTab"',
    "ai portfolio tab testid": 'data-testid="ai-portfolio-tab"',
    "run history": 'id="historyList"',
    "market snapshot": 'id="homeMarketList"',
    "home news": 'id="homeNewsList"',
    "tradingview chart": 'id="tvOverviewWidget"',
    "intraday heatmap": 'id="homeHeatmap"',
    "intraday heatmap refresh": 'id="homeHeatmapRefresh"',
    "intraday heatmap refresh testid": 'data-testid="market-heatmap-refresh"',
    "data health": 'id="homeDataHealth"',
    "data health refresh": 'id="dataHealthRefresh"',
    "data health refresh testid": 'data-testid="data-health-refresh"',
    "macro surface": 'id="macroSurface"',
    "macro refresh": 'id="macroRefresh"',
    "macro refresh testid": 'data-testid="macro-refresh"',
    "macro brief generate": 'id="macroBriefGenerate"',
    "macro brief generate testid": 'data-testid="macro-brief-generate"',
    "macro report export": 'id="macroReportExport"',
    "macro report export testid": 'data-testid="macro-report-export"',
    "macro overview": 'id="macroOverviewSurface"',
    "macro indicators": 'id="macroIndicatorTable"',
    "macro chart surface": 'id="macroChartSurface"',
    "macro interest rates": 'id="macroInterestRatesSurface"',
    "macro inflation": 'id="macroInflationSurface"',
    "macro growth labor": 'id="macroGrowthLaborSurface"',
    "macro yield curve": 'id="macroYieldCurveSurface"',
    "macro liquidity credit": 'id="macroLiquidityCreditSurface"',
    "macro fx dollar": 'id="macroFxDollarSurface"',
    "macro commodities": 'id="macroCommoditiesSurface"',
    "macro regime": 'id="macroRegimeSurface"',
    "macro asset impact": 'id="macroAssetImpactSurface"',
    "macro portfolio hints": 'id="macroPortfolioHintsSurface"',
    "macro brief": 'id="macroBriefSurface"',
    "macro data quality": 'id="macroDataQualitySurface"',
    "asset detail": 'id="assetDetailSurface"',
    "asset detail range": 'id="assetDetailRange"',
    "asset detail start date": 'id="assetDetailStartDate"',
    "asset detail end date": 'id="assetDetailEndDate"',
    "asset detail view": 'id="assetDetailView"',
    "asset detail benchmark": 'id="assetDetailBenchmark"',
    "asset detail benchmark compare": 'id="assetDetailBenchmarkCompare"',
    "quant feature preview": 'id="quantFeatureSurface"',
    "quant feature preview action": 'id="quantFeatureRun"',
    "quant feature preview action testid": 'data-testid="quant-feature-run"',
    "quant signal matrix": 'id="quantSignalSurface"',
    "quant signal matrix action": 'id="quantSignalRun"',
    "quant signal matrix action testid": 'data-testid="quant-signal-run"',
    "strategy governance": 'id="quantStrategySurface"',
    "strategy refresh": 'id="quantStrategyRefresh"',
    "strategy refresh testid": 'data-testid="quant-strategy-refresh"',
    "strategy new draft": 'id="quantStrategyNewDraft"',
    "strategy new draft testid": 'data-testid="quant-strategy-new-draft"',
    "strategy prompt": 'id="strategyPromptInput"',
    "strategy generate": 'id="quantStrategyGenerate"',
    "strategy generate testid": 'data-testid="quant-strategy-generate"',
    "strategy editor": 'id="strategyDefinitionJson"',
    "strategy review": 'id="strategyPromptReviewSurface"',
    "strategy editor note": 'class="strategy-editor-note"',
    "strategy dry run": 'id="quantStrategyDryRun"',
    "strategy dry run testid": 'data-testid="quant-strategy-dry-run"',
    "strategy save": 'id="quantStrategySave"',
    "strategy save testid": 'data-testid="quant-strategy-save"',
    "strategy delete": 'id="quantStrategyDelete"',
    "strategy delete testid": 'data-testid="quant-strategy-delete"',
    "backtest": 'id="backtestSurface"',
    "backtest run": 'id="backtestRun"',
    "backtest run testid": 'data-testid="quant-backtest-run"',
    "backtest universe picker": 'id="backtestUniverseOpen"',
    "backtest universe chips": 'id="backtestUniverseChips"',
    "backtest strategy registry": 'id="backtestStrategyRegistry"',
    "backtest benchmark": 'id="backtestBenchmark"',
    "backtest benchmark compare": 'id="backtestBenchmarkCompare"',
    "symbol picker modal": 'id="symbolPickerModal"',
    "symbol picker summary": 'id="symbolPickerSummary"',
    "symbol picker add filtered": 'id="symbolPickerAddFiltered"',
    "symbol picker remove filtered": 'id="symbolPickerRemoveFiltered"',
    "freshness profile": 'id="backtestFreshnessProfile"',
    "strict freshness toggle": 'id="backtestRequireFresh"',
    "research score toggle": 'id="backtestUseResearchScore"',
    "quant run history": 'id="quantRunHistorySurface"',
    "quant run history refresh": 'id="quantRunHistoryRefresh"',
    "quant run history refresh testid": 'data-testid="quant-run-history-refresh"',
    "quant export storage report": 'id="quantExportStorageReport"',
    "quant export storage report testid": 'data-testid="quant-export-storage-report"',
    "quant cross-run cleanup preview": 'id="quantCrossRunCleanupPreview"',
    "quant cross-run cleanup preview testid": 'data-testid="quant-cross-run-cleanup-preview"',
    "portfolio optimizer": 'id="portfolioSurface"',
    "portfolio sync backtest": 'id="portfolioSyncBacktest"',
    "portfolio sync backtest testid": 'data-testid="portfolio-sync-backtest"',
    "portfolio optimize action": 'id="portfolioOptimize"',
    "portfolio optimize action testid": 'data-testid="portfolio-optimize"',
    "portfolio benchmark": 'id="portfolioBenchmark"',
    "portfolio covariance method": 'id="portfolioCovarianceMethod"',
    "ai portfolio surface": 'id="aiPortfolioSurface"',
    "ai portfolio investment types": 'id="aiPortfolioInvestmentTypes"',
    "ai portfolio universe preset": 'id="aiPortfolioUniverse"',
    "ai portfolio custom universe": 'id="aiPortfolioCustomUniverse"',
    "ai portfolio universe status": 'id="aiPortfolioUniverseStatus"',
    "ai portfolio ops": 'id="aiPortfolioOpsSurface"',
    "ai portfolio ops refresh": 'id="aiPortfolioOpsRefresh"',
    "ai portfolio operation hydrate": 'id="aiPortfolioHydrateData"',
    "ai portfolio operation retry": 'id="aiPortfolioRetryMissing"',
    "ai portfolio snapshot job": 'id="aiPortfolioSnapshotJob"',
    "ai portfolio policy list": 'id="aiPortfolioPolicyListSurface"',
    "ai portfolio recommendation diff": 'id="aiPortfolioRecommendationDiffSurface"',
    "ai portfolio operations history": 'id="aiPortfolioOperationsSurface"',
    "ai portfolio policy form": 'id="aiPortfolioPolicyForm"',
    "ai portfolio generate": 'id="aiPortfolioGenerate"',
    "ai portfolio recommendation": 'id="aiPortfolioRecommendationSurface"',
    "ai portfolio performance": 'id="aiPortfolioPerformanceSurface"',
    "ai portfolio compliance": 'id="aiPortfolioComplianceSurface"',
    "ai portfolio rebalance": 'id="aiPortfolioRebalanceSurface"',
    "ai portfolio reports": 'id="aiPortfolioReportsSurface"',
    "ai portfolio history": 'id="aiPortfolioHistorySurface"',
}


def run_check() -> dict[str, Any]:
    with TestClient(api_server.app) as client:
        ui_response = client.get("/ui/")
        health_response = client.get("/api/v1/health")

    html = ui_response.text
    missing = [name for name, marker in REQUIRED_UI_MARKERS.items() if marker not in html]
    passed = ui_response.status_code == 200 and health_response.status_code == 200 and not missing
    return {
        "status": "passed" if passed else "failed",
        "ui_status": ui_response.status_code,
        "health_status": health_response.status_code,
        "missing_markers": missing,
        "checked_markers": sorted(REQUIRED_UI_MARKERS),
        "html_bytes": len(html.encode("utf-8", errors="ignore")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the FinGPT UI/API contract without a browser.")
    parser.add_argument("--output", default="reports/ui_contract_latest.json")
    args = parser.parse_args()

    report = run_check()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
