# Quant Lab Product-Depth Extension Plan

> Date: 2026-05-05 KST
> Scope: final re-analysis and practical continuation plan after completing `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: compatibility contract complete; first product-depth extension slice implemented and verified

## Final Summary

The Quant Lab is no longer just compatible with the original design contract. It now has a deeper operator surface around freshness enforcement, attribution, research provenance, portfolio risk, and optional provider boundaries.

The completed architecture remains:

```text
data_mart -> factors -> signals -> backtest -> artifacts -> portfolio -> UI
```

The important boundary decisions still hold:

- `data/research_mart.db` is the canonical structured data source.
- Qdrant remains document evidence storage only.
- LLM output can confirm or label a thesis, but cannot calculate metrics, weights, or executions.
- Backtest signals execute on a later bar, not the same close that generated the signal.
- Qlib remains disabled by default and outside app startup.

## What Changed In This Product-Depth Run

### 1. Strict Freshness Mode

Implemented surfaces:

- `core/schemas/quant.py`
- `pipelines/backtest/validation.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/web/index.html`
- `app/web/app.js`
- `tests/test_quant_schema_contract.py`
- `tests/test_quant_lab_pipeline.py`

Behavior:

- Default behavior stays warning-first for local research.
- `require_fresh_prices=true` turns daily-price freshness into an explicit gate.
- `max_market_calendar_lag_days` lets the caller tighten the policy.
- Feature/signal preview returns `partial` when strict freshness is violated but still shows diagnostics.
- Quant backtest returns `failed` when strict freshness is violated, because a strict requested backtest should not generate decision-grade metrics from stale/missing prices.

Operational acceptance:

```powershell
python -m pytest tests/test_quant_schema_contract.py tests/test_quant_lab_pipeline.py -q
```

### 2. Attribution And Provenance UI

Implemented surfaces:

- `core/schemas/quant.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/web/app.js`
- `app/web/index.html`
- `scripts/check_ui_contract.py`

Behavior:

- Quant backtest responses now include `weights`.
- The UI renders rebalance attribution from returned weights immediately after the run.
- Feature, signal, and backtest panels render the freshness policy and per-asset freshness table.
- Signal Matrix can render research-score provenance when the Research score toggle is enabled.

Acceptance signals:

- The UI contract now checks the strict freshness toggle, research score toggle, portfolio benchmark, and covariance controls.
- Fallback browser smoke clicked the new controls and produced no console errors.

### 3. Portfolio Risk Depth

Implemented surfaces:

- `pipelines/portfolio/optimizer.py`
- `app/api/routers/portfolio.py`
- `core/schemas/portfolio.py`
- `app/web/index.html`
- `app/web/app.js`
- `tests/test_portfolio_optimizer.py`

Behavior:

- New request fields:
  - `benchmark`
  - `covariance_method`
  - `shrinkage_alpha`
- Supported covariance methods:
  - `sample`
  - `diagonal_shrinkage`
- New benchmark-relative outputs:
  - benchmark annual return
  - active annual return
  - tracking error
  - information ratio
  - beta to benchmark
  - benchmark sample count
- UI now renders covariance method, shrinkage alpha, benchmark-relative metrics, risk contribution bars, and correlation matrix.

Operational acceptance:

```powershell
python -m pytest tests/test_portfolio_optimizer.py -q
```

### 4. Qlib Export Boundary

Implemented surfaces:

- `pipelines/adapters/qlib_adapter.py`
- `app/api/routers/quant_lab.py`
- `tests/test_quant_lab_api.py`

Behavior:

- `GET /api/v1/quant/qlib/status` remains disabled by default.
- `POST /api/v1/quant/qlib/export` reports a safe export boundary.
- When Qlib is disabled, the route returns `disabled` and `export_ready=false`.
- When Qlib is enabled but missing, it returns `dependency_missing`.
- When Qlib is available, it reports `dry_run_only` until a separate explicit export implementation is accepted.

This intentionally does not make Qlib a startup dependency and does not replace the deterministic FinGPT engine.

## Verification Matrix

Commands and observed results from the run:

```powershell
python -m pytest tests/test_quant_schema_contract.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py tests/test_portfolio_optimizer.py -q
# 22 passed

python -m py_compile core\schemas\quant.py core\schemas\portfolio.py pipelines\backtest\validation.py pipelines\orchestration\quant_lab_pipeline.py pipelines\portfolio\optimizer.py pipelines\adapters\qlib_adapter.py app\api\routers\quant_lab.py app\api\routers\portfolio.py scripts\check_ui_contract.py
# passed

node --check app\web\app.js
# passed

python scripts\check_ui_contract.py
# passed, zero missing markers

python -m pytest tests/test_backtest_engine.py tests/test_api_router_split.py tests/test_api_routing_contract.py tests/test_ui_routing_contract.py tests/test_data_mart_api.py tests/test_quality_review.py tests/test_browser_acceptance_matrix.py -q
# 28 passed

python -m pytest tests -q
# 353 passed, 3 subtests passed

python -m core.preflight
# all critical dependencies operational

powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
# automated validation passed
```

Fresh server smoke on `http://127.0.0.1:8136` verified:

