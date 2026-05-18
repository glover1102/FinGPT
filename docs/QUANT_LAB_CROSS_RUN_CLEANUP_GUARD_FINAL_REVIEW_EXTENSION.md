# Quant Lab Cross-Run Cleanup Guard Final Review Extension

> Date: 2026-05-05 12:25 KST
> Automation ID: `automation-2`
> Source implementation document: `docs/QUANT_LAB_CROSS_RUN_CLEANUP_GUARD_EXTENSION.md`
> Status: current implementation re-verified; no additional code patch was required in this pass

## 1. Final Review Summary

This pass re-ran the `QUANT_LAB_CROSS_RUN_CLEANUP_GUARD_EXTENSION.md` work against the current `F:\LLM\FinGPT` checkout instead of relying on the document's prior completion claim.

The current code already contains the cross-run cleanup guard described by the source MD:

```text
saved Quant Lab exports
  -> cross-run cleanup preview
  -> preview_id + candidate_ids exact match
  -> guarded apply
  -> direct generated export directories only
```

The implementation is complete for the deterministic Quant Lab export-cleanup boundary. No new backend, frontend, or test code changes were needed during this review pass. The work performed here was verification, MD re-analysis, and writing this final practical continuation document.

## 2. Verified Implementation Surface

### Backend

Verified files:

- `pipelines/backtest/artifact_exports.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/api/routers/quant_lab.py`
- `tests/test_quant_lab_pipeline.py`
- `tests/test_quant_lab_api.py`

Verified functions:

- `preview_cross_run_artifact_export_cleanup(...)`
- `cleanup_cross_run_artifact_exports(...)`
- `preview_cross_run_export_cleanup(...)`
- `cleanup_cross_run_exports(...)`

Verified routes:

- `GET /api/v1/quant/exports/cleanup-preview`
- `POST /api/v1/quant/exports/cleanup`

The apply path recomputes the current preview and requires both:

- exact `preview_id`
- exact sorted `candidate_ids`

This is stricter than accepting either one independently. A stale preview id, missing candidate id, changed candidate set, or malformed cleanup target fails before deletion.

### Frontend

Verified files:

- `app/web/index.html`
- `app/web/app.js`
- `scripts/check_ui_contract.py`
- `scripts/quant_lab_ui_smoke.py`

Verified UI capabilities:

- Run History `cleanup preview` control.
- Cross-run storage-report inline cleanup preview control.
- Rendered cross-run cleanup preview state.
- Exact-preview apply payload sent from the current preview state.
- Static UI contract marker: `quant cross-run cleanup preview`.
- Browser fallback smoke marker: `cross-run export cleanup preview`.

### Safety Boundary

Cleanup is intentionally limited to generated export directories:

```text
data/quant_lab/backtests/{run_id}/exports/{export_id}/
```

It does not target:

- source artifact manifests
- source configs
- metrics and diagnostics files
- replay reports
- strategy definitions
- Qlib export/provider output
- nested directories below a generated export directory
- paths outside the selected run's `exports` directory

The target validator requires the resolved cleanup path to be a direct child of the run's `exports` directory.

## 3. Re-Verification Record

All commands below were rerun in this pass from:

```powershell
F:\LLM\FinGPT
```

### Syntax And Focused Regression

```powershell
python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py scripts\check_ui_contract.py
# passed

node --check app\web\app.js
# passed

python -m pytest tests/test_quant_lab_pipeline.py::test_cross_run_export_cleanup_requires_exact_preview_candidates tests/test_quant_lab_api.py::test_export_cleanup_preview_and_apply_endpoint -q
# 2 passed
```

### Quant Lab Targeted Suite

```powershell
python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q
# 19 passed
```

### Static UI Contract

```powershell
python scripts\check_ui_contract.py
# status=passed
# missing_markers=[]
# checked marker included: quant cross-run cleanup preview
```

### Full Test Suite

```powershell
python -m pytest tests -q
# 367 passed, 3 subtests passed
```

### Runtime Preconditions

```powershell
python -m core.preflight
# PREFLIGHT: All critical dependencies are operational.
```

