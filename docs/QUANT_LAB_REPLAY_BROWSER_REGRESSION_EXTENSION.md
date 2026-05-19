# Quant Lab Replay, Browser Regression, And Freshness Profile Extension

> Date: 2026-05-05 KST
> Scope: final re-analysis and practical extension after `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: implemented and verified in the current workspace

## Executive Summary

The original Quant Lab compatibility contract is complete. This extension closes the highest-value remaining product-depth items that were still practical in the current repo:

1. Saved Quant Lab artifacts can be replayed and compared against their original metrics.
2. The UI exposes replay comparison directly from Backtest Workbench and Run History.
3. Freshness behavior now has named profiles instead of only low-level booleans.
4. A committed Playwright fallback smoke script now protects the product-depth UI controls.
5. Browser Use IAB evidence remains separate from Playwright fallback evidence.

The implementation keeps the same architecture:

```text
data_mart -> factors -> signals -> backtest -> artifacts -> portfolio -> UI
```

It does not add a parallel quant stack and it does not make Qlib a startup dependency.

## What Changed

### 1. Named Freshness Profiles

Added request-level `freshness_profile` support for Quant Lab feature, signal, and backtest workflows.

Profiles:

| Profile | Require fresh prices | Max market-day lag | Intended use |
| --- | ---: | ---: | --- |
| `research_default` | false | 3 | Local research and exploratory analysis. |
| `decision_review` | true | 1 | Current decision review where stale prices should fail closed. |
| `historical_lab` | false | 30 | Historical experiments where old end dates are expected. |

Implementation details:

- `core/schemas/quant.py` defines the profile contract.
- `pipelines/orchestration/quant_lab_pipeline.py` resolves profile defaults.
- Explicit request fields still override profile defaults.
- `pipelines/backtest/validation.py` records the resolved profile in `freshness_policy.profile`.
- `GET /api/v1/quant/config` exposes all profiles to the UI.

Operational behavior:

- If the caller sends only `freshness_profile=decision_review`, strict freshness is enabled.
- If the caller sends `freshness_profile=decision_review` and explicitly sends `require_fresh_prices=false`, the explicit override wins.
- The UI avoids sending an explicit false override unless the strict checkbox is turned on, so profile semantics remain useful for normal operation.

### 2. Artifact Replay Comparison API

Added:

```text
POST /api/v1/quant/backtest/{run_id}/replay
```

The endpoint:

- Loads the saved artifact manifest and config.
- Reconstructs a `QuantBacktestRequest` from stored config fields.
- Re-runs the deterministic backtest against the current data mart.
- Writes a new replay artifact bundle.
- Returns original metrics, replay metrics, metric deltas, config hash equality, and code lineage.

Response shape:

```json
{
  "status": "success",
  "run_id": "qlab_original",
  "replay_run_id": "qlab_replay",
  "config_hash_match": true,
  "original_config_hash": "...",
  "replay_config_hash": "...",
  "original_code_version": {"git_commit": "...", "git_dirty": true},
  "current_code_version": {"git_commit": "...", "git_dirty": true},
  "original_metrics": {},
  "replay_metrics": {},
  "metric_deltas": {"total_return": 0.0},
  "diagnostics": {
    "replay_status": "success",
    "lookahead_safe": true,
    "signal_shift_bars": 1,
    "warnings": []
  }
}
```

Why this matters:

- A saved backtest can now be audited after data mart updates.
- Operators can distinguish stable deterministic metrics from changed metrics caused by changed source data or code.
- Config hash matching gives a compact reproducibility signal without pretending the whole environment is immutable.

### 3. Replay Comparison UI

Added UI support in `app/web/app.js` and `app/web/index.html`:

- Freshness profile select control in the Backtest Workbench.
- `replay compare` action on the active backtest result.
- `compare` action for each Run History row.
- Replay comparison table with original, replay, and delta columns.
- Lineage block showing original/replay generated timestamps and code versions.

The UI deliberately keeps replay comparison inside the existing Quant Lab workflow instead of introducing a separate page. That keeps the operator path short:

```text
Run backtest -> inspect result -> replay compare -> check deltas -> reopen history if needed
```

### 4. Committed Playwright Fallback Smoke

Added:

```text
scripts/quant_lab_ui_smoke.py
```

The script:

- Starts a fresh local server on a free port when `--base-url` is omitted.
- Opens `/ui/` with Playwright Chromium.
- Clicks Quant Lab.
- Verifies the product-depth controls:
  - `#backtestFreshnessProfile`
  - `#backtestRequireFresh`
  - `#backtestUseResearchScore`
  - `#portfolioBenchmark`
  - `#portfolioCovarianceMethod`
  - `#portfolioShrinkageAlpha`
