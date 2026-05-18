from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


NODE_MODULE_CONTRACT = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = process.argv[1];
const context = { window: {}, console };
for (const rel of [
  "app/web/modules/market-ui.js",
  "app/web/modules/macro-ui.js",
  "app/web/modules/forecast-ui.js",
  "app/web/modules/quant-ui.js",
  "app/web/modules/ai-portfolio-ui.js",
]) {
  vm.runInNewContext(fs.readFileSync(path.join(root, rel), "utf8"), context, { filename: rel });
}

function assertNoRawHtml(html, raw) {
  assert.equal(html.includes(raw), false, `${raw} was not escaped`);
}

const marketTape = context.window.FinGPTMarketUi.marketTape({
  advisory_only: true,
  raw_market_meta: { generated_at: "2026-05-14T00:00:00Z" },
  freshness_summary: { status: "ok", decision_usable_count: 1, item_count: 2, warning: "<stale>" },
  heatmap_summary: { status: "partial", universe_size: 2, decision_usable_count: 1, latest_as_of: "2026-05-14" },
  market_tape: [
    {
      symbol: "QQQ",
      asset_class: "equity",
      label: "<script>alert(1)</script>",
      price: 430.12,
      return_1d: -0.5,
      return_1m: 2.25,
      freshness_status: "ok",
      source: "fixture",
      is_decision_usable: true,
      as_of: "2026-05-14T00:00:00Z",
    },
    {
      symbol: "SPY",
      asset_class: "equity",
      label: "S&P 500",
      price: 510.33,
      return_1d: 1.1,
      return_1m: 3.5,
      freshness_status: "ok",
      source: "fixture",
      is_decision_usable: true,
      as_of: "2026-05-14T00:00:00Z",
    },
  ],
}, { freshnessLabels: { ok: "fresh" } });
assert.match(marketTape.meta, /1\/2 usable/);
assert.match(marketTape.html, /SPY/);
assert.match(marketTape.html, /QQQ/);
assertNoRawHtml(marketTape.html, "<script>alert(1)</script>");
assert.match(marketTape.html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);

const marketSignals = context.window.FinGPTMarketUi.marketSignals({
  signals: [{
    status: "partial",
    signal_id: "credit",
    title: "Credit stress",
    summary: "spread widening",
    evidence: ["HYG down", "LQD down"],
    interpretation: "risk-off",
  }],
});
assert.match(marketSignals, /market-signal-item/);
assert.match(marketSignals, /credit/);

const macroProvider = context.window.FinGPTMacroUi.providerHealth({
  status: "partial",
  generated_at: "2026-05-14T00:00:00Z",
  warnings: ["<provider warning>"],
  scheduler: { enabled: true },
  stale_series: [{ series_id: "DCOILWTICO" }],
  providers: [{
    provider: "fred",
    enabled: true,
    configured: true,
    latest_status: "ok",
    latest_rows: 1234,
    latest_error: "<none>",
  }],
});
assert.match(macroProvider, /Provider/);
assert.match(macroProvider, /fred/);
assert.match(macroProvider, /DCOILWTICO/);
assertNoRawHtml(macroProvider, "<provider warning>");

const forecastJobs = context.window.FinGPTForecastUi.jobs([
  {
    job_id: "job-1",
    job_status: "queued",
    ticker: "SPY",
    model_name: "ridge",
    progress_stage: "queued",
    progress_message: "waiting",
    can_cancel: true,
    result_summary: { experiment_id: "exp-1" },
  },
  {
    job_id: "job-2",
    job_status: "failed",
    ticker: "QQQ",
    model_name: "lasso",
    progress_stage: "failed",
    progress_message: "error",
    can_retry: true,
    result_summary: { status: "failed" },
  },
]);
assert.match(forecastJobs, /data-action="forecast-job-cancel"/);
assert.match(forecastJobs, /data-action="forecast-job-retry"/);
assert.match(forecastJobs, /data-action="forecast-experiment-detail"/);

const quantReport = context.window.FinGPTQuantUi.exportStorageReport({
  status: "success",
  run_count: 2,
  runs_with_exports: 1,
  export_directory_count: 3,
  total_bytes: 2048,
  stale_export_count: 1,
  format_counts: { csv: 1 },
  manifest_status_counts: { valid: 1 },
  artifact_root: "F:/very/long/path/to/quant/artifacts/that/should/be/compacted/for/display",
  top_runs: [{
    run_id: "run-1",
    export_count: 1,
    total_bytes: 2048,
    total_rows: 30,
    formats: { csv: 1 },
    newest_export_generated_at: "2026-05-14T00:00:00Z",
  }],
  stale_exports: [{
    run_id: "run-1",
    format: "csv",
    age_days: 45,
    total_bytes: 2048,
    status: "valid",
    manifest_path: "F:/artifacts/run-1/manifest.json",
  }],
});
assert.match(quantReport, /cross-run export storage report/);
assert.match(quantReport, /data-testid="quant-run-open"/);
assert.match(quantReport, /data-action="cross-run-cleanup-preview"/);

const aiMeta = context.window.FinGPTAiPortfolioUi.dashboardMeta({
  generated_at: "2026-05-14T00:00:00Z",
  cache: { hit: true, age_seconds: 2, ttl_seconds: 15 },
  debug_timing: { total: 0.25, holdings: 0.12, coverage: 0.05 },
});
assert.match(aiMeta, /ai-portfolio-dashboard-meta/);
assert.match(aiMeta, /cache hit/);
const aiOps = context.window.FinGPTAiPortfolioUi.operationList([{
  operation_type: "hydrate",
  created_at: "2026-05-14T00:00:00Z",
  operation_id: "op-1",
  status: "completed",
  request_id: "req-1",
  price_result: { created: 3 },
}]);
assert.match(aiOps, /ai-operation-item/);
assert.match(aiOps, /hydrate/);

console.log(JSON.stringify({
  ok: true,
  modules: Object.keys(context.window).filter((key) => key.startsWith("FinGPT")).sort(),
}));
"""


def test_domain_ui_modules_render_fixture_payloads() -> None:
    result = subprocess.run(
        ["node", "-e", textwrap.dedent(NODE_MODULE_CONTRACT), str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "modules": [
            "FinGPTAiPortfolioUi",
            "FinGPTForecastUi",
            "FinGPTMacroUi",
            "FinGPTMarketUi",
            "FinGPTQuantUi",
        ],
    }
