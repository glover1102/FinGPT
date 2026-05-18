# Quant Lab Parquet Artifact Export Extension

> Date: 2026-05-05 06:08 KST
> Scope: final practical extension after re-reading `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: implemented and verified in the local environment

## Executive Summary

The Quant Lab compatibility contract remains complete. This run closed the remaining practical large-run export gap by adding optional Parquet export to the existing saved-artifact export path.

The implementation deliberately keeps the same ownership boundary:

```text
data/research_mart.db -> deterministic Quant Lab run -> saved artifact bundle -> JSONL/CSV/Parquet export
```

Parquet is not a new source of truth, not a market-data cache, and not a Qlib provider runtime. It is an optional export format generated from already-saved run artifacts.

## What Changed

### Artifact Export Backend

File: `pipelines/backtest/artifact_exports.py`

- Added `parquet` to supported export formats.
- Writes one Parquet file per artifact section when dependencies are available.
- Preserves existing JSONL and CSV behavior.
- Adds `supported_formats`, `export_written`, and optional dependency metadata to export responses and export manifests.
- Detects `pandas` plus `pyarrow` or `fastparquet` before writing.
- Returns `status=dependency_missing` with `export_written=false` if Parquet dependencies are unavailable.

Supported request:

```http
POST /api/v1/quant/backtest/{run_id}/export
Content-Type: application/json

{"format": "parquet"}
```

Successful response shape:

```json
{
  "status": "success",
  "run_id": "qlab_...",
  "format": "parquet",
  "export_written": true,
  "export_root": "data/quant_lab/backtests/.../exports/..._parquet",
  "files": {
    "metrics": ".../metrics.parquet",
    "trades": ".../trades.parquet"
  },
  "dependency": {
    "available": true,
    "engine": "pyarrow"
  }
}
```

Missing optional dependency response shape:

```json
{
  "status": "dependency_missing",
  "format": "parquet",
  "export_written": false,
  "dependency": {
    "available": false,
    "message": "Parquet export requires pandas plus pyarrow or fastparquet."
  }
}
```

### UI Workflow

File: `app/web/app.js`

Parquet export actions now appear in:

- Backtest diagnostics artifact actions.
- Replay Comparison actions.
- Replay Report History actions.
- Quant Run History export actions.

The UI also renders optional dependency status instead of hiding it behind a generic request failure.

### Regression Coverage

Files:

- `tests/test_quant_lab_pipeline.py`
- `tests/test_quant_lab_api.py`
- `scripts/quant_lab_ui_smoke.py`

Coverage added:

- Pipeline-level artifact export can request Parquet.
- API-level `/export` accepts `format=parquet`.
- Invalid formats still return HTTP 400.
- Browser fallback smoke clicks the Parquet export action and observes the export result surface.

## Verification Record

Fresh verification from this run:

```powershell
python -m py_compile pipelines\backtest\artifact_exports.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py
node --check app\web\app.js
python -m pytest tests\test_quant_lab_pipeline.py tests\test_quant_lab_api.py -q
python -m pytest tests\test_quant_lab_pipeline.py tests\test_quant_lab_api.py tests\test_qlib_adapter_export.py -q
python scripts\check_ui_contract.py
python -m core.preflight
python -m pytest tests -q
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Browser Use IAB tool was available from tool discovery in this run"
```

Results:

- Compile gate: passed.
- JS syntax gate: passed.
- Targeted Quant Lab/API tests: `14 passed`.
- Targeted Quant Lab/API/Qlib boundary tests: `16 passed`.
- UI contract: passed with zero missing markers.
- Preflight: all critical dependencies operational.
- Full suite: `362 passed, 3 subtests passed`.
- Production path: automated validation passed.
- Browser fallback smoke: passed with zero console errors.
- Browser screenshot: `reports/browser_ui/quant_lab_ui_smoke_1777928921.png`.
- Browser Use IAB: still blocked by environment/tooling; fallback evidence remains separately labeled.

## Operational Notes

Use JSONL when:

- You need a single dependency-free export bundle.
- You want easy line-by-line audit streaming.
- The consumer can parse nested JSON payloads.

Use CSV when:

- You need spreadsheet-friendly per-section files.
- Nested payloads can be flattened into JSON strings.
- Analysts want quick inspection without Python tooling.

Use Parquet when:

- The run has many trades, signals, or curve points.
- The consumer is pandas, DuckDB, Spark, Polars, or another columnar analytics tool.
- Optional Parquet dependencies are installed.

Do not use Parquet as:

- The canonical market-data store.
- A replacement for `data/research_mart.db`.
- A hidden Qlib provider cache.
- Evidence that Qlib provider execution works.

## Remaining Limitations

1. Qlib provider execution remains intentionally unimplemented.
2. Browser Use IAB remains unavailable in this environment; Playwright fallback smoke is not the same acceptance level.
3. Replay report history exists, but the UI does not yet provide a rich side-by-side drilldown across multiple historical replay reports.
4. Export retention is unmanaged; repeated exports can accumulate under each run's `exports/` directory.
5. Export files do not yet carry checksums beyond the export manifest and existing run config hash lineage.

## Concrete Next Extensions

### 1. Export Integrity Manifest

Add SHA-256 checksums and byte sizes for every exported file in `export_manifest.json`.

Acceptance:

- Each JSONL/CSV/Parquet export manifest includes `files[name].sha256` and `files[name].bytes`.
- A helper can re-hash files and fail on mismatch.
- Tests cover at least one modified-file mismatch.

### 2. Export Retention Policy

Add a cleanup helper for old export directories under a run.

Acceptance:

- Default policy keeps latest N exports per format.
- Dry-run mode reports what would be deleted.
- No cleanup touches source artifacts outside `exports/`.

### 3. Replay Report Drilldown UI

Turn replay report history from a compact table into a compare surface.

Acceptance:

- Selecting two replay reports shows metric deltas side by side.
- Tolerance failures are grouped by metric.
- Config hash and code lineage are visible above the table.

### 4. Qlib Provider Execution Gate

Only pursue this if `QUANT_LAB_QLIB_ENABLED=true`, Qlib runtime is installed, and the user explicitly asks for provider execution.

Acceptance:

- Qlib provider execution is isolated in an adapter.
- Startup still works without Qlib.
- Provider metrics are labeled provider-specific and compared against deterministic FinGPT metrics.
- Data input comes from data-mart export, not an independent hidden data source.

### 5. Strategy Schema V2 Only After A Real Contract Exists

Do not invent a v2 migration without a real schema change.

Acceptance:

- A v2 schema is documented first.
- v1-to-v2 migration has deterministic defaults.
- Unsupported future versions still fail explicitly.

## Final Assessment

After this run, the two source MDs are internally consistent with the current implementation state:

- The compatibility contract is complete.
- The future-improvement items that were concrete and safe for the current deterministic Quant Lab boundary have been implemented.
- The remaining work is deliberately narrower product-depth work: export integrity/retention, richer replay drilldown, and optional Qlib provider execution only under explicit enablement.

