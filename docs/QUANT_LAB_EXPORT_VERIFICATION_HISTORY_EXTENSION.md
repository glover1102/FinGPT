# Quant Lab Export Verification And History Extension

> Date: 2026-05-05 08:15 KST
> Scope: practical extension after re-reading `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: implemented and verified in the local environment

## Executive Summary

The Quant Lab compatibility contract remains complete. This run closed the next concrete export-auditability gap after export integrity and retention: generated export files can now be listed and re-verified later without creating a new export or recomputing a backtest.

The implemented flow is:

```text
saved Quant Lab run
  -> generated export directory
  -> export_manifest.json with SHA-256 and byte sizes
  -> export history API/UI
  -> read-only verification API/UI
  -> per-file pass/fail result
```

This keeps source artifacts immutable for audit purposes. Verification reads the export manifest and exported files, hashes them again, and reports drift. It does not rewrite `manifest.json`, `config.json`, replay reports, curves, trades, signals, weights, or generated export files.

## What Changed

### Export History API

Files:

- `pipelines/backtest/artifact_exports.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/api/routers/quant_lab.py`

Added:

```http
GET /api/v1/quant/backtest/{run_id}/exports?limit=20
```

The endpoint lists generated export directories under:

```text
data/quant_lab/backtests/{run_id}/exports/
```

Each item includes:

- export status
- format
- generated time
- export root
- manifest path
- row counts
- total rows
- total bytes from integrity metadata
- whether integrity metadata is available
- file map
- retention metadata when present

It tolerates missing or decode-failed export manifests and marks those rows explicitly instead of crashing the history view.

### Export Verification API

Files:

- `pipelines/backtest/artifact_exports.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/api/routers/quant_lab.py`

Added:

```http
POST /api/v1/quant/backtest/{run_id}/export/verify
Content-Type: application/json

{
  "export_manifest_path": "data/quant_lab/backtests/.../exports/.../export_manifest.json"
}
```

If `export_manifest_path` is omitted, the latest export manifest for that run is verified.

Verification behavior:

- Reads `export_manifest.json`.
- Reads `integrity.files` from the manifest.
- Re-hashes every listed exported file with SHA-256.
- Re-checks file byte sizes.
- Returns `status=success` only when every listed file matches.
- Returns `status=partial` when any exported file is missing, tampered, or mismatched.
- Returns `status=failed` for decode-level manifest failures.
- Rejects manifest paths that escape the selected run's `exports/` directory.
- Rejects paths that do not point to `export_manifest.json`.

Example response fragment:

```json
{
  "status": "success",
  "run_id": "momentum_ranking_...",
  "files_checked": 3,
  "files_passed": 3,
  "files_failed": 0,
  "files": {
    "metrics": {
      "status": "passed",
      "expected_sha256": "64_hex_chars",
      "actual_sha256": "64_hex_chars",
      "expected_size_bytes": 1024,
      "actual_size_bytes": 1024
    }
  }
}
```

### Tamper Detection

File:

- `tests/test_quant_lab_api.py`

The test now verifies the happy path and a drift path:

1. Create a Quant Lab backtest.
2. Export JSONL and CSV.
3. List export history.
4. Verify the latest export successfully.
5. Verify the JSONL manifest successfully.
6. Modify the exported JSONL file.
7. Verify the same manifest again and expect `status=partial` plus `files_failed=1`.

This proves the checksum is not only written, but actually usable for detecting post-generation mutation.

### UI Surface

Files:

- `app/web/app.js`
- `app/web/styles.css`
- `scripts/quant_lab_ui_smoke.py`

The Quant Lab export controls now include:

- `export JSONL`
- `export CSV`
- `export Parquet`
- retention selector:
  - `No cleanup`
  - `Keep last 3`
  - `Keep last 5`
  - `Keep last 10`
- `export history`
- `verify latest export`

The export summary now redraws these controls after an export completes. This was fixed after the first browser smoke found that the result screen showed checksum rows but did not preserve the next-step verify/history actions.

The UI can now render:

- export history table
- generated time
- format
- export status
- rows
- bytes
- integrity availability
- manifest path
- per-manifest verify button
- verification status summary
- expected versus actual SHA-256 prefixes
- expected versus actual byte sizes
- mismatch warnings

## Verification Record

Baseline before editing:

```powershell
python -m pytest tests\test_quant_lab_api.py tests\test_quant_lab_pipeline.py -q
node --check app\web\app.js
python scripts\check_ui_contract.py
```

Results:

- Targeted Quant Lab/API baseline: `14 passed`.
- JS syntax gate: passed.
- UI contract: passed.

Post-implementation targeted verification:

```powershell
python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py
node --check app\web\app.js
python -m pytest tests\test_quant_lab_api.py -q
python -m pytest tests\test_quant_lab_pipeline.py tests\test_qlib_adapter_export.py tests\test_browser_acceptance_matrix.py -q
```

Results:

- Python compile gate: passed.
- JS syntax gate: passed.
- Targeted API tests: `6 passed`.
- Targeted Quant Lab pipeline/Qlib/browser-acceptance tests: `11 passed`.

Full verification:

```powershell
python scripts\check_ui_contract.py
python -m pytest tests -q
python -m core.preflight
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "Browser Use IAB was not requested in this run; Playwright fallback used for automation acceptance"
```

Results:

- UI contract: passed with zero missing markers.
- Full suite: `362 passed, 3 subtests passed`.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- First Playwright fallback smoke found a real UI issue: export result screens did not include the new verify/history action row.
- After fixing the UI, Playwright fallback smoke passed with zero console errors.
- Browser fallback screenshot: `reports/browser_ui/quant_lab_ui_smoke_1777936479.png`.
- Browser fallback checks included `artifact export verify` and `artifact export history`.

## Operational Guidance

### Verify Latest Export

Use this when the operator wants to confirm the most recent generated export for a run:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/quant/backtest/<run_id>/export/verify" `
  -ContentType "application/json" `
  -Body '{}'
```

