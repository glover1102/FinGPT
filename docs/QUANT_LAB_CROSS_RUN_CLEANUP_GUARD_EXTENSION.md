# Quant Lab Cross-Run Cleanup Guard Extension

> Date: 2026-05-05 12:11 KST
> Scope: guarded cross-run cleanup for Quant Lab artifact exports
> Source documents: `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`, `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: implemented and verified in the local Windows workstation

## Final Summary

The two source MD files remained complete for the original FinGPT Quant Lab compatibility contract. The concrete remaining product-depth gap was not another quant engine rewrite. It was export operations safety:

```text
per-run cleanup -> cross-run storage report -> offline package verification -> guarded cross-run cleanup
```

Before this run, operators could inspect total export storage across runs and could cleanup one run at a time. Cross-run apply was intentionally absent because deleting across many saved runs is stateful and risky. This run adds cross-run cleanup only with an exact preview guard.

## What Changed

### Backend

Files:

- `pipelines/backtest/artifact_exports.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `app/api/routers/quant_lab.py`

Added:

- `preview_cross_run_artifact_export_cleanup(...)`
- `cleanup_cross_run_artifact_exports(...)`
- `preview_cross_run_export_cleanup(...)`
- `cleanup_cross_run_exports(...)`
- `GET /api/v1/quant/exports/cleanup-preview`
- `POST /api/v1/quant/exports/cleanup`

The preview endpoint scans saved Quant Lab run export directories and selects candidates using:

```text
candidate = export older than keep_last_exports within its run
candidate must also satisfy stale_after_days
```

The apply endpoint recomputes the current preview and requires:

```json
{
  "preview_id": "exact preview hash from latest preview",
  "candidate_ids": ["exact candidate ids from latest preview"],
  "keep_last_exports": 1,
  "stale_after_days": 0,
  "limit": 50
}
```

If the preview id is stale or the candidate list is incomplete, cleanup fails before deleting anything.

### UI

Files:

- `app/web/index.html`
- `app/web/app.js`
- `scripts/check_ui_contract.py`
- `scripts/quant_lab_ui_smoke.py`

Added:

- Run History `cleanup preview` action.
- Storage-report inline `cleanup preview` action.
- Cross-run cleanup preview rendering.
- Exact-preview apply action.
- Static UI contract marker: `quant cross-run cleanup preview`.
- Playwright fallback smoke coverage for `cross-run export cleanup preview`.

## Safety Model

The delete path is intentionally narrow.

Cleanup can delete only:

```text
data/quant_lab/backtests/{run_id}/exports/{export_id}/
```

Cleanup cannot delete:

- source run artifacts such as `manifest.json`, `config.json`, `metrics.json`, `diagnostics.json`
- replay reports
- strategy definitions
- Qlib export/provider output
- files outside the selected run's `exports/` directory
- nested paths below a generated export directory

Apply also requires a direct-child directory check:

```text
resolved_target.parent == data/quant_lab/backtests/{run_id}/exports
```

This prevents a malformed candidate path from targeting a nested or external directory.

## Candidate Identity

Each cleanup candidate receives a SHA-256 `candidate_id` built from:

- run id
- export directory name
- export root
- export manifest path
- generated timestamp
- total bytes
- total rows

The preview id is a SHA-256 hash over:

- schema version
- artifact root
- keep-last policy
- stale-age policy
- sorted candidate ids

This means a stale UI cannot silently apply a cleanup after exports are added, removed, resized, or rescanned into a different candidate set.

## Operator Workflow

### Preview Only

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/quant/exports/cleanup-preview?keep_last_exports=5&stale_after_days=30&limit=100"
```

Expected response fields:

- `preview_id`
- `candidate_ids`
- `eligible_export_count`
- `candidate_count`
- `total_bytes_to_prune`
- `candidates`

### Apply Exact Preview

Use the exact `preview_id` and exact `candidate_ids` from the preview response:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/quant/exports/cleanup" `
  -H "Content-Type: application/json" `
  -d "{\"preview_id\":\"...\",\"candidate_ids\":[\"...\"],\"keep_last_exports\":5,\"stale_after_days\":30,\"limit\":100}"
```

Expected safe failure modes:

- wrong preview id -> HTTP 400
- missing candidate id -> HTTP 400
- changed export set -> HTTP 400
- path outside run exports -> HTTP 400
- already deleted export path -> HTTP 404

## Verification Record

Baseline before editing:

```powershell
python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q
# 18 passed

node --check app\web\app.js
# passed
```

After implementation:

```powershell
python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py scripts\check_ui_contract.py
# passed

node --check app\web\app.js
# passed

python -m pytest tests/test_quant_lab_pipeline.py::test_cross_run_export_cleanup_requires_exact_preview_candidates tests/test_quant_lab_api.py::test_export_cleanup_preview_and_apply_endpoint -q
# 2 passed

python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q
# 19 passed

python scripts\check_ui_contract.py
# passed, zero missing markers

python -m pytest tests -q
# 367 passed, 3 subtests passed

python -m core.preflight
# all critical dependencies operational

powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
# automated validation passed

python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "Browser Use IAB was not requested in this cross-run cleanup guard run; Playwright fallback used for automation acceptance"
# passed, console_errors=0
```

