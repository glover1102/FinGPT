# Quant Lab Export Integrity And Retention Extension

> Date: 2026-05-05 07:08 KST
> Scope: practical extension after re-reading `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: implemented and verified in the local environment

## Executive Summary

The Quant Lab compatibility contract remains complete. This run closed the next concrete product-depth gap after optional Parquet export: generated export files now carry integrity metadata, and export accumulation can be bounded through an explicit opt-in retention policy.

The implementation keeps the same audit boundary:

```text
data/research_mart.db
  -> deterministic Quant Lab run
  -> saved source artifacts
  -> generated export set
  -> export manifest with SHA-256, byte sizes, and optional retention result
```

Exports are still derived from saved artifacts. The export layer does not recompute backtests, does not replace `data/research_mart.db`, and does not change Qlib provider execution status.

## What Changed

### Export Integrity

File: `pipelines/backtest/artifact_exports.py`

Every successful JSONL, CSV, or Parquet export now returns and persists:

- `integrity.algorithm`: currently `sha256`.
- `integrity.files[name].sha256`: SHA-256 digest of the exported file.
- `integrity.files[name].size_bytes`: file size at export time.
- `integrity.files[name].path`: concrete path written on disk.

The same integrity block is written into `export_manifest.json` for the generated data files. The API response also includes the manifest file checksum after the manifest is written.

Example response fragment:

```json
{
  "format": "jsonl",
  "export_written": true,
  "integrity": {
    "algorithm": "sha256",
    "files": {
      "jsonl": {
        "path": "data/quant_lab/backtests/.../artifact_bundle.jsonl",
        "sha256": "64_hex_chars",
        "size_bytes": 12345
      },
      "manifest": {
        "path": "data/quant_lab/backtests/.../export_manifest.json",
        "sha256": "64_hex_chars",
        "size_bytes": 2048
      }
    }
  }
}
```

### Export Retention

Files:

- `pipelines/backtest/artifact_exports.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/api/routers/quant_lab.py`

`POST /api/v1/quant/backtest/{run_id}/export` now accepts an optional `keep_last_exports` field.

Request:

```http
POST /api/v1/quant/backtest/{run_id}/export
Content-Type: application/json

{
  "format": "csv",
  "keep_last_exports": 5
}
```

Behavior:

- Missing or non-positive `keep_last_exports` means retention is disabled.
- Positive `keep_last_exports` prunes older generated export directories for the same run.
- The current export directory is always preserved.
- Cleanup is scoped only to `data/quant_lab/backtests/{run_id}/exports/`.
- Source artifacts are never deleted by this policy.

Response fragment:

```json
{
  "retention": {
    "policy": "keep_last_exports",
    "keep_last_exports": 5,
    "retention_applied": true,
    "pruned_export_count": 2,
    "pruned_exports": [
      "data/quant_lab/backtests/.../exports/old_jsonl"
    ]
  }
}
```

### UI Surface

File: `app/web/app.js`

The Quant Lab artifact export summary now shows:

- export status
- format
- row counts
- export root
- manifest path
- SHA-256 checksum prefix per displayed exported file
- byte size per displayed exported file
- retention-pruning message when retention is applied
- optional Parquet dependency message when Parquet dependencies are missing

The UI still does not apply retention by default. That is intentional: deletion should remain explicit until there is a visible retention control or an operator-level cleanup job.

## Verification Record

Baseline before editing:

```powershell
python -m pytest tests\test_quant_lab_pipeline.py tests\test_quant_lab_api.py tests\test_qlib_adapter_export.py -q
node --check app\web\app.js
python scripts\check_ui_contract.py
```

Results:

- Targeted Quant Lab/API/Qlib export tests: `16 passed`.
- JS syntax gate: passed.
- UI contract: passed.

Post-implementation targeted verification:

```powershell
python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py
node --check app\web\app.js
python -m pytest tests\test_quant_lab_pipeline.py tests\test_quant_lab_api.py -q
```

Results:

- Compile gate: passed.
- JS syntax gate: passed.
- Targeted Quant Lab pipeline/API tests: `14 passed`.

Full verification:

```powershell
python scripts\check_ui_contract.py
python -m pytest tests -q
python -m core.preflight
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
python -m py_compile scripts\quant_lab_ui_smoke.py
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "Browser Use IAB was not requested in this run; Playwright fallback used for automation acceptance"
```

Results:

- UI contract: passed with zero missing markers.
- Full suite: `362 passed, 3 subtests passed`.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- Browser smoke compile gate: passed.
- Browser fallback smoke: passed with zero console errors.
- Browser fallback screenshot: `reports/browser_ui/quant_lab_ui_smoke_1777932649.png`.
- Browser fallback checks included `artifact export integrity`.

## Operational Guidance

### When To Use Integrity Metadata

Use the export checksums when:

- moving Quant Lab exports into another local analysis folder
- attaching exports to a review package
- comparing a generated CSV/JSONL/Parquet export to a later copy
- investigating whether an export changed after generation

The checksum proves file equality for the generated export file. It does not prove that the underlying market data is current. For data currency, use the run manifest, data snapshot, freshness diagnostics, and replay comparison.

### When To Use Retention

Use `keep_last_exports` when:

- repeated browser or automation runs generate many export directories for the same run
- the export is reproducible from source artifacts
- old generated transfer files are no longer needed

Do not use retention to clean source artifacts. Retention is intentionally limited to generated exports because source artifacts are part of audit history.

Recommended policies:

| Situation | Suggested `keep_last_exports` |
| --- | ---: |
| Manual one-off review | omit field |
| Hourly automation smoke | `3` |
| Daily review package generation | `5` |
| High-volume benchmark export loop | `10` plus a separate operator review |

### Safe Manual API Check

Generate a JSONL export without pruning:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/quant/backtest/<run_id>/export" `
  -ContentType "application/json" `
  -Body '{"format":"jsonl"}'
```

