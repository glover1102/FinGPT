# Quant Lab Offline Export Package Verification Extension

> Date: 2026-05-05 KST
> Scope: product-depth extension after `QUANT_LAB_EXPORT_STORAGE_REPORT_EXTENSION.md`
> Status: implemented and verified in the local environment

## Executive Summary

The Fincept-compatible Quant Lab contract remains complete. This run closed the next practical export-auditability gap: operators could verify generated exports through the API, but copied export directories did not yet have a portable manifest or offline verification command.

The new workflow is:

```text
saved Quant Lab run -> generate export -> package_manifest.json -> offline CLI verification -> copy/tamper audit
```

It does not run Qlib, recompute a backtest, require FastAPI, or mutate any artifact.

## What Changed

### Portable Package Manifest

New exports now include:

- `export_manifest.json`: existing API/export manifest.
- `package_manifest.json`: portable verification manifest.

The package manifest records:

- source run id
- source artifact manifest SHA-256 and size
- config hash
- code-version lineage
- export format
- relative file paths
- SHA-256 and byte size for each exported file
- row counts
- optional dependency status
- retention policy result

### Offline Verifier

Added:

- `verify_export_package(...)`
- `scripts/verify_quant_export.py`

Usage:

```powershell
python scripts\verify_quant_export.py data\quant_lab\backtests\{run_id}\exports\{export_id}
python scripts\verify_quant_export.py --json data\quant_lab\backtests\{run_id}\exports\{export_id}
```

The verifier accepts:

- an export directory
- `package_manifest.json`
- legacy `export_manifest.json`

Package manifests use relative paths, so a copied export folder can be verified on another location. Legacy `export_manifest.json` verification still works, but reports a fallback warning because older manifests stored workstation-specific absolute paths.

## Files Touched

- `pipelines/backtest/artifact_exports.py`
- `scripts/verify_quant_export.py`
- `tests/test_quant_lab_pipeline.py`
- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
- `docs/QUANT_LAB_OFFLINE_EXPORT_PACKAGE_VERIFICATION_EXTENSION.md`

## Verification Record

Baseline:

```powershell
python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q
# 17 passed

node --check app\web\app.js
# passed

python scripts\check_ui_contract.py
# passed
```

Implementation gates:

```powershell
python -m py_compile pipelines\backtest\artifact_exports.py scripts\verify_quant_export.py
# passed

python -m pytest tests/test_quant_lab_pipeline.py::test_export_package_manifest_verifies_after_copy_and_detects_tamper -q
# 1 passed

python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q
# 18 passed

python -m pytest tests/test_browser_acceptance_matrix.py tests/test_qlib_adapter_export.py tests/test_strategy_registry.py -q
# 8 passed
```

Full/runtime gates:

```powershell
python -m pytest tests -q
# 366 passed, 3 subtests passed

python -m core.preflight
# all critical dependencies operational

powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
# automated validation passed

python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "Browser Use IAB was not requested in this offline export verification run; Playwright fallback used for continuity"
# passed, console_errors=0
```

Browser fallback screenshot:

- `reports/browser_ui/quant_lab_ui_smoke_1777946908.png`

## Operator Guide

### Verify Latest Export Directory

```powershell
python scripts\verify_quant_export.py data\quant_lab\backtests\qlab_run_id\exports\20260505T000000000000Z_jsonl
```

Success criteria:

- `status: success`
- `files_failed: 0`
- no failure rows

### Save Machine-Readable Verification

```powershell
python scripts\verify_quant_export.py --json `
  --output reports\quant_export_verification_latest.json `
  data\quant_lab\backtests\qlab_run_id\exports\20260505T000000000000Z_jsonl
```

Success criteria:

- process exits `0`
- output JSON has `status=success`
- output JSON has `files_failed=0`

### Verify A Copied Export

```powershell
Copy-Item `
  data\quant_lab\backtests\qlab_run_id\exports\20260505T000000000000Z_jsonl `
  F:\tmp\copied_quant_export `
  -Recurse

python scripts\verify_quant_export.py F:\tmp\copied_quant_export
```

The copied folder should verify because `package_manifest.json` stores relative paths.

### Expected Tamper Behavior

If any exported file is edited, truncated, or replaced:

- CLI exits non-zero.
- report status becomes `partial`.
- the failed file includes expected and actual SHA-256 and byte size.

## Safety Properties

- Offline verification is read-only.
- The verifier never rewrites package files or export manifests.
- File paths are constrained to the export directory.
- Absolute paths in legacy manifests are normalized only for legacy offline verification.
- Missing files, hash drift, size drift, and decode errors fail closed.
- API export verification remains unchanged.

## Practical Improvement Points

### 1. Add Signed Package Manifests

The current manifest is hash-based but unsigned. A future signed package should add:

- signing key id
- signature algorithm
- signature over canonical package manifest JSON
- verification command that separates hash drift from signature failure

### 2. Persist Verification Reports

Automation can write:

```text
reports/quant_export_verification/{timestamp}_{run_id}_{export_id}.json
```

This would make export integrity trendable without rescanning all packages each run.

### 3. Add Cross-Run Cleanup Preview IDs

Before any cross-run cleanup apply endpoint exists, add preview ids:

```text
cleanup_preview_id = hash(candidate export roots + keep policy + generated_at)
```

Apply should require the exact preview id or exact candidate list. This prevents a stale UI from deleting a different set of exports.

### 4. Add Replay Report Drilldown

The next read-only UI improvement should compare saved replay reports side by side without recomputing:

- original metrics
- replay metrics
- metric deltas
- tolerance failures
- config hash status
- code-version differences
- data-snapshot differences

### 5. Keep Qlib Execution Separate

Qlib data export exists, but provider execution remains intentionally outside verified scope. When added, Qlib execution should write provider-specific results under a separate branch and never overwrite deterministic FinGPT metrics.

## Final Assessment

The two source MD files remain complete for the deterministic FinGPT Quant Lab boundary. The export subsystem now has a practical audit chain:

```text
generate -> verify through API -> list -> cleanup preview/apply per run -> cross-run storage report -> offline package verification
```

The next safest product-depth increment is signed or persisted verification reporting, not Qlib execution or broad strategy schema changes.