Browser fallback artifact:

```text
reports/browser_ui/quant_lab_ui_smoke_1777950609.png
```

### Automation 2 Re-Validation

The implementation and this MD were re-read and re-verified during the 2026-05-05 12:25 KST `automation-2` pass. No additional backend, frontend, or test code patch was required.

Fresh re-validation evidence:

- `python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py scripts\check_ui_contract.py`: passed.
- `node --check app\web\app.js`: passed.
- `python -m pytest tests/test_quant_lab_pipeline.py::test_cross_run_export_cleanup_requires_exact_preview_candidates tests/test_quant_lab_api.py::test_export_cleanup_preview_and_apply_endpoint -q`: `2 passed`.
- `python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q`: `19 passed`.
- `python scripts\check_ui_contract.py`: passed with zero missing markers.
- `python -m pytest tests -q`: `367 passed, 3 subtests passed`.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- `python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "Browser Use IAB was not requested in this automation run; Playwright fallback used for cross-run cleanup guard acceptance"`: passed, console errors `0`, screenshot `reports/browser_ui/quant_lab_ui_smoke_1777951465.png`.

Final practical continuation document:

- `docs/QUANT_LAB_CROSS_RUN_CLEANUP_GUARD_FINAL_REVIEW_EXTENSION.md`

## Final MD Re-Analysis

After implementation and verification, the two source MD files were reviewed again.

### `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`

Status:

- Original compatibility phases 1-8 remain complete.
- Phase 9 remains default-disabled for true Qlib provider execution.
- The new cross-run cleanup guard is product-depth work, not compatibility-contract repair.
- The design's safety constraints still hold: data mart remains canonical, deterministic metrics stay outside the LLM, and cleanup does not affect source artifacts.

### `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`

Status:

- The previously remaining concrete item "cross-run cleanup preview/apply should require an exact preview id or exact candidate list" is now implemented with a stricter guard: exact preview id and exact candidate list.
- Remaining items are intentionally future-scoped:
  - Qlib provider execution.
  - Replay-report side-by-side drilldown.
  - true strategy v2 migration.
  - signed export packages.
  - persisted cleanup audit reports.

No unchecked checklist item or open task marker in the two source MD files is now blocking the deterministic Quant Lab boundary.

## Practical Improvement Points

### 1. Persist Cleanup Audit Reports

Next add write-on-apply reports:

```text
reports/quant_export_cleanup/{timestamp}_{preview_id}.json
```

Each report should store:

- preview id
- applied timestamp
- operator/runtime source
- keep-last policy
- stale-age policy
- candidate ids
- pruned directories
- bytes pruned
- failures

This makes cleanup decisions auditable after directories are removed.

### 2. Add Signed Package Manifests

Portable export packages are hash-verified but unsigned. Add optional signatures over canonical package manifest JSON:

- `QUANT_LAB_EXPORT_SIGNING_ENABLED=false` by default
- `QUANT_LAB_EXPORT_SIGNING_KEY_ID`
- algorithm field such as `hmac-sha256` or future asymmetric signing
- verifier output that separates hash drift from signature failure

Do not require signing for local startup or legacy export verification.

### 3. Add Replay Report Drilldown

Replay history exists, but the UI can become more useful by comparing saved replay reports without recomputing:

- latest replay vs selected previous replay
- metric deltas
- tolerance failures
- config hash status
- code version differences
- data snapshot differences

This is read-only and should be lower risk than provider execution.

### 4. Keep Qlib Execution Separate

The verified Qlib surface is still:

```text
disabled/default status -> optional data-mart CSV seed export
```

Real Qlib strategy execution should remain separate:

- provider-specific output path
- separate metrics namespace
- no overwrite of deterministic FinGPT metrics
- explicit `QUANT_LAB_QLIB_ENABLED=true`
- tests for disabled, dependency-missing, dry-run, and enabled export states before any provider execution comparison

### 5. Add Strategy V2 Only When Needed

The current strategy migration path normalizes legacy or missing schema versions to `quant_strategy_v1`. Do not create `quant_strategy_v2` until there is a real new field or behavior that cannot be represented safely in v1.

Candidate v2 triggers:

- multi-leg execution policy
- per-factor transform graph
- portfolio-level constraints embedded in strategy definition
- benchmark-relative objective
- provider-specific strategy branch

## Practical Next Sequence

Recommended order:

1. Persist cleanup audit reports.
2. Add signed package manifests.
3. Add replay report drilldown UI.
4. Add strategy v2 only after a real schema requirement appears.
5. Add Qlib provider execution only after explicit acceptance work is requested.

Avoid doing these in one broad patch. Each item has a different risk profile and should keep its own tests and verification record.

## Final Assessment

The Quant Lab export subsystem now has a complete local audit chain:

```text
generate -> list -> verify -> package -> offline verify -> per-run cleanup -> cross-run storage report -> guarded cross-run cleanup
```

The best next increment is persisted cleanup audit reporting or signed package manifests. Qlib provider execution remains deliberately outside the verified deterministic boundary.