### Production Path

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
# automated validation passed
# automated_passed=true
```

Fresh artifacts written by production validation:

- `data/outputs/validation_latest.json`
- `data/outputs/validation_20260505T032412Z.json`
- `reports/validation_latest.md`
- `reports/validation_20260505T032412Z.md`

### Browser Fallback Acceptance

```powershell
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "Browser Use IAB was not requested in this automation run; Playwright fallback used for cross-run cleanup guard acceptance"
# status=passed
# console_errors=[]
# checked included: cross-run export cleanup preview
```

Fresh browser artifact:

```text
reports/browser_ui/quant_lab_ui_smoke_1777951465.png
```

Acceptance matrix:

```text
reports/browser_acceptance_latest.json
```

Browser Use IAB was not claimed as passed in this run. The accepted browser evidence is Playwright fallback plus static UI contract.

## 4. Source MD Re-Analysis

The source MD was re-read after verification:

- `docs/QUANT_LAB_CROSS_RUN_CLEANUP_GUARD_EXTENSION.md`

The two upstream source documents named by the source MD were also re-read:

- `docs/QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
- `docs/QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`

Current disposition:

- The Fincept compatibility contract remains complete for phases 1-8.
- Phase 9 remains intentionally default-disabled for true Qlib provider execution.
- Cross-run cleanup is product-depth export-operability work, not a compatibility-contract repair.
- The future-improvement item requiring exact preview/candidate guarding before cross-run cleanup is implemented.
- No unchecked checklist item or open marker was found that blocks the deterministic Quant Lab boundary.

The remaining items are intentionally separate future tracks:

- true Qlib provider execution
- signed export/package manifests
- persisted cleanup audit reports
- replay-report side-by-side drilldown
- strategy schema v2 only when a real v2 contract exists

## 5. Current Operator Runbook

### Preview Cross-Run Cleanup

Use preview first:

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/quant/exports/cleanup-preview?keep_last_exports=5&stale_after_days=30&limit=100"
```

Review these fields:

- `preview_id`
- `candidate_ids`
- `candidate_count`
- `eligible_export_count`
- `total_bytes_to_prune`
- `candidates[].run_id`
- `candidates[].export_root`
- `candidates[].total_bytes`
- `candidates[].generated_at`

### Apply Exact Preview

Only apply the exact preview that was just reviewed:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/quant/exports/cleanup" `
  -H "Content-Type: application/json" `
  -d "{\"preview_id\":\"<preview_id>\",\"candidate_ids\":[\"<candidate_id>\"],\"keep_last_exports\":5,\"stale_after_days\":30,\"limit\":100}"
```

Expected safe failure cases:

- stale or wrong `preview_id`: HTTP 400
- missing or incomplete `candidate_ids`: HTTP 400
- changed export set between preview and apply: HTTP 400
- cleanup target outside run `exports`: HTTP 400
- selected export already deleted before apply: HTTP 404

### Recommended Manual Safety Check