- `/api/v1/health`: `ok`
- `/api/v1/quant/qlib/status`: `disabled`
- `/api/v1/quant/qlib/export`: `disabled`
- `/api/v1/quant/features/preview`: `success`
- strict `/api/v1/quant/features/preview`: `partial` with `require_fresh_prices=true`
- `/api/v1/quant/signals/generate`: `success`
- `/api/v1/quant/backtest`: `success`
- `/api/v1/quant/backtest/{run_id}/bundle`: reopened with weights
- `/api/v1/portfolio/optimize`: `success`, `covariance_method=diagonal_shrinkage`, `covariance_shrinkage_used=true`

Browser evidence:

- Browser Use IAB: blocked by `No Codex IAB backends were discovered`
- Playwright fallback: passed
- Screenshot: `reports/browser_ui/automation_2_quant_lab_product_depth_58719.png`
- Console errors: `0`
- Evidence matrix: `reports/browser_acceptance_latest.json`

## Current Remaining Limitations

These are not blockers for the completed compatibility contract:

- Browser Use IAB still depends on the local Codex IAB backend becoming available.
- Playwright fallback is useful browser evidence, but it must remain labeled as fallback.
- Qlib provider export/execution is still intentionally dry-run/disabled unless explicitly enabled and implemented.
- `quality_review.py --suite all` remains a slower research-output quality gate and should not be mixed with deterministic Quant Lab compatibility status.
- The Quant Lab UI is now richer, but `app/web/app.js` is large enough that future UI work should start extracting tested Quant Lab modules.

## Practical Next Expansion Points

### Extension A: Committed Playwright Regression

Why:

- The current fallback browser smoke was run as an automation script, not as a committed repeatable test.

Implementation:

- Add `tests/test_quant_lab_ui_playwright.py` or `scripts/quant_lab_ui_smoke.py`.
- Start a fresh server on a random port.
- Click Quant Lab.
- Verify visible controls:
  - `#backtestRequireFresh`
  - `#backtestUseResearchScore`
  - `#portfolioBenchmark`
  - `#portfolioCovarianceMethod`
  - `#portfolioShrinkageAlpha`
- Run Feature Preview, Signal Matrix, Backtest, Portfolio Optimize.
- Assert zero console errors.
- Save a screenshot under `reports/browser_ui/`.

Done when:

- The test is deterministic enough for local CI.
- The browser acceptance matrix can ingest its screenshot path automatically.

### Extension B: Artifact Compare And Replay UI

Why:

- Manifest replay exists at the backend helper level, but users cannot compare current versus replayed metrics from the UI.

Implementation:

- Add `POST /api/v1/quant/backtest/{run_id}/replay`.
- Return:
  - original metrics
  - replay metrics
  - metric deltas
  - config hash match
  - current code version
  - original code version
- Add a Run History button: `replay`.
- Render a compact comparison table.

Done when:

- Replay reports stable metrics for unchanged data.
- The UI shows when a metric changed because data mart history changed.

### Extension C: Strict Freshness Profiles

Why:

- `require_fresh_prices` is now a caller flag. Product workflows may need named policies.

Implementation:

- Add profiles:
  - `research_default`: warning-first, max lag 3 market days
  - `decision_review`: strict, max lag 1 market day
  - `historical_lab`: warning-first, no strict fail
- Add `freshness_profile` to Quant requests.
- Resolve profile into policy fields on the backend.
- Keep explicit request fields as overrides.

Done when:

- UI users can select a profile without knowing calendar-lag internals.
- API diagnostics still show the resolved policy explicitly.

### Extension D: Qlib Data-Mart Export

Why:

- The safe Qlib boundary exists, but no provider-format export is written.

Implementation only after explicit opt-in:

- Require `QUANT_LAB_QLIB_ENABLED=true`.
- Add `pipelines/adapters/qlib_export.py`.
- Export data mart daily prices to a temporary provider directory.
- Do not mutate canonical data mart state.
- Add fake-provider tests that do not require real Qlib.
- Return export manifest paths, date ranges, row counts, and skipped tickers.

Done when:

- Disabled mode still returns `disabled`.
- Missing dependency still returns `dependency_missing`.
- Enabled dry-run reports exactly what would export.
- Enabled export writes only to an explicit temp/export directory.

### Extension E: Strategy Governance UI

Why:

- Strategy dry-run exists, but users still need a visible lifecycle workflow.

Implementation:

- Add a Strategy Registry panel in Quant Lab.
- Support:
  - list defaults
  - load strategy
  - dry-run current strategy
  - save strategy
  - delete user strategy
- Render validation results before save.
- Keep same-bar close strategies blocked.

Done when:

- A user can load, validate, and save a strategy without editing JSON manually.
- Saved strategies remain compatible with `POST /api/v1/quant/strategy/dry-run`.

## Recommended Execution Order

1. Commit or checkpoint the current product-depth slice.
2. Add the committed Playwright regression, because it protects the new UI controls.
3. Add artifact replay UI, because reproducibility is the strongest next auditability gain.
4. Add named freshness profiles, because strict freshness is now implemented but still low-level.
5. Add Qlib export only if there is an explicit provider-integration request.

## Decision

The two original MD files are complete as implementation contracts. The next useful work is not another compatibility pass. It is a sequence of narrow, verifiable product-depth increments with explicit browser evidence, artifact replay, freshness profiles, and optional provider exports behind flags.
