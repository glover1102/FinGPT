# Quant Lab Replay History And Artifact Export Extension

> Date: 2026-05-05 05:09 KST
> Scope: product-depth continuation for `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: implemented and verified in the current local environment

## Executive Summary

The Quant Lab compatibility contract was already complete. This run closed the next practical auditability gap: replay evidence is no longer latest-only, and saved runs can now be exported without recomputing or depending on live data state.

The useful boundary is:

```text
saved artifact bundle -> replay report history -> CSV/JSONL export -> external review or archival
```

This keeps reproducibility tied to the stored artifact bundle and avoids turning Qlib, Parquet, or another provider into a hidden runtime dependency.

## What Changed

### Replay Report History

Before this run, `POST /api/v1/quant/backtest/{run_id}/replay` persisted only `replay_report.json`, so each replay replaced the previous report.

Now each persisted replay writes:

- `data/quant_lab/backtests/{run_id}/replay_report.json`
- `data/quant_lab/backtests/{run_id}/replay_reports/{timestamp}_{status}.json`

The latest pointer remains stable for existing bundle consumers, while timestamped reports preserve replay history for audit review.

New API:

```text
GET /api/v1/quant/backtest/{run_id}/replay-reports
```

Response shape:

```json
{
  "status": "success",
  "run_id": "qlab_...",
  "count": 2,
  "latest": {
    "status": "success",
    "config_hash_match": true,
    "tolerance_passed": true
  },
  "items": []
}
```

### Artifact Bundle Export

New API:

```text
POST /api/v1/quant/backtest/{run_id}/export
```

Request:

```json
{"format": "jsonl"}
```

Supported formats:

- `jsonl`: one portable `artifact_bundle.jsonl` with section/index/payload records.
- `csv`: one CSV per exportable section, with nested fields flattened where feasible.

Exported sections:

- `manifest`
- `config`
- `metrics`
- `diagnostics`
- `equity_curve`
- `drawdown_curve`
- `trades`
- `signals`
- `weights`
- `replay_report`

Exports are written under:

```text
data/quant_lab/backtests/{run_id}/exports/{timestamp}_{format}/
```

### UI Workflow

The Quant Lab UI now exposes:

- replay history from Backtest results
- replay history from Replay Comparison
- replay report count buttons in Run History
- JSONL export from Backtest, Replay Comparison, and Run History
- CSV export from Backtest and Replay Comparison

The committed Playwright fallback smoke clicks the new replay-history and JSONL-export paths.

## Files Changed

- `app/api/routers/quant_lab.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `pipelines/backtest/artifact_exports.py`
- `app/web/app.js`
- `app/web/index.html`
- `scripts/quant_lab_ui_smoke.py`
- `tests/test_quant_lab_api.py`
- `tests/test_quant_lab_pipeline.py`
- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`

## Verification Record

Fresh verification from this run:

```powershell
python -m pytest tests\test_quant_lab_pipeline.py tests\test_quant_lab_api.py tests\test_qlib_adapter_export.py -q
# 16 passed

python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py
# passed

node --check app\web\app.js
# passed

python -m pytest tests -q
# 362 passed, 3 subtests passed

python scripts\check_ui_contract.py
# status: passed, missing_markers: []

python -m core.preflight
# all critical dependencies operational

powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
# automated_passed: true

python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Browser Use IAB tool was available from tool discovery in this run"
# status: passed, console_errors: []
```

Browser evidence:

- Playwright fallback screenshot: `reports/browser_ui/quant_lab_ui_smoke_1777925371.png`
- Browser Use IAB: blocked in this environment and recorded separately in the browser acceptance matrix.

## Operational Guidance

Use replay history when:

- metrics changed after a code or data update
- a saved run needs audit evidence across multiple replay attempts
- tolerance policy changed and old report evidence must remain inspectable

Use JSONL export when:

- a complete artifact bundle needs to be moved to an evaluator, notebook, or external archival step
- preserving nested payloads matters more than spreadsheet convenience

Use CSV export when:

- metrics, trades, signals, or curve rows need quick spreadsheet review
- a downstream tool expects flat tabular sections

Do not use these exports as proof of live provider freshness. They are artifact-backed outputs from a saved run.

## Practical Next Extensions

1. Replay diff drilldown UI

Add a side-by-side report detail view for two selected replay reports. Show metric deltas, tolerance failures, config hash, code version, data snapshot, and warning changes.

Acceptance:

```powershell
python -m pytest tests\test_quant_lab_api.py::test_replay_report_history_diff_endpoint -q
python scripts\quant_lab_ui_smoke.py --timeout-s 180
```

2. Export retention policy

Add retention metadata and optional cleanup for old `exports/` and `replay_reports/` folders. Keep defaults non-destructive and report what would be deleted before any removal.

Acceptance:

```powershell
python -m pytest tests\test_quant_lab_pipeline.py::test_artifact_export_retention_dry_run -q
```

3. Optional Parquet export

Add Parquet only behind dependency detection. If `pyarrow` is unavailable, return `dependency_missing` rather than failing app startup or blocking CSV/JSONL.

Acceptance:

```powershell
python -m pytest tests\test_quant_lab_api.py::test_parquet_export_dependency_missing_is_non_blocking -q
```

4. Strategy schema v2

Do not invent a v2 schema just to satisfy migration machinery. Define v2 only when there is a real new field contract, such as portfolio sleeves, multi-signal ensemble rules, or benchmark-relative constraints.

Acceptance:

```powershell
python -m pytest tests\test_strategy_registry.py::test_strategy_v2_migration_preserves_v1_execution_policy -q
```

5. Qlib provider execution

Keep this separate from default Quant Lab. Only implement if `QUANT_LAB_QLIB_ENABLED=true`, Qlib is installed, and acceptance includes provider-specific metric comparison against the deterministic engine.

Acceptance:

```powershell
$env:QUANT_LAB_QLIB_ENABLED='true'
python -m pytest tests\test_qlib_adapter_execution.py -q
```

## Current Limitation

Qlib provider execution remains intentionally unimplemented in this run. The verified Qlib surface is disabled-by-default status plus data-mart export. Browser Use IAB also remains blocked by tool availability; Playwright fallback evidence is valid as fallback evidence only.
