# Quant Lab Export Cleanup Preview Extension

> Date: 2026-05-05 KST
> Scope: product-depth extension after `QUANT_LAB_EXPORT_VERIFICATION_HISTORY_EXTENSION.md`
> Status: implemented and verified in the local environment

## Executive Summary

The Quant Lab compatibility contract remains complete. This run closed the next concrete export-operability gap: generated exports could be listed and verified, but cleanup was only available as an opt-in side effect of creating a new export. Operators now have a preview-first cleanup workflow for a saved run.

The new behavior is intentionally conservative:

```text
saved run exports -> cleanup preview -> explicit apply -> generated export directories only
```

Cleanup never touches source backtest artifacts, replay reports, strategy definitions, Qlib provider exports, or other runs.

## What Changed

### Cleanup Planning

Added a non-destructive backend planner:

- `preview_backtest_artifact_export_cleanup(...)`
- `GET /api/v1/quant/backtest/{run_id}/exports/cleanup-preview?keep_last_exports=N`

The response reports:

- selected run id
- policy id
- `keep_last_exports`
- total export directories
- kept export directories
- prune candidates
- rows and byte impact
- generated timestamp
- `cleanup_applied=false`

### Cleanup Application

Added an explicit apply path:

- `cleanup_backtest_artifact_exports(...)`
- `POST /api/v1/quant/backtest/{run_id}/exports/cleanup`

The apply path uses the same plan calculation, then deletes only generated export directories selected by the policy. The selected targets are resolved under:

```text
data/quant_lab/backtests/{run_id}/exports/
```

Path containment is enforced before deletion.

### UI Workflow

The Quant Lab export controls now include:

- export JSONL
- export CSV
- export Parquet
- retention selector
- export history
- cleanup preview
- verify latest export

The cleanup preview view shows:

- policy and keep-last value
- total exports
- prune count
- byte impact
- exports that would be pruned
- exports that would be kept

The apply action is only rendered from the preview result when there are prune candidates.

### Tests

Added coverage for both layers:

- pipeline-level preview/apply behavior
- API-level preview/apply behavior
- proof that preview is non-destructive
- proof that apply prunes the expected export directories

## Files Touched

- `pipelines/backtest/artifact_exports.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/api/routers/quant_lab.py`
- `app/web/app.js`
- `scripts/quant_lab_ui_smoke.py`
- `tests/test_quant_lab_api.py`
- `tests/test_quant_lab_pipeline.py`
- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
- `docs/QUANT_LAB_EXPORT_CLEANUP_PREVIEW_EXTENSION.md`

## API Contract

### Preview Cleanup

```http
GET /api/v1/quant/backtest/{run_id}/exports/cleanup-preview?keep_last_exports=3
```

Example response shape:

```json
{
  "status": "success",
  "run_id": "qlab_...",
  "policy": "keep_last_exports",
  "keep_last_exports": 3,
  "cleanup_applied": false,
  "export_count": 8,
  "kept_export_count": 3,
  "prune_export_count": 5,
  "total_bytes_to_prune": 284122,
  "total_bytes_pruned": 0,
  "kept_exports": [],
  "prune_exports": []
}
```

### Apply Cleanup

```http
POST /api/v1/quant/backtest/{run_id}/exports/cleanup
Content-Type: application/json

{"keep_last_exports": 3}
```

The apply response keeps the same shape but sets:

```json
{
  "cleanup_applied": true,
  "total_bytes_pruned": 284122
}
```

If `keep_last_exports` is missing, the route defaults to `5`. If it is `0`, cleanup is disabled and no files are deleted.

## Verification Record

Baseline before editing:

```powershell
python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q
```

Result:

```text
14 passed
```

Post-edit syntax gates:

```powershell
python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py
node --check app\web\app.js
```

Result: passed.

Targeted Quant Lab tests:

```powershell
python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q
```

Result:

```text
16 passed
```

Full suite:

```powershell
python -m pytest tests -q
```

Result:

```text
364 passed, 3 subtests passed
```

UI/static/preflight gates:

```powershell
python scripts\check_ui_contract.py
python -m core.preflight
python -m pytest tests/test_browser_acceptance_matrix.py tests/test_qlib_adapter_export.py tests/test_strategy_registry.py -q
```

Results:

- UI contract passed with zero missing markers.
- Preflight reported all critical dependencies operational.
- Targeted Browser/Qlib/strategy boundary tests: `8 passed`.

Production path:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
```

Result: automated validation passed.

Browser fallback smoke:

```powershell
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Browser Use IAB tool was available from tool discovery in this run"
```

Result:

- status: `passed`
- console errors: `0`
- screenshot: `reports/browser_ui/quant_lab_ui_smoke_1777939794.png`
- checked: `artifact export cleanup preview`

Browser Use IAB was not available from tool discovery in this run, so it remains recorded as blocked rather than passed.

## Safety Properties

- Preview is read-only.
- Apply is opt-in.
- Apply uses the same plan as preview.
- `keep_last_exports=0` disables cleanup.
- Cleanup is run-scoped.
- Cleanup deletes directories only under the selected run's `exports/` directory.
- Source artifacts such as `manifest.json`, `config.json`, `metrics.json`, `diagnostics.json`, curves, trades, signals, weights, and replay reports are not cleanup targets.

## Current Boundaries

Implemented and verified:

- Export generation.
- Export integrity metadata.
- Export retention during generation.
- Export history listing.
- Export verification.
- Export tamper detection.
- Export cleanup preview.
- Explicit export cleanup apply.
- UI controls for export/verify/history/cleanup.

Still intentionally outside scope:

- Qlib provider execution.
- Cross-run export storage dashboards.
- Offline export verification CLI.
- Signed export/package manifests.
- Strategy schema migration beyond `quant_strategy_v1`.
- Replay report side-by-side drilldown beyond current metric-delta tables.

## Practical Expansion Points

### 1. Cross-Run Export Storage Report

Add a report that scans all Quant Lab runs and summarizes generated export storage:

```text
GET /api/v1/quant/exports/storage
```

Recommended response fields:

- total runs
- runs with exports
- total export directories
- total bytes
- top 20 largest runs
- oldest export timestamp
- newest export timestamp
- stale export candidates by age

Acceptance checks:

- Report must not delete files.
- Report must tolerate missing or corrupt export manifests.
- Report must include enough paths for operator review but not require a running backtest.

### 2. Cross-Run Cleanup Preview

Only after the storage report is stable, add a cross-run preview:

```text
POST /api/v1/quant/exports/cleanup-preview
```

Recommended body:

```json
{
  "keep_last_exports_per_run": 5,
  "min_age_days": 7,
  "max_total_bytes": 1073741824
}
```

The apply route should remain separate and should require the preview id or exact candidate list from the preview response.

### 3. Offline Export Verifier

Add a CLI that verifies an export directory without starting FastAPI:

```powershell
python scripts\verify_quant_export.py data\quant_lab\backtests\{run_id}\exports\{export_id}
```

The CLI should:

- load `export_manifest.json`
- re-hash listed files
- compare SHA-256 and byte sizes
- emit JSON and human-readable output
- return non-zero on drift

This is useful when export packages are copied off the workstation.

### 4. Export Package Manifest

Add a package-level manifest that references all generated files plus the source artifact manifest:

```text
package_manifest.json
```

Recommended fields:

- package schema version
- source run id
- source artifact config hash
- source artifact code version
- export format
- export manifest hash
- generated file hashes
- generated by route or CLI
- created at

This can later support signed export packages.

### 5. Replay Report Drilldown

The replay report history table currently shows metric deltas. A useful next UI increment is a side-by-side replay report drilldown:

- selected report A
- selected report B
- original metrics
- replay metrics
- delta differences
- tolerance policy differences
- code version differences
- data snapshot differences

Keep this read-only. It should not recompute a backtest.

### 6. Browser Use IAB Re-Attach

When Browser Use IAB becomes available, rerun the same workflow through Browser Use rather than replacing the fallback smoke:

- Quant Lab tab
- feature preview
- signal matrix
- backtest
- replay comparison
- replay history
- export
- verify
- export history
- cleanup preview

The acceptance matrix should keep reporting Browser Use, Playwright fallback, and static UI contract separately.

## Final Assessment

The two source MD files were re-read after implementation. The original Fincept compatibility contract remains complete, and the practical future-improvement track now includes export cleanup preview/apply as a verified product-depth extension.

The next best work is not another broad compatibility pass. It is a narrow storage/auditability increment: cross-run export storage reporting, offline export verification, or replay report drilldown.