- Runs Feature Preview.
- Runs Signal Matrix.
- Runs Backtest.
- Runs Replay Compare.
- Runs Portfolio Optimize.
- Refreshes Run History and checks replay controls.
- Captures a screenshot under `reports/browser_ui/`.
- Updates `reports/browser_acceptance_latest.json`.

Run command:

```powershell
python scripts\quant_lab_ui_smoke.py `
  --timeout-s 180 `
  --browser-use-status blocked `
  --browser-use-error "No Codex IAB backends were discovered"
```

Important evidence rule:

- Browser Use IAB blocked is still blocked.
- Playwright fallback passed is useful browser evidence.
- Playwright fallback does not satisfy explicit Browser Use acceptance.
- The browser acceptance matrix records those levels separately.

### 5. Artifact Run ID Hardening

Updated `pipelines/backtest/artifacts.py` so generated run IDs include microsecond precision.

Reason:

- Immediate replay of a just-created artifact could previously produce the same run ID when it happened within the same second and the config hash matched.
- Microsecond timestamps make artifact overwrite during immediate replay much less likely while preserving the existing `qlab_{timestamp}_{template}_{hash}` shape.

## Verification Results

Baseline before editing:

```powershell
python -m pytest tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py tests/test_quant_schema_contract.py tests/test_portfolio_optimizer.py -q
# 22 passed

node --check app\web\app.js
# passed

python scripts\check_ui_contract.py
# passed
```

Targeted after editing:

```powershell
python -m pytest tests/test_quant_schema_contract.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py -q
# 16 passed

python -m py_compile core\schemas\quant.py pipelines\backtest\validation.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py scripts\check_ui_contract.py
# passed

node --check app\web\app.js
# passed

python scripts\check_ui_contract.py
# passed, zero missing markers
```

Browser fallback:

```powershell
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered"
# passed
```

Observed browser evidence:

- Screenshot: `reports\browser_ui\quant_lab_ui_smoke_1777914590.png`
- Console errors: `0`
- Checked controls/workflows:
  - Quant tab
  - Freshness profile
  - Strict freshness toggle
  - Research score toggle
  - Portfolio benchmark
  - Portfolio covariance method
  - Portfolio shrinkage alpha
  - Feature Preview
  - Signal Matrix
  - Backtest
  - Replay Comparison
  - Portfolio Optimize
  - Run History replay button

Full deterministic gate:

```powershell
python -m pytest tests -q
# 355 passed, 3 subtests passed

python -m core.preflight
# all critical dependencies operational

powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
# automated validation passed
```

Fresh server smoke:

```text
Base URL: http://127.0.0.1:8137
Health: ok
Config profiles: research_default, decision_review, historical_lab
Decision review strict: true
Feature status: success
Feature profile: decision_review
Backtest status: success
Replay status: success
Replay config hash match: true
Total return delta: 0.0
```

## File Map

Core contract:

- `core/schemas/quant.py`
- `pipelines/backtest/validation.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `pipelines/backtest/artifacts.py`

API:

- `app/api/routers/quant_lab.py`

UI:

- `app/web/index.html`
- `app/web/app.js`
- `scripts/check_ui_contract.py`

Browser regression:

- `scripts/quant_lab_ui_smoke.py`
- `scripts/browser_acceptance_matrix.py`

Tests:

- `tests/test_quant_schema_contract.py`
- `tests/test_quant_lab_pipeline.py`
- `tests/test_quant_lab_api.py`

Docs:

- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
- `docs/QUANT_LAB_REPLAY_BROWSER_REGRESSION_EXTENSION.md`

## Operator Runbook

### Fast Local Confidence

Use this after touching Quant Lab schemas, pipeline, or API:

```powershell
python -m pytest tests/test_quant_schema_contract.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py -q
node --check app\web\app.js
python scripts\check_ui_contract.py
```

### Browser Confidence

Use this after touching Quant Lab UI:

```powershell
python scripts\quant_lab_ui_smoke.py --timeout-s 180
```

If Browser Use IAB remains unavailable and the run is an automation report:

```powershell
python scripts\quant_lab_ui_smoke.py `
  --timeout-s 180 `
  --browser-use-status blocked `
  --browser-use-error "No Codex IAB backends were discovered"
```

### Fresh Server Replay Smoke

Use this to validate the new API surface:

```powershell
$base = "http://127.0.0.1:8137"
Invoke-RestMethod "$base/api/v1/quant/config"

