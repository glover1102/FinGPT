# Quant Lab Automation 2 Final Expansion Report

> Date: 2026-05-05 03:11 KST
> Scope: final completion check for `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: deterministic Quant Lab compatibility complete; practical extension items from the two source MDs are implemented where they fit the current repo boundary.

## 1. Final State

The Quant Lab is now a FinGPT-native deterministic workflow, not a copied FinceptTerminal subsystem and not a parallel `pipelines/quant` stack.

Current verified flow:

```text
data/research_mart.db
  -> pipelines/factors
  -> pipelines/signals
  -> pipelines/backtest
  -> pipelines/portfolio
  -> data/quant_lab/backtests/{run_id}
  -> FastAPI /api/v1/quant/*
  -> app/web Quant Lab UI
```

The two requested MD files were re-read after implementation. The compatibility design remains complete, and the future-improvement analysis now has its concrete product-depth items closed except for intentionally separate future work: real Qlib provider execution, full long-running answer-quality review, and Browser Use IAB re-verification once the local IAB backend is available.

## 2. What Changed In This Run

### 2.1 Backtest Freshness Profile Contract

Problem found:

- The UI sent `freshness_profile` in Quant backtest requests.
- `QuantBacktestRequest` did not declare that field, so Pydantic ignored it.
- This meant `decision_review` and `historical_lab` could silently fall back to `research_default` for backtests.

Implemented:

- Added `freshness_profile` to `core/schemas/quant.py`.
- Added validator parity with `QuantFeaturePreviewRequest`.
- Added regression coverage proving `decision_review` makes Quant backtests strict/fail-closed when stale data violates policy.

Practical impact:

- Feature Preview, Signal Matrix, Backtest, artifact config, and replay now use the same freshness profile contract.
- Saved runs are more reproducible because the operator's profile intent is preserved in artifact config.

### 2.2 Qlib Data-Mart Export Boundary

Problem found:

- `POST /api/v1/quant/qlib/export` was a safe status/preview boundary only.
- The future-improvement track still called out data-mart-to-Qlib export as remaining explicit opt-in work.

Implemented:

- Added `pipelines/adapters/qlib_export.py`.
- Extended `pipelines/adapters/qlib_adapter.py`.
- Extended `POST /api/v1/quant/qlib/export` with `dry_run`.
- Added tests in `tests/test_qlib_adapter_export.py`.

Default behavior remains fail-safe:

```text
QUANT_LAB_QLIB_ENABLED=false
POST /api/v1/quant/qlib/export
  -> status=disabled
  -> export_written=false
  -> no filesystem writes
```

Explicit opt-in behavior:

```text
QUANT_LAB_QLIB_ENABLED=true
QLIB_PROVIDER_URI=<export-dir>
POST /api/v1/quant/qlib/export { dry_run: false, tickers: [...] }
  -> reads data/research_mart.db
  -> writes calendars/day.txt
  -> writes instruments/all.txt
  -> writes features/{ticker}.csv
  -> writes manifest.json
```

Important boundary:

- This is a data export seed, not Qlib strategy execution.
- If the Qlib Python package is missing, the response keeps that visible as `exported_dependency_missing`.
- App startup, legacy endpoints, and default Quant Lab workflows still do not depend on Qlib.

### 2.3 Strategy Governance UI

Problem found:

- Strategy registry, save, load, delete, and dry-run APIs existed.
- The Quant Lab UI still lacked a practical governance surface for operators.

Implemented:

- Added a `Strategy Governance` card to the Quant Lab.
- Added registry table with source, schema version, strategy version, execution policy, and feature list.
- Added JSON editor for strategy definitions.
- Added `New draft`, `Dry-run`, `Save`, and `Delete saved` actions.
- Loading a strategy synchronizes universe, benchmark, top N, portfolio method, max weight, freshness profile, and research-score setting into the existing backtest/portfolio controls.

Practical impact:

- Saved strategies are no longer invisible API-only artifacts.
- Operators can validate no-lookahead execution policy before saving.
- Strategy governance now belongs to the same UI acceptance surface as feature preview, signal generation, backtest, replay, portfolio, and run history.

## 3. Verification Evidence

Fresh verification from this run:

```powershell
python -m pytest tests/test_quant_lab_pipeline.py -q
# 6 passed

python -m pytest tests/test_qlib_adapter_export.py tests/test_quant_lab_api.py::test_qlib_export_preview_is_disabled_by_default -q
# 3 passed

python -m pytest tests/test_strategy_registry.py tests/test_quant_lab_api.py tests/test_qlib_adapter_export.py -q
# 10 passed

node --check app\web\app.js
# passed

python scripts\check_ui_contract.py
# passed, no missing markers

python -m pytest tests -q
# 357 passed, 3 subtests passed

python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered"
# passed, console_errors=0

python -m core.preflight
# all critical dependencies operational

powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
# automated validation passed
```

Browser evidence:

- Playwright fallback smoke passed on fresh local server `http://127.0.0.1:49383`.
- Screenshot: `reports/browser_ui/quant_lab_ui_smoke_1777918181.png`.
- Browser acceptance matrix: `reports/browser_acceptance_latest.json`.
- Browser Use IAB remains blocked by `No Codex IAB backends were discovered`; this is not counted as Browser Use success.

## 4. File Map

Core contract and backend:

- `core/schemas/quant.py`: backtest freshness profile schema.
- `app/api/routers/quant_lab.py`: Qlib export route passes `dry_run`; existing strategy routes remain the UI backend.
- `pipelines/adapters/qlib_adapter.py`: Qlib status/export boundary.
- `pipelines/adapters/qlib_export.py`: data-mart CSV provider seed export.

Frontend:

- `app/web/index.html`: Strategy Governance card.
- `app/web/app.js`: strategy registry fetch, editor, dry-run, save, delete, and control sync.
- `app/web/styles.css`: Strategy Governance layout and responsive behavior.

Verification:

- `tests/test_quant_lab_pipeline.py`: backtest profile regression.
- `tests/test_qlib_adapter_export.py`: opt-in export and disabled no-write behavior.
- `scripts/check_ui_contract.py`: strategy governance markers.
- `scripts/quant_lab_ui_smoke.py`: strategy dry-run browser fallback smoke.

Documentation:

- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`: updated completion log.
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`: updated future-improvement disposition.
- `docs/QUANT_LAB_AUTOMATION_2_FINAL_EXPANSION_REPORT.md`: this final expansion report.

## 5. Practical Operating Guide

### 5.1 Daily Quant Lab Smoke

Use this when checking local workstation readiness:

```powershell
python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py tests/test_strategy_registry.py tests/test_qlib_adapter_export.py -q
node --check app\web\app.js
python scripts\check_ui_contract.py
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered"
```

Acceptance:

- Tests pass.
- UI contract reports no missing markers.
- Playwright smoke reports `status=passed`.
- Console errors list is empty.
- Browser Use IAB may remain blocked, but that must stay explicitly labeled as blocked.

### 5.2 Qlib Export Dry Run

Default dry run:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:<port>/api/v1/quant/qlib/export `
  -ContentType application/json `
  -Body '{"tickers":["SPY","QQQ"],"start_date":"2024-01-01","dry_run":true}'
```

Expected when disabled:

```text
status=disabled
export_written=false
startup_required=false
```

### 5.3 Qlib Export Write

Only use this when the operator explicitly wants a file export:

```powershell
$env:QUANT_LAB_QLIB_ENABLED="true"
$env:QLIB_PROVIDER_URI="data/quant_lab/qlib_exports/manual_spy_qqq"

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:<port>/api/v1/quant/qlib/export `
  -ContentType application/json `
  -Body '{"tickers":["SPY","QQQ"],"start_date":"2024-01-01","dry_run":false}'
```

Acceptance:

- Response has `export_written=true`.
- `manifest.json` exists.
- `calendars/day.txt` exists.
- `instruments/all.txt` exists.
- At least one `features/{ticker}.csv` exists.
- If Qlib is not installed, status may be `exported_dependency_missing`; do not treat that as provider execution success.

### 5.4 Strategy Governance Workflow

Operator workflow:

1. Open Quant Lab.
2. Click `Strategy Governance`.
3. Load an existing strategy or click `New draft`.
4. Review/edit JSON.
5. Click `Dry-run`.
6. Only save if dry-run shows `lookahead safe` and no missing features.
7. Run Feature Preview, Signal Matrix, Backtest, Replay Compare, and Portfolio Optimize with the synchronized controls.

Acceptance:

- `execution.trade_at` must be `next_bar_close`.
- Missing factors must be visible.
- Saved custom strategies must have `schema_version`, `strategy_version`, `created_at`, `updated_at`, and `source`.

## 6. Remaining Expansion Points

These are intentionally not blockers for the two requested MD files.

### 6.1 Real Qlib Provider Execution

Current state:

- Data export exists.
- Runtime execution does not.

Concrete next slice:

1. Add `pipelines/adapters/qlib_runner.py`.
2. Require `QUANT_LAB_QLIB_ENABLED=true`.
3. Require dependency status `available`.
4. Load only an exported provider URI.
5. Run a single fake/minimal strategy fixture first.
6. Return provider metrics under a separate response branch, for example `provider_results.qlib`.
7. Never mix Qlib metrics into deterministic FinGPT metrics.

Acceptance commands:

```powershell
python -m pytest tests/test_qlib_adapter_export.py tests/test_qlib_adapter_runner.py -q
python -m pytest tests/test_quant_lab_api.py -q
```

### 6.2 Strategy Migration Helpers

Current state:

- New saved strategies default to `quant_strategy_v1`.
- Dry-run validates execution policy and feature availability.

Concrete next slice:

1. Add `pipelines/strategies/migrations.py`.
2. Add migration from `quant_strategy_v1` to `quant_strategy_v2` only after a real schema change exists.
3. Add UI badge for `migration_available`.
4. Keep default registry immutable; migrate user strategies only.

Acceptance:

```powershell
python -m pytest tests/test_strategy_registry.py tests/test_strategy_migrations.py -q
python scripts\quant_lab_ui_smoke.py --timeout-s 180
```

### 6.3 Full Research Output Quality Gate

Current state:

- Deterministic Quant Lab gates pass.
- `quality_review.py --suite all` remains long-running and should stay separate from hourly automation.

Concrete next slice:

```powershell
python quality_review.py --suite all --case-offset 0 --case-limit 5 --output reports/quality_review_shard_000.json
python quality_review.py --suite all --resume-from reports/quality_review_shard_000.json --output reports/quality_review_full.json
```

Acceptance:

- No orphaned Python processes.
- Partial output is written after each case.
- Quant Lab compatibility status is not downgraded by research-answer quality experiments unless a shared contract breaks.

### 6.4 Browser Use IAB Re-Attachment

Current state:

- Browser Use IAB is blocked by local backend discovery.
- Playwright fallback is passing.

Concrete next slice:

1. Retry IAB once the Codex desktop IAB backend is available.
2. Record IAB evidence separately in `reports/browser_acceptance_latest.json`.
3. Only then mark `explicit_browser_use_satisfied=true`.

Acceptance:

```powershell
python scripts\browser_acceptance_matrix.py `
  --browser-use-status passed `
  --playwright-status passed `
  --output reports\browser_acceptance_latest.json
```

## 7. Final Recommendation

Stop treating `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` as an open implementation backlog. It is complete for the current deterministic FinGPT Quant Lab boundary.

Future work should be handled as separate, narrow product-depth increments:

- Qlib provider execution.
- Strategy schema migration.
- Full research-output quality review.
- Browser Use IAB re-verification.

Do not merge these into compatibility completion status. That would make evidence reporting less precise and could cause fallback browser/static evidence to be mistaken for Browser Use IAB success.