Generate a CSV export and keep only the latest three generated export sets for that run:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/quant/backtest/<run_id>/export" `
  -ContentType "application/json" `
  -Body '{"format":"csv","keep_last_exports":3}'
```

## Current Boundaries

Implemented and verified:

- JSONL export from saved artifacts.
- CSV export from saved artifacts.
- Optional dependency-detected Parquet export from saved artifacts.
- SHA-256 and byte-size integrity metadata.
- Explicit per-run generated-export retention.
- UI rendering for integrity and retention results.
- Full test, production-path, preflight, static UI, and fallback browser verification.

Still intentionally not implemented:

- Qlib provider execution.
- Qlib strategy runs.
- Provider-specific metric comparison against deterministic FinGPT metrics.
- Strategy schema v2 migration without a real v2 contract.
- Browser Use IAB validation in this environment.

## Practical Expansion Points

### 1. Export Integrity Verification Endpoint

Add a read-only endpoint:

```http
POST /api/v1/quant/backtest/{run_id}/export/verify
```

Suggested request:

```json
{
  "export_manifest_path": "data/quant_lab/backtests/.../exports/.../export_manifest.json"
}
```

Acceptance:

- Re-hashes files listed in the export manifest.
- Returns `status=success` when every checksum matches.
- Returns `status=partial` with per-file mismatches when any exported file changed.
- Never rewrites export files.
- Has tests for one valid export and one tampered file.

### 2. Export History API

Add:

```http
GET /api/v1/quant/backtest/{run_id}/exports
```

Acceptance:

- Lists export directories by generated time.
- Includes format, manifest path, total rows, total bytes, and checksum availability.
- Flags incomplete or decode-failed export manifests.
- Lets the UI show export history without generating a new export.

### 3. UI Retention Control

Add a small retention selector near the export buttons:

- `No cleanup`
- `Keep last 3`
- `Keep last 5`
- `Keep last 10`

Acceptance:

- Default remains `No cleanup`.
- The selected value is sent as `keep_last_exports`.
- The UI renders the retention result after export.
- Browser fallback smoke covers one retention-enabled export.

### 4. Replay Report Side-By-Side Drilldown

Extend replay report history beyond the compact table.

Acceptance:

- Select any two replay reports for a run.
- Show metric deltas side by side.
- Group tolerance failures by metric.
- Show original/replay code versions and config hash equality.
- Do not recompute backtests just to compare already-saved replay reports.

### 5. Qlib Provider Execution Only As A Separate Gate

Keep Qlib execution out of this export-integrity track.

Acceptance before implementation:

- `QUANT_LAB_QLIB_ENABLED=true` is explicit.
- Qlib runtime is installed and verified.
- Data input comes from data-mart export.
- Provider metrics are labeled provider-specific.
- Deterministic FinGPT metrics remain the baseline, not the fallback.

## Final Assessment

The two source MDs now match the implementation state more tightly:

- The compatibility contract is complete.
- The concrete future-improvement items that fit the current deterministic Quant Lab boundary have been implemented.
- Export files are now auditable after generation.
- Export accumulation can be controlled without touching source artifacts.
- Remaining work should be split into small product-depth tracks rather than reopening the original compatibility plan.