$bt = Invoke-RestMethod `
  -Method Post `
  -Uri "$base/api/v1/quant/backtest" `
  -ContentType "application/json" `
  -Body (@{
    tickers = @("SPY", "QQQ", "TLT")
    benchmark = "SPY"
    template = "momentum_ranking"
    lookback = 21
    top_n = 2
    freshness_profile = "historical_lab"
  } | ConvertTo-Json -Depth 8)

Invoke-RestMethod -Method Post "$base/api/v1/quant/backtest/$($bt.run_id)/replay"
```

Acceptance:

- Backtest status is `success`.
- Replay status is `success`.
- `config_hash_match` is `true` for unchanged configs.
- Important metric deltas are zero or explainable by current data/code changes.

## Practical Improvement Points

### Improvement 1: Persist Replay Reports

Current state:

- Replay comparison is returned by API and rendered in UI.
- It is not saved as a first-class artifact.

Next implementation:

- Write `replay_comparison.json` under the replay artifact directory.
- Include original run id, replay run id, metric deltas, and lineage.
- Add `GET /api/v1/quant/backtest/{run_id}/replays`.

Acceptance:

```powershell
python -m pytest tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py -q
```

### Improvement 2: Add Tolerance Policies

Current state:

- Metric deltas are exact numeric differences.

Next implementation:

- Add tolerances per metric:
  - returns: `1e-8`
  - volatility: `1e-8`
  - Sharpe/Sortino: `1e-6`
  - turnover/exposure: `1e-8`
- Return `stable`, `changed`, or `missing` per metric.

Acceptance:

- Replay UI should show stable/changed status without forcing the user to interpret raw floating-point deltas.

### Improvement 3: Strategy Governance UI

Current state:

- Strategy dry-run and persistence exist.
- The UI still focuses on the Backtest Workbench rather than lifecycle management.

Next implementation:

- Add a Strategy Registry panel.
- List default and user strategies.
- Load strategy into current controls.
- Dry-run before saving.
- Block same-bar close strategies.
- Save user strategies only after validation passes.

Acceptance:

```powershell
python -m pytest tests/test_strategy_registry.py tests/test_quant_lab_api.py -q
python scripts\quant_lab_ui_smoke.py --timeout-s 180
```

### Improvement 4: Qlib Export Only Behind Explicit Opt-In

Current state:

- Qlib status and export preview are disabled by default.
- No data-mart provider export is written.

Next implementation, only if explicitly requested:

- Require `QUANT_LAB_QLIB_ENABLED=true`.
- Add `pipelines/adapters/qlib_export.py`.
- Export data mart daily prices into an explicit temporary provider directory.
- Return manifest paths, row counts, date ranges, skipped tickers, and provider status.
- Keep deterministic FinGPT backtest output separate from provider-specific Qlib output.

Acceptance:

- Disabled mode returns `disabled`.
- Missing dependency returns `dependency_missing`.
- Enabled dry-run returns planned export shape.
- Enabled export writes only to an explicit export directory.

### Improvement 5: Quality Review Sharding

Current state:

- `quality_review.py` is shardable from prior work.
- `--suite all` remains a long-running research-output quality gate.

Next implementation:

- Add a Quant Lab specific quality suite that runs only research-to-quant handoff cases.
- Keep it separate from deterministic Quant Lab compatibility.
- Record latency, partials, and model fallback reasons.

Acceptance:

```powershell
python quality_review.py --suite quant-smoke --case-limit 3 --output reports/quality_review_quant_smoke.json
```

## Expansion Roadmap

### Milestone A: Reproducibility

- Persist replay comparison artifacts.
- Add metric tolerance status.
- Add UI filter for changed metrics.
- Add run-to-run diff export as JSON.

### Milestone B: Operator Workflow

- Strategy Registry UI.
- Saved profile presets.
- Run History filters by strategy, profile, and status.
- One-click rerun with modified freshness profile.

### Milestone C: Provider Boundary

- Disabled-by-default Qlib data-mart export.
- Fake-provider tests.
- Provider-specific result labeling.
- No default Quant Lab dependency on Qlib.

### Milestone D: Browser Evidence

- Keep `scripts/quant_lab_ui_smoke.py` as the repeatable fallback.
- Retry Browser Use IAB only when local backend discovery works.
- Never conflate Browser Use IAB with Playwright fallback in automation reports.

## Final Decision

The two original MD files are complete as implementation contracts. This extension makes the completed Quant Lab more reproducible and easier to validate:

- named freshness profiles make data policy operational,
- replay comparison makes saved artifacts auditable,
- UI replay controls make the feature usable,
- Playwright smoke makes browser regression repeatable,
- and evidence boundaries remain honest when Browser Use IAB is blocked.

The next best increment is persisted replay reports plus metric tolerance policies, followed by Strategy Governance UI. Qlib export should remain behind explicit opt-in.
