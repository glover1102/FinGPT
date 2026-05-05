# Quant Lab Replay Tolerance And Strategy Migration Extension

> Run status: implemented and verified on 2026-05-05 04:14 KST.

## Purpose

This document records the practical extension completed after re-reading:

- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`

The compatibility contract was already complete. This run focused on the next auditability layer: making replay comparisons persistable and tolerance-aware, and making strategy definitions migratable instead of becoming unversioned JSON blobs.

## What Changed

### 1. Replay Reports Are Now First-Class Artifacts

`POST /api/v1/quant/backtest/{run_id}/replay` now returns and can persist:

- `schema_version=quant_lab_replay_report_v1`
- `generated_at`
- `config_hash_match`
- original and replay config hashes
- original and replay code version
- original and replay metric payloads
- metric deltas
- tolerance policy
- tolerance pass/fail status
- tolerance failure rows
- replay diagnostics
- `report_path`

When `persist_report=true`, the report is written to:

```text
data/quant_lab/backtests/{run_id}/replay_report.json
```

`GET /api/v1/quant/backtest/{run_id}/bundle` now includes `replay_report`, so operators can inspect replay evidence from one bundle response.

### 2. Replay Tolerances Are Explicit

Replay comparison now supports a request body such as:

```json
{
  "persist_report": true,
  "tolerances": {
    "default_abs": 1e-8,
    "total_return": 1e-8,
    "sharpe": 1e-8,
    "max_drawdown": 1e-8
  }
}
```

The response includes:

- `tolerance_passed=true|false`
- `tolerance_failures=[...]`
- per-metric absolute tolerance values

This is intentionally simple and deterministic. It does not hide differences behind relative tolerances or statistical explanations.

### 3. Freshness Profile Replay Bug Fixed

During fresh-server verification, `historical_lab` replay initially returned `status=partial` even though metric deltas were zero. The cause was real:

- Runtime profile resolution treated `historical_lab` as max 30 market-calendar lag days.
- The artifact config persisted the Pydantic default `max_market_calendar_lag_days=3`.
- Replay loaded that saved config and accidentally overrode the profile default.
- Metrics still matched, but `config_hash_match=false`.

The artifact config now stores the resolved freshness policy:

- `freshness_profile`
- `require_fresh_prices`
- `max_market_calendar_lag_days`

Fresh server verification then confirmed:

- `replay_status=success`
- `config_hash_match=true`
- `tolerance_passed=true`

### 4. Strategy Schema Migration Helpers Added

Strategy storage now has a migration helper:

```python
migrate_strategy(strategy, source=None, touch=False)
```

It normalizes legacy or missing schema versions to:

```text
schema_version=quant_strategy_v1
strategy_version=1
source=user|default
```

It also records `migration_history` and rejects unsupported future schemas such as `quant_strategy_v99`.

The API now exposes:

```text
POST /api/v1/quant/strategy/migrate
```

This lets UI or automation callers preflight old saved strategies without saving them.

### 5. UI Evidence Is More Operational

The Quant Lab UI replay comparison now shows:

- replay tolerance pass/check
- metric tolerance values
- tolerance failure warning rows
- replay report path

The strategy dry-run result now shows:

- schema version
- strategy version
- migration history

## Key Files Changed

- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/api/routers/quant_lab.py`
- `pipelines/strategies/storage.py`
- `pipelines/strategies/registry.py`
- `app/web/app.js`
- `tests/test_quant_lab_pipeline.py`
- `tests/test_quant_lab_api.py`
- `tests/test_strategy_registry.py`
- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`

## Verification Record

### Targeted Code Gates

```powershell
python -m py_compile pipelines\orchestration\quant_lab_pipeline.py pipelines\strategies\storage.py pipelines\strategies\registry.py app\api\routers\quant_lab.py
node --check app\web\app.js
python -m pytest tests\test_quant_lab_pipeline.py tests\test_quant_lab_api.py tests\test_strategy_registry.py -q
```

Result:

```text
19 passed
```

### Full Test Gate

```powershell
python -m pytest tests -q
```

Result:

```text
362 passed, 3 subtests passed
```

### UI Contract

```powershell
python scripts\check_ui_contract.py
```

Result:

```text
status=passed
missing_markers=[]
```

### Browser Fallback Smoke

```powershell
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Browser Use IAB tool was available from tool discovery in this run"
```

Result:

```text
status=passed
console_errors=[]
screenshot=reports\browser_ui\quant_lab_ui_smoke_1777921954.png
```

Browser Use IAB was not counted as passed. The available browser evidence for this run is Playwright fallback plus static UI contract.

### Production Path

```powershell
python -m core.preflight
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
```

Result:

```text
preflight: all critical dependencies operational
verify_production_path.ps1: automated_passed=true
```

### Fresh Server Runtime Smoke

Fresh server:

```text
http://127.0.0.1:61211
```

Verified:

- `/api/v1/health`
- `/api/v1/quant/config`
- `POST /api/v1/quant/backtest`
- `POST /api/v1/quant/backtest/{run_id}/replay`
- `GET /api/v1/quant/backtest/{run_id}/bundle`
- `POST /api/v1/quant/strategy/migrate`
- `POST /api/v1/quant/strategy/dry-run`
- `POST /api/v1/quant/qlib/export`

Observed:

```json
{
  "health": "ok",
  "backtest_status": "success",
  "replay_status": "success",
  "replay_config_hash_match": true,
  "replay_tolerance_passed": true,
  "replay_report_schema": "quant_lab_replay_report_v1",
  "strategy_migration_status": "success",
  "strategy_schema": "quant_strategy_v1",
  "strategy_dry_run_status": "success",
  "qlib_export_status": "disabled"
}
```

## Practical Operator Workflow

1. Run or open a Quant Lab backtest.
2. Replay it through the UI or API.
3. Inspect `tolerance_passed`.
4. If false, inspect `tolerance_failures` before trusting changed metrics.
5. Load the bundle and keep `replay_report` with the artifact evidence.
6. Dry-run or migrate strategy JSON before saving.
7. Treat Qlib export/provider status as optional integration evidence only.

## Improvement Points

### Replay Report History

Current behavior stores the latest replay report per artifact. The next step is to store multiple replay reports:

```text
replay_reports/{timestamp}_{config_hash}.json
```

This would let users compare replay drift across code versions.

### Replay Diff UI

The UI now shows one comparison. A practical next UI increment is:

- report selector
- metric diff table across multiple replays
- code version badge
- data snapshot badge
- failed tolerance filter

### Strategy Migration V2

Do not invent `quant_strategy_v2` yet. Add it only when the strategy schema actually changes. When it does, add:

- versioned migration functions
- migration dry-run endpoint output
- save-time migration summary
- tests for v1 to v2 and unsupported v3

### Qlib Execution Boundary

Qlib provider execution remains intentionally unimplemented. The next safe milestone would be a disabled-by-default comparison command that:

- consumes exported data-mart CSV only
- runs only when `QUANT_LAB_QLIB_ENABLED=true`
- labels results as provider-specific
- never changes deterministic FinGPT metrics
- fails closed if Qlib dependency or provider URI is missing

### Larger Run Export

For larger universes, JSON artifact bundles will become heavy. The practical path is:

- keep manifest/config/diagnostics in JSON
- add optional Parquet or CSV exports for curves/trades/signals/weights
- keep schema version and file hashes in manifest
- avoid changing default small-run JSON behavior

## Current Limitations

- Browser Use IAB was not available from tool discovery in this run.
- Qlib provider execution is not implemented by design.
- Replay history stores the latest replay report only.
- Strategy migration currently supports normalization to `quant_strategy_v1`; future schema versions need explicit migration code when they exist.

## Recommended Next Increment

Build replay-report history and diff UI before adding any new quant model complexity. It is low-risk, improves auditability, and uses the artifact boundary already proven by this run.