Before applying a broad cleanup policy, run:

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/quant/exports/storage?limit=20&stale_after_days=30"
```

Use the storage report to inspect:

- largest runs
- oldest export timestamps
- stale export candidates
- manifest status counts
- total generated export bytes

Then run cleanup preview with a small `limit` before a broader cleanup.

## 6. Practical Improvement Points

### 6.1 Persist Cleanup Audit Reports

Highest-value next slice.

Problem:

- After cleanup apply, deleted directories are gone.
- The response contains what happened, but there is no durable cleanup decision log.

Add:

```text
reports/quant_export_cleanup/{timestamp}_{preview_id}.json
```

Report fields:

- schema version
- preview id
- applied timestamp
- runtime source, for example `api`, `ui`, or future `cli`
- artifact root
- keep-last policy
- stale-age policy
- limit
- exact candidate ids submitted
- recomputed candidate ids
- pruned export roots
- total bytes pruned
- per-target deletion status
- failures

Acceptance:

```powershell
python -m pytest tests/test_quant_lab_pipeline.py::test_cross_run_export_cleanup_writes_audit_report -q
python -m pytest tests/test_quant_lab_api.py::test_cross_run_export_cleanup_endpoint_returns_audit_report_path -q
python -m pytest tests -q
```

Do not put this audit log inside a deleted export directory. Use `reports/quant_export_cleanup/`.

### 6.2 Add A Cleanup Dry-Run CLI

Problem:

- API/UI cleanup is useful, but operator maintenance may happen when FastAPI is not running.

Add:

```powershell
python scripts\cleanup_quant_exports.py preview --keep-last 5 --stale-after-days 30 --limit 100
python scripts\cleanup_quant_exports.py apply --preview-file reports\quant_export_cleanup_preview\preview_....json
```

Design:

- Preview command writes immutable preview JSON.
- Apply command requires that preview JSON.
- Apply recomputes the candidate set before deletion.
- Apply refuses to proceed if the recomputed preview id differs.

Acceptance:

```powershell
python -m py_compile scripts\cleanup_quant_exports.py
python scripts\cleanup_quant_exports.py preview --artifact-root <tmp-artifacts> --keep-last 1 --stale-after-days 0 --limit 10 --json
python -m pytest tests/test_quant_export_cleanup_cli.py -q
```

### 6.3 Add Signed Package Manifests

Problem:

- Offline package verification proves hash equality, but not who produced or approved the package.

Add optional signing:

```env
QUANT_LAB_EXPORT_SIGNING_ENABLED=false
QUANT_LAB_EXPORT_SIGNING_KEY_ID=
```

Suggested first implementation:

- HMAC-SHA256 over canonical `package_manifest.json`.
- Keep disabled by default.
- Store `signature`, `signature_algorithm`, `key_id`, and canonical payload hash.
- Verifier separates checksum mismatch from signature mismatch.

Acceptance:

```powershell
python -m pytest tests/test_quant_lab_pipeline.py::test_export_package_signature_verifies_when_enabled -q
python scripts\verify_quant_export.py --json data\quant_lab\backtests\{run_id}\exports\{export_id}
```

Do not require signing for local startup, default export, or legacy package verification.

### 6.4 Add Replay Report Side-By-Side Drilldown

Problem:

- Replay history exists, but operators still need a richer comparison view across saved replay reports.

Add:

- report A selector
- report B selector
- original metrics side by side
- replay metrics side by side
- delta table
- tolerance failure grouping
- config hash equality
- code-version comparison
- data snapshot comparison

API shape:

```http
GET /api/v1/quant/backtest/{run_id}/replay-reports/{report_a}/compare/{report_b}
```

Acceptance:

```powershell
python -m pytest tests/test_quant_lab_api.py::test_replay_report_pair_compare_endpoint -q
node --check app\web\app.js
python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "Playwright fallback for replay-report drilldown"
```

Keep this read-only. Do not recompute backtests just to compare existing replay reports.

### 6.5 Keep Qlib Provider Execution Separate

Current verified Qlib boundary:

```text
disabled/default status
  -> optional data-mart CSV seed export
  -> no provider strategy execution
```

Do not mix Qlib provider execution into cleanup/export guard work.

If provider execution is requested later, require:

- `QUANT_LAB_QLIB_ENABLED=true`
- dependency status `available`
- explicit provider URI
- provider metrics under a separate response branch
- deterministic FinGPT metrics preserved as baseline
- tests for disabled, dependency-missing, dry-run, and enabled states

Acceptance:

```powershell
python -m pytest tests/test_qlib_adapter_export.py tests/test_qlib_adapter_runner.py -q
python -m pytest tests/test_quant_lab_api.py -q
```

## 7. Recommended Next Sequence

Do these as separate patches, not one broad refactor:

1. Persist cleanup audit reports.
2. Add cleanup preview/apply CLI.
3. Add signed package manifests.
4. Add replay report side-by-side drilldown.
5. Add strategy v2 only after a real schema change exists.
6. Add Qlib provider execution only if explicitly requested and accepted.

The best next task is persisted cleanup audit reports because it strengthens the exact feature just completed without expanding the modeling surface.

## 8. Final Assessment

The current export subsystem has a verified local audit chain:

```text
generate
  -> list
  -> verify
  -> package
  -> offline verify
  -> per-run cleanup preview/apply
  -> cross-run storage report
  -> guarded cross-run cleanup preview/apply
```

The cross-run cleanup guard is implemented and re-verified in this pass. The remaining work is not required for compatibility completion; it is product-depth auditability and operator tooling.