### Verify A Specific Manifest

Use this when a user has a concrete export manifest path from history:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/quant/backtest/<run_id>/export/verify" `
  -ContentType "application/json" `
  -Body '{"export_manifest_path":"data/quant_lab/backtests/<run_id>/exports/<stamp>_csv/export_manifest.json"}'
```

### List Export History

Use this before cleanup or before attaching exports to a review package:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/v1/quant/backtest/<run_id>/exports?limit=20"
```

### Use Retention Carefully

Retention remains opt-in. Recommended defaults:

| Workflow | Suggested setting |
| --- | ---: |
| Manual review | `No cleanup` |
| Hourly smoke | `Keep last 3` |
| Daily package generation | `Keep last 5` |
| High-volume export loop | `Keep last 10` plus operator review |

Retention only prunes generated export directories for the selected run. It does not prune source artifacts or replay reports.

## Current Boundaries

Implemented and verified:

- JSONL/CSV export history listing.
- Optional Parquet export history listing when Parquet export is generated.
- Read-only export checksum verification.
- Latest-export verification.
- Specific-manifest verification.
- Path containment for verification requests.
- Tamper detection for modified exported files.
- UI retention selector.
- UI export history table.
- UI export verification table.
- Fallback browser smoke coverage for export verify/history.

Still intentionally not implemented:

- Qlib provider execution.
- Qlib strategy runs.
- Provider-specific metric comparison against deterministic FinGPT metrics.
- Strategy schema v2 migration without a real v2 contract.
- Browser Use IAB validation in this environment.
- Cross-run export retention policy.
- Deeper replay-report side-by-side drilldown.

## Practical Expansion Points

### 1. Export Cleanup Preview

Add a dry-run cleanup endpoint:

```http
POST /api/v1/quant/backtest/{run_id}/exports/cleanup/preview
```

Acceptance:

- Accepts `keep_last_exports`.
- Returns export directories that would be deleted.
- Includes generated time, format, total bytes, and manifest status.
- Does not delete anything.
- UI can show the preview before applying retention.

### 2. Cross-Run Export Storage Report

Add an operator report:

```http
GET /api/v1/quant/exports/storage
```

Acceptance:

- Scans all Quant Lab runs.
- Returns total generated export directories, total bytes, and largest runs.
- Flags missing or decode-failed manifests.
- Does not scan or hash large files unless `include_integrity=true`.

### 3. Replay Report Side-By-Side Drilldown

Extend the replay report history UI:

- Select two replay reports from one run.
- Compare metric deltas side by side.
- Group tolerance failures by metric.
- Show original/replay code versions and config hash equality.
- Do not recompute backtests for already-saved report comparison.

### 4. Export Package Manifest

Add a package-level manifest for review bundles:

```text
review_package/
  exports/
  replay_reports/
  package_manifest.json
```

Acceptance:

- References source run id and artifact config hash.
- Includes export manifest checksums.
- Includes replay report summary.
- Can be verified without a running API server.

### 5. Qlib Provider Execution As A Separate Track

Keep Qlib execution outside this artifact-export track.

Acceptance before implementation:

- `QUANT_LAB_QLIB_ENABLED=true` is explicit.
- Qlib runtime is installed and version-reported.
- Input comes from data-mart export.
- Provider metrics are labeled provider-specific.
- Deterministic FinGPT metrics remain the baseline for comparison.
- The provider path has isolated tests and is not required for default startup.

## Final Assessment

The two source MDs now match the current implementation more tightly:

- The original compatibility contract remains complete.
- The concrete future-improvement items that fit the deterministic Quant Lab boundary have been implemented through small verified slices.
- Generated exports are now auditable after creation.
- Existing exports can be listed, verified, and tamper-detected without recomputation.
- The UI exposes retention, history, and verification as normal operator actions.
- Remaining work should proceed as narrow product-depth tracks, not as a reopening of the completed compatibility plan.
