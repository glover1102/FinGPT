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
    "quant lab tab": 'id="quantLabTab"',
    "ai portfolio tab": 'id="aiPortfolioTab"',
    "run history": 'id="historyList"',
    "market snapshot": 'id="homeMarketList"',
    "home news": 'id="homeNewsList"',
    "tradingview chart": 'id="tvOverviewWidget"',
    "intraday heatmap": 'id="homeHeatmap"',
    "intraday heatmap refresh": 'id="homeHeatmapRefresh"',
    "data health": 'id="homeDataHealth"',
    "asset detail": 'id="assetDetailSurface"',
    "asset detail range": 'id="assetDetailRange"',
    "asset detail start date": 'id="assetDetailStartDate"',
    "asset detail end date": 'id="assetDetailEndDate"',
    "asset detail view": 'id="assetDetailView"',
    "asset detail benchmark": 'id="assetDetailBenchmark"',
    "asset detail benchmark compare": 'id="assetDetailBenchmarkCompare"',
    "quant feature preview": 'id="quantFeatureSurface"',
    "quant signal matrix": 'id="quantSignalSurface"',
    "strategy governance": 'id="quantStrategySurface"',
    "strategy prompt": 'id="strategyPromptInput"',
    "strategy generate": 'id="quantStrategyGenerate"',
    "strategy editor": 'id="strategyDefinitionJson"',
    "strategy review": 'id="strategyPromptReviewSurface"',
    "strategy editor note": 'class="strategy-editor-note"',
    "strategy dry run": 'id="quantStrategyDryRun"',
    "backtest": 'id="backtestSurface"',
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
    "quant export storage report": 'id="quantExportStorageReport"',
    "quant cross-run cleanup preview": 'id="quantCrossRunCleanupPreview"',
    "portfolio optimizer": 'id="portfolioSurface"',
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
