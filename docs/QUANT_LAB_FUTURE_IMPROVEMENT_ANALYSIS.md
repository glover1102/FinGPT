# Quant Lab Future Improvement Analysis

> Date: 2026-05-04 KST
> Scope: post-completion improvement analysis for `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md`
> Status: implementation contract complete; latest improvement slice re-verified 2026-05-05 12:11 KST.

## Executive Summary

The FinGPT Quant Lab compatibility plan is now implemented around the correct boundaries:

```text
data_mart -> factors -> signals -> backtest -> portfolio -> artifacts -> UI
```

The core decision was sound: keep the deterministic quant stack inside existing FinGPT modules instead of creating a parallel `pipelines/quant` subsystem or importing FinceptTerminal architecture directly. The result is auditable enough for local research use: data comes from `data/research_mart.db`, signals carry next-bar execution diagnostics, backtests write artifact bundles, the UI can reopen saved runs, and the legacy endpoints remain compatible.

The next phase should not be another broad rewrite. It should harden reproducibility, attribution, and operator confidence around the now-working system.

## Verified Baseline

The final completion runs verified:

- `python -m pytest tests -q`: `343 passed, 3 subtests passed`.
- `node --check app/web/app.js`: passed.
- `python scripts/check_ui_contract.py`: passed.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Fresh local server on `http://127.0.0.1:8131/ui/`: health returned `{"status":"ok","version":"1.1.0"}`.
- Legacy compatibility: `/api/v1/data/health`, `/api/v1/data/prices/SPY`, `/api/v1/dashboard/equity-heatmap`, `/api/v1/backtest/run`, and `/api/v1/portfolio/optimize` responded successfully.
- Quant Lab compatibility: `/api/v1/quant/config`, `/api/v1/quant/features/preview`, `/api/v1/quant/signals/generate`, `/api/v1/quant/backtest`, `/api/v1/quant/backtests`, and `/api/v1/quant/backtest/{run_id}/bundle` responded successfully.
- Supplementary UI fallback clicked the Quant Lab workflow end to end and captured no console errors or warnings.

Browser Use itself remains blocked by the local Codex IAB backend discovery failure. That is an environment/tooling limitation, not an application failure, and should remain visible in future automation reports.

### Closure Re-Verification: 2026-05-04 23:40 KST

The final automation closure run rechecked the completed implementation against the current dirty worktree and a fresh server process:

- `node --check app/web/app.js`: passed.
- `python scripts/check_ui_contract.py`: passed.
- Targeted Quant Lab/router/UI tests: `23 passed`.
- `python -m pytest tests -q`: `343 passed, 3 subtests passed`.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed and wrote fresh validation artifacts.
- Fresh server on `http://127.0.0.1:8133/ui/` exposed the latest Quant Lab route table, including `/api/v1/quant/backtest/{run_id}/bundle`.
- Live API checks on the fresh server passed for legacy `/api/v1/backtest/run`, legacy `/api/v1/portfolio/optimize`, `/api/v1/quant/features/preview`, `/api/v1/quant/signals/generate`, `/api/v1/quant/backtest`, and artifact bundle reload.
- The fresh Quant signal and backtest diagnostics returned `lookahead_safe=true` and `signal_shift_bars=1`.
- Browser Use IAB was attempted again and remained blocked by backend discovery. A separately labeled fallback browser smoke clicked Quant Lab, Feature Preview, Signal Matrix, Backtest Workbench, Portfolio Optimizer, Run History refresh, and saved-run reopen with zero captured console errors or warnings.

Disposition: stop the current compatibility-plan automation. Remaining work belongs in a new improvement track, not in the completed `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` automation.

### Practical Extension Run: 2026-05-04 23:59 KST

This run implemented the first concrete improvement slice from the future-improvement track:

- Added `scripts/browser_acceptance_matrix.py` and `reports/browser_acceptance_latest.json` generation so Browser Use IAB, Playwright fallback, and static UI contract evidence are reported separately.
- Added `quality_review.py --case-limit`, `--case-offset`, and `--resume-from`, with partial report writes after every completed case.
- Extended Quant Lab artifact manifests with `schema_version`, `config_hash`, `code_version`, and data snapshot lineage.
- Added `replay_backtest_from_manifest(run_id)` for deterministic same-snapshot replay checks.
- Added strategy persistence governance fields and `POST /api/v1/quant/strategy/dry-run` for no-lookahead/factor validation before saving.
- Added `docs/QUANT_LAB_PRACTICAL_EXTENSION_ROADMAP.md` as the concrete next-track execution document.

Verified:

- `python -m pytest tests/test_browser_acceptance_matrix.py tests/test_quality_review.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py tests/test_strategy_registry.py -q`: `12 passed`.
- `python -m py_compile scripts/browser_acceptance_matrix.py quality_review.py pipelines/backtest/artifacts.py pipelines/orchestration/quant_lab_pipeline.py pipelines/strategies/storage.py app/api/routers/quant_lab.py`: passed.
- `python scripts/browser_acceptance_matrix.py --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered" --output reports/browser_acceptance_latest.json`: UI contract passed; Browser Use IAB was recorded as blocked, not passed.
- `python quality_review.py --suite analysis --case-offset 0 --case-limit 0 --output reports/quality_review_shard_smoke.json`: CLI/preflight shard smoke passed. This is not answer-quality evidence because no cases were run.
- `node --check app/web/app.js`: passed.
- `python scripts/check_ui_contract.py`: passed.
- `python -m pytest tests -q`: `347 passed, 3 subtests passed`.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Fresh server on `http://127.0.0.1:8134` passed health, data health, Quant config, feature preview, signal generation, Quant backtest, artifact bundle reload, and strategy dry-run checks.

Remaining future work before the 2026-05-05 hardening run:

- Rich per-asset trade attribution, deeper freshness policy, research-score provenance, portfolio risk contributions, and disabled-by-default Qlib adapter were the actionable remaining improvements.

### Completion Hardening Run: 2026-05-05 00:20 KST

This run closed the remaining practical future-improvement items that were still concrete enough to implement inside the deterministic Quant Lab boundary:

- Standardized backtest trade rows into per-asset execution events with `signal_date`, `execution_date`, `ticker`, `previous_weight`, `target_weight`, `delta_weight`, price, cost, slippage, reason, and no-lookahead diagnostics.
- Added momentum-ranking rebalance snapshots with selected assets, rejected assets, scores, target weights, and turnover.
- Added explicit daily-price freshness policy diagnostics: expected latest market date, latest price dates, market-calendar lag days, stale assets, per-asset freshness audits, and manifest data-snapshot freshness fields.
- Wired optional research-score provenance into Quant Lab signal generation from `data/runs.db` history, including score status, run id, model, prompt/schema version, evidence doc IDs, as-of time, and expiry.
- Hardened portfolio risk diagnostics with correlation matrix output, concentration HHI, effective number of positions, actual max weight, capped assets, risk contribution sum, and risk contribution method.
- Added a disabled-by-default Qlib adapter boundary plus `GET /api/v1/quant/qlib/status`, keeping Qlib outside application startup and the default deterministic workflow.
- Added `docs/QUANT_LAB_COMPLETION_EXTENSION_PLAYBOOK.md` as the final practical extension/playbook document.

Verified:

- `python -m pytest tests/test_backtest_engine.py tests/test_portfolio_optimizer.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py -q`: `20 passed`.
- `python -m py_compile core/schemas/quant.py pipelines/backtest/validation.py pipelines/backtest/engine.py pipelines/orchestration/quant_lab_pipeline.py pipelines/signals/research_score.py pipelines/portfolio/optimizer.py pipelines/adapters/qlib_adapter.py app/api/routers/quant_lab.py core/config/settings.py`: passed.
- `python -m pytest tests -q`: `349 passed, 3 subtests passed`.
- `node --check app/web/app.js`: passed.
- `python scripts/check_ui_contract.py`: passed with zero missing UI markers.
- `python -m core.preflight`: all critical dependencies operational.
- `python scripts/browser_acceptance_matrix.py --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered" --output reports/browser_acceptance_latest.json`: static UI contract passed and Browser Use IAB remained correctly recorded as blocked.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Fresh server on `http://127.0.0.1:8135` passed health, Qlib disabled status, Quant feature preview, research-score signal generation, Quant backtest, artifact bundle reload, and portfolio risk diagnostics smoke checks.

Remaining expansion work is now intentionally product-depth work, not compatibility completion work:

- Render rebalance snapshots and research-score provenance more prominently in the UI.
- Add optional covariance shrinkage and benchmark-relative portfolio risk.
- Add data-mart-to-Qlib export only if `QUANT_LAB_QLIB_ENABLED=true` is explicitly requested.
- Keep Browser Use IAB verification separate from fallback browser/static UI evidence until the local IAB backend is available.

### Product-Depth Extension Run: 2026-05-05 01:13 KST

This run implemented the practical product-depth work that was still actionable from this improvement analysis:

- Added strict freshness request controls: `require_fresh_prices` and `max_market_calendar_lag_days` for feature preview, signal generation, and Quant backtests.
- Added fail-closed strict Quant backtest behavior while preserving warning-first default local research behavior.
- Returned and rendered rebalance snapshots directly from Quant backtest responses, including selected/rejected assets and turnover.
- Rendered research-score provenance in the Signal Matrix when research confirmation is enabled.
- Rendered freshness policy and per-asset freshness audits in Feature Preview, Signal Matrix, and Backtest diagnostics.
- Added portfolio benchmark, covariance method, and shrinkage controls in the UI.
- Added diagonal covariance shrinkage and benchmark-relative portfolio metrics in the deterministic optimizer.
- Added `POST /api/v1/quant/qlib/export` as a disabled-by-default export boundary that reports `disabled`, `dependency_missing`, or `dry_run_only` without making Qlib a startup dependency.
- Added `docs/QUANT_LAB_PRODUCT_DEPTH_EXTENSION_PLAN.md` as the final practical extension and continuation document.

Verified:

- Targeted Quant/portfolio tests: `22 passed`.
- Focused routing/UI/data-quality regression tests: `28 passed`.
- Full suite: `353 passed, 3 subtests passed`.
- `node --check app/web/app.js`: passed.
- `python scripts/check_ui_contract.py`: passed.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Fresh server on `http://127.0.0.1:8136`: health, Qlib status/export, feature preview, strict-freshness preview, research-score signal generation, Quant backtest, artifact bundle reload, and diagonal-shrinkage portfolio smoke all passed.
- Playwright fallback browser smoke clicked Quant Lab, exercised the new controls, ran feature/signal/backtest/portfolio workflows, captured zero console errors, and saved `reports/browser_ui/automation_2_quant_lab_product_depth_58719.png`.
- Browser Use IAB remained blocked by `No Codex IAB backends were discovered`; this is recorded as blocked, not passed.

Remaining expansion work is now narrower:

- Convert the current UI smoke into a committed Playwright regression test for the new product-depth controls.
- Add artifact compare/replay UI so users can compare current metrics with saved manifest replays.
- Add actual data-mart-to-Qlib export only behind `QUANT_LAB_QLIB_ENABLED=true`, with fake-provider tests before any real provider workflow.
- Keep `quality_review.py --suite all` as a long-running research-output quality gate separate from deterministic Quant Lab compatibility.

### Replay/Profile Regression Run: 2026-05-05 02:12 KST

This run completed the first two concrete remaining expansion items from the product-depth section:

- Added named freshness profiles so operators can select policy intent instead of hand-tuning calendar lag:
  - `research_default`: warning-first, max 3 market-day lag.
  - `decision_review`: strict, max 1 market-day lag.
  - `historical_lab`: warning-first, max 30 market-day lag.
- Added profile resolution on the backend while preserving explicit request-field overrides.
- Added profile selection to the Quant Lab UI.
- Added artifact replay comparison:
  - `POST /api/v1/quant/backtest/{run_id}/replay`
  - original metrics
  - replay metrics
  - metric deltas
  - config hash equality
  - original/current code lineage
- Added UI replay comparison from the active backtest result and from Run History.
- Added `scripts/quant_lab_ui_smoke.py`, a committed Playwright fallback smoke that exercises Feature Preview, Signal Matrix, Backtest, Replay Compare, Portfolio Optimize, and Run History replay controls.
- Hardened Quant Lab run IDs with microsecond timestamps to avoid immediate replay overwriting a same-second artifact.
- Added the detailed continuation document `docs/QUANT_LAB_REPLAY_BROWSER_REGRESSION_EXTENSION.md`.

Verified:

- Targeted profile/replay API tests: `16 passed`.
- Full test suite: `355 passed, 3 subtests passed`.
- `node --check app\web\app.js`: passed.
- `python scripts\check_ui_contract.py`: passed.
- Playwright fallback smoke: passed, console errors `0`, screenshot `reports\browser_ui\quant_lab_ui_smoke_1777914590.png`.
- Browser acceptance matrix updated with Browser Use IAB still blocked and Playwright fallback passed.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Fresh server on `http://127.0.0.1:8137`: `decision_review` profile diagnostics, `historical_lab` backtest, and replay comparison passed with `config_hash_match=true` and `total_return_delta=0.0`.

Remaining expansion work after this run:

- Qlib data-mart export was still pending until explicit `QUANT_LAB_QLIB_ENABLED=true` acceptance work.
- Strategy governance UI was still a useful next product feature at this checkpoint.
- `quality_review.py --suite all` remains a separate long-running research-output quality gate.
- Browser Use IAB should be retried when the local Codex IAB backend becomes available; Playwright fallback should remain labeled separately.

### Strategy Governance And Qlib Export Completion Run: 2026-05-05 03:11 KST

This run completed the two concrete product-depth items that remained after the replay/profile regression work, while preserving the completed compatibility contract:

- Added `freshness_profile` to `QuantBacktestRequest`, so Quant backtests now honor the same `research_default`, `decision_review`, and `historical_lab` profile selection that Feature Preview and Signal Matrix already used.
- Added `pipelines/adapters/qlib_export.py` and upgraded `POST /api/v1/quant/qlib/export` from preview-only to an explicit opt-in data-mart CSV provider seed export.
- Kept Qlib disabled by default. Disabled export returns `status=disabled`, `export_written=false`, and writes no files.
- When `QUANT_LAB_QLIB_ENABLED=true`, export writes `calendars/day.txt`, `instruments/all.txt`, `features/{ticker}.csv`, and `manifest.json` from `data/research_mart.db`. Missing Qlib runtime remains visible as `exported_dependency_missing`; this is export evidence, not provider-execution evidence.
- Added Strategy Governance to the Quant Lab UI: registry table, JSON editor, draft generation, dry-run validation, save, delete, and control synchronization into the backtest/portfolio workbench.
- Extended `scripts/check_ui_contract.py` and `scripts/quant_lab_ui_smoke.py` so the new Strategy Governance surface is part of static and fallback browser acceptance.
- Added `docs/QUANT_LAB_AUTOMATION_2_FINAL_EXPANSION_REPORT.md` as the final practical extension record and continuation playbook.

Verified:

- `python -m pytest tests/test_quant_lab_pipeline.py -q`: `6 passed`.
- `python -m pytest tests/test_qlib_adapter_export.py tests/test_quant_lab_api.py::test_qlib_export_preview_is_disabled_by_default -q`: `3 passed`.
- `python -m pytest tests/test_strategy_registry.py tests/test_quant_lab_api.py tests/test_qlib_adapter_export.py -q`: `10 passed`.
- `node --check app\web\app.js`: passed.
- `python scripts\check_ui_contract.py`: passed with strategy governance markers.
- `python -m pytest tests -q`: `357 passed, 3 subtests passed`.
- `python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered"`: passed, console errors `0`, screenshot `reports\browser_ui\quant_lab_ui_smoke_1777918181.png`.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented. The system now exports a data-mart CSV seed, but does not run Qlib strategies or compare provider metrics.
- `quality_review.py --suite all` remains a separate long-running research-output quality gate, not a deterministic Quant Lab compatibility blocker.
- Browser Use IAB should be retried when the local Codex IAB backend becomes available; current evidence remains Playwright fallback plus static UI contract.
- Strategy migration helpers for future schema versions are still future work; current saved strategies default to `quant_strategy_v1` and are validated at save/dry-run time.

### Replay Tolerance And Strategy Migration Run: 2026-05-05 04:14 KST

This run completed the next narrow auditability slice after re-reading this future-improvement analysis and the compatibility design:

- Added persisted replay comparison reports to `POST /api/v1/quant/backtest/{run_id}/replay`.
- Added tolerance policy output: `tolerance_policy`, `tolerance_passed`, and `tolerance_failures`.
- Added `replay_report.json` to the saved artifact bundle and exposed it through `GET /api/v1/quant/backtest/{run_id}/bundle`.
- Fixed a named freshness profile replay bug: `historical_lab` now persists the resolved 30-day market-calendar lag policy instead of replaying with the raw default 3-day lag.
- Added strategy schema migration helpers and `POST /api/v1/quant/strategy/migrate`; legacy/missing schema versions normalize to `quant_strategy_v1`, while unsupported future schemas fail explicitly.
- Surfaced replay tolerance status and strategy migration details in the Quant Lab UI.
- Added `docs/QUANT_LAB_REPLAY_TOLERANCE_STRATEGY_MIGRATION_EXTENSION.md` as the detailed final expansion artifact for this run.

Verification:

- Targeted replay/API/strategy tests: `19 passed`.
- Full suite: `362 passed, 3 subtests passed`.
- `node --check app\web\app.js`: passed.
- `python scripts\check_ui_contract.py`: passed.
- `python scripts\quant_lab_ui_smoke.py --timeout-s 180 --browser-use-status blocked --browser-use-error "No Browser Use IAB tool was available from tool discovery in this run"`: passed with zero console errors and screenshot `reports\browser_ui\quant_lab_ui_smoke_1777921954.png`.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Fresh server on `http://127.0.0.1:61211`: health, config profile discovery, historical_lab backtest, replay `config_hash_match=true`, replay `tolerance_passed=true`, persisted replay report bundle reload, strategy migration, strategy dry-run, and disabled Qlib export all passed.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay-report history/diff UI is still future work; this run stores the latest replay report per artifact.
- Strategy schema migration beyond `quant_strategy_v1` is intentionally not implemented until a real v2 schema exists.
- Browser Use IAB should still be retried when the local Codex IAB backend becomes available; current browser evidence remains Playwright fallback plus static UI contract.

2026-05-05 04:14 KST update: persisted replay reports, tolerance policies, resolved freshness-profile replay, and strategy schema migration helpers are now implemented and verified. The remaining future scope is narrower: Qlib provider execution, replay-report history/diff UI, strategy schema migration beyond `quant_strategy_v1`, and larger-run export formats.

### Replay History And Artifact Export Run: 2026-05-05 05:09 KST

This run completed two concrete remaining product-depth items without changing the completed compatibility contract:

- Replay reports are now history-preserving. Each replay writes a timestamped report under `replay_reports/`, while `replay_report.json` remains the latest report for bundle consumers.
- Added `GET /api/v1/quant/backtest/{run_id}/replay-reports` and included replay report counts in Quant Run History.
- Added saved artifact exports through `POST /api/v1/quant/backtest/{run_id}/export` with `jsonl` and `csv` formats.
- Kept exports artifact-backed. The export path reads saved `manifest`, `config`, `metrics`, `diagnostics`, curves, trades, signals, weights, and latest replay report instead of recomputing a backtest.
- Updated the Quant Lab UI so Backtest, Replay Comparison, and Run History can open replay report history and request JSONL/CSV exports.
- Extended the committed Playwright fallback smoke to click replay history and JSONL export.
- Added `docs/QUANT_LAB_REPLAY_HISTORY_ARTIFACT_EXPORT_EXTENSION.md` as the final practical extension and continuation document.

Verified:

- Baseline targeted gate before editing: `16 passed`.
- Post-edit compile gate: `python -m py_compile pipelines\backtest\artifact_exports.py pipelines\orchestration\quant_lab_pipeline.py app\api\routers\quant_lab.py scripts\quant_lab_ui_smoke.py`: passed.
- Post-edit targeted gate: `16 passed`.
- Full suite: `python -m pytest tests -q`: `362 passed, 3 subtests passed`.
- `node --check app\web\app.js`: passed.
- `python scripts\check_ui_contract.py`: passed.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Playwright fallback smoke: passed, console errors `0`, screenshot `reports\browser_ui\quant_lab_ui_smoke_1777925371.png`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented. The verified Qlib surface remains disabled-by-default status/export.
- At that checkpoint, Parquet was still optional; the 2026-05-05 06:08 KST run below added dependency-detected Parquet export.
- Replay report UI now lists history, but deeper side-by-side drilldown can be added later.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.

### Parquet Artifact Export Run: 2026-05-05 06:08 KST

This run completed the remaining optional large-run export item without changing the completed compatibility contract:

- Added optional Parquet export to `POST /api/v1/quant/backtest/{run_id}/export`.
- Kept exports artifact-backed and read-only against saved Quant Lab run bundles.
- Added dependency detection for `pandas` plus `pyarrow` or `fastparquet`; missing optional dependencies return `status=dependency_missing` with `export_written=false`, row counts, and dependency diagnostics.
- Added Parquet buttons in Backtest diagnostics, Replay Comparison, Replay Report History, and Quant Run History.
- Updated the committed Playwright fallback smoke so browser acceptance covers `artifact parquet export`.
- Added `docs/QUANT_LAB_PARQUET_EXPORT_EXTENSION.md` as the final practical extension artifact and continuation guide.

Verified:

- Compile and JS syntax gates passed.
- Targeted Quant Lab/API/Qlib boundary tests: `16 passed`.
- Full suite: `python -m pytest tests -q`: `362 passed, 3 subtests passed`.
- UI contract: passed with zero missing markers.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- Playwright fallback smoke: passed with zero console errors, screenshot `reports\browser_ui\quant_lab_ui_smoke_1777928921.png`, and checked `artifact parquet export`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay report history exists, but deeper side-by-side multi-report drilldown remains future UI work.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.
- Optional artifact retention/checksum policy can be added once export volume grows.

### Export Integrity And Retention Run: 2026-05-05 07:08 KST

This run completed the concrete export integrity/retention item that remained after Parquet artifact export:

- Export responses and `export_manifest.json` now include SHA-256 checksums and byte sizes for generated JSONL, CSV, and Parquet files.
- `POST /api/v1/quant/backtest/{run_id}/export` accepts `keep_last_exports` for opt-in retention. The default remains non-destructive.
- Retention pruning is limited to generated export directories under a single run's `exports/` directory and never deletes source Quant Lab artifacts or replay reports.
- The Quant Lab UI export summary now displays checksum prefixes, file sizes, and retention-pruning results.
- Added `docs/QUANT_LAB_EXPORT_INTEGRITY_RETENTION_EXTENSION.md` as the final practical extension and continuation guide for export auditability.

Verified:

- Baseline targeted Quant Lab/API/Qlib export tests: `16 passed`.
- Compile gate: passed.
- JS syntax gate: passed.
- Targeted Quant Lab pipeline/API tests: `14 passed`.
- UI contract: passed with zero missing markers.
- Full suite: `362 passed, 3 subtests passed`.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- Playwright fallback smoke: passed with zero console errors, screenshot `reports/browser_ui/quant_lab_ui_smoke_1777932649.png`, including `artifact export integrity`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay report history exists, but deeper side-by-side multi-report drilldown remains future UI work.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.
- Export integrity now records checksums; a future verification endpoint can re-hash existing exports and report drift without generating a new export.

### Export Verification And History Run: 2026-05-05 08:15 KST

This run completed the next concrete export auditability item after export integrity/retention:

- Added read-only export history listing through `GET /api/v1/quant/backtest/{run_id}/exports`.
- Added read-only export integrity verification through `POST /api/v1/quant/backtest/{run_id}/export/verify`.
- Verification re-hashes files listed in `export_manifest.json`, compares SHA-256 and byte size, and returns per-file pass/fail details.
- Verification is path-contained to the selected run's `exports/` directory and rejects manifest paths outside that boundary.
- Added tamper-detection regression coverage by modifying a generated JSONL export and confirming the verification response becomes `partial`.
- Added Quant Lab UI controls for export retention, export history, and verify-latest/export-manifest verification.
- Extended the committed Playwright fallback smoke to exercise export verification and export history.
- Added `docs/QUANT_LAB_EXPORT_VERIFICATION_HISTORY_EXTENSION.md` as the concrete final summary and continuation document for this run.

Verified:

- Baseline targeted Quant Lab/API tests: `14 passed`.
- Compile gate: passed.
- JS syntax gate: passed.
- Targeted API tests after implementation: `6 passed`.
- Targeted Quant Lab pipeline/Qlib/browser-acceptance tests: `11 passed`.
- UI contract: passed with zero missing markers.
- Full suite: `362 passed, 3 subtests passed`.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- First Playwright fallback smoke found a real UI regression: export result pages did not preserve verify/history controls.
- After the UI fix, Playwright fallback smoke passed with zero console errors, screenshot `reports/browser_ui/quant_lab_ui_smoke_1777936479.png`, including `artifact export verify` and `artifact export history`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay report history exists, but deeper side-by-side multi-report drilldown remains future UI work.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.
- At that checkpoint, export cleanup preview was still pending; the 2026-05-05 09:10 KST run below added run-level retention preview and explicit cleanup apply.

### Export Cleanup Preview Run: 2026-05-05 09:10 KST

This run completed the concrete cleanup-dashboard item left after export verification/history:

- Added a non-destructive export cleanup preview that computes exactly which generated export directories would be kept or pruned for a selected run and `keep_last_exports` policy.
- Added a scoped export cleanup apply path that prunes only generated directories under that run's `exports/` directory.
- Added `GET /api/v1/quant/backtest/{run_id}/exports/cleanup-preview?keep_last_exports=N`.
- Added `POST /api/v1/quant/backtest/{run_id}/exports/cleanup`.
- Added API and pipeline regression coverage proving preview is non-destructive and apply prunes the expected directories.
- Added Quant Lab UI cleanup preview controls with kept/pruned rows, total byte impact, and preview-first apply.
- Extended the committed Playwright fallback smoke to cover `artifact export cleanup preview`.
- Added `docs/QUANT_LAB_EXPORT_CLEANUP_PREVIEW_EXTENSION.md` as the concrete final summary, verification record, improvement points, and next-extension playbook for this run.

Verified:

- Baseline before editing: `python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q`: `14 passed`.
- Compile gate: passed.
- JS syntax gate: passed.
- Targeted Quant Lab API/pipeline tests: `16 passed`.
- Full suite: `python -m pytest tests -q`: `364 passed, 3 subtests passed`.
- UI contract: passed with zero missing markers.
- Preflight: all critical dependencies operational.
- Targeted Browser/Qlib/strategy boundary tests: `8 passed`.
- Production path: automated validation passed.
- Playwright fallback smoke: passed with zero console errors, screenshot `reports/browser_ui/quant_lab_ui_smoke_1777939794.png`, including `artifact export cleanup preview`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay report history exists, but deeper side-by-side multi-report drilldown remains future UI work.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.
- At that checkpoint, cross-run export storage reporting and offline export-package verification were still future product-depth work; the 2026-05-05 10:08 KST run below added the read-only storage report.

### Cross-Run Export Storage Report Run: 2026-05-05 10:08 KST

This run completed the concrete cross-run storage-observability item left after export cleanup preview:

- Added `summarize_backtest_artifact_export_storage(...)` to scan all Quant Lab saved-run export directories without deleting or mutating files.
- Added `GET /api/v1/quant/exports/storage?limit=N&stale_after_days=N`.
- The report summarizes total runs, runs with exports, export directory count, total generated bytes, total exported rows, format counts, manifest status counts, oldest/newest export timestamps, top storage-heavy runs, and old export candidates.
- The scanner tolerates missing or corrupt `export_manifest.json` files and reports them under `manifest_status_counts` instead of failing the whole report.
- Added a Quant Lab Run History `storage report` UI action and cross-run storage table for operator review.
- Extended `scripts/check_ui_contract.py` with the `quant export storage report` marker.
- Extended the committed Playwright fallback smoke to exercise `cross-run export storage report`.
- Added `docs/QUANT_LAB_EXPORT_STORAGE_REPORT_EXTENSION.md` as the concrete final summary, verification record, improvement points, and next-extension playbook for this run.

Verified:

- Compile gate: passed.
- JS syntax gate: passed.
- Targeted Quant Lab API/pipeline tests: `17 passed`.
- UI contract: passed with zero missing markers.
- Full suite: `python -m pytest tests -q`: `365 passed, 3 subtests passed`.
- Targeted Browser/Qlib/strategy boundary tests: `8 passed`.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- Playwright fallback smoke: passed with zero console errors, screenshot `reports/browser_ui/quant_lab_ui_smoke_1777943321.png`, including `cross-run export storage report`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay report history exists, but deeper side-by-side multi-report drilldown remains future UI work.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.
- Offline export-package verification can be added next so copied export directories can be verified without FastAPI.
- Cross-run cleanup preview should only be considered after the read-only storage report has been used safely.

### Offline Export Package Verification Run: 2026-05-05 11:08 KST

This run completed the next concrete export auditability item after cross-run storage reporting:

- Added a portable `package_manifest.json` to newly generated Quant Lab JSONL, CSV, and Parquet artifact exports.
- The package manifest records relative file paths, SHA-256 checksums, byte sizes, source run id, source artifact manifest hash, config hash, code-version lineage, row counts, export format, dependency status, and retention policy.
- Added `verify_export_package(...)` so an export directory can be verified without FastAPI, without the original saved-run directory, and after the export folder has been copied elsewhere.
- Added `scripts/verify_quant_export.py` for operator use:

```powershell
python scripts\verify_quant_export.py data\quant_lab\backtests\{run_id}\exports\{export_id}
python scripts\verify_quant_export.py --json data\quant_lab\backtests\{run_id}\exports\{export_id}
```

- Kept legacy compatibility: export directories that only have `export_manifest.json` are still verifiable, with an explicit fallback warning.
- Added tamper-detection coverage proving a copied export package reports `status=partial` and exits non-zero after an exported data file is modified.
- Added `docs/QUANT_LAB_OFFLINE_EXPORT_PACKAGE_VERIFICATION_EXTENSION.md` as the concrete final summary, verification record, operating guide, improvement points, and next-extension playbook for this run.

Verified:

- Baseline before editing: `python -m pytest tests/test_quant_lab_api.py tests/test_quant_lab_pipeline.py -q`: `17 passed`.
- Baseline UI syntax/contract: `node --check app\web\app.js` passed; `python scripts\check_ui_contract.py` passed.
- Compile gate: `python -m py_compile pipelines\backtest\artifact_exports.py scripts\verify_quant_export.py` passed.
- New focused regression: `python -m pytest tests/test_quant_lab_pipeline.py::test_export_package_manifest_verifies_after_copy_and_detects_tamper -q`: `1 passed`.
- Targeted Quant Lab API/pipeline tests: `18 passed`.
- Boundary tests: `python -m pytest tests/test_browser_acceptance_matrix.py tests/test_qlib_adapter_export.py tests/test_strategy_registry.py -q`: `8 passed`.
- Full suite: `python -m pytest tests -q`: `366 passed, 3 subtests passed`.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- Playwright fallback smoke: passed with zero console errors, screenshot `reports/browser_ui/quant_lab_ui_smoke_1777946908.png`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay report history exists, but deeper side-by-side multi-report drilldown remains future UI work.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.
- Cross-run cleanup preview/apply should require an exact preview id or exact candidate list before any delete operation is allowed.
- Signed export packages can be added later on top of the portable package manifest.

### Cross-Run Cleanup Guard Run: 2026-05-05 12:11 KST

This run completed the concrete cross-run cleanup safety item left after offline export-package verification:

- Added cross-run cleanup preview for generated Quant Lab export directories across saved runs.
- Added guarded cross-run cleanup apply.
- Added `GET /api/v1/quant/exports/cleanup-preview?keep_last_exports=N&stale_after_days=N&limit=N`.
- Added `POST /api/v1/quant/exports/cleanup`.
- Apply requires both the exact `preview_id` and exact `candidate_ids` returned by the current preview.
- Apply recomputes the current preview before deleting anything, so stale preview ids and incomplete candidate lists fail closed.
- Cleanup only removes direct generated export directories under each run's `exports/` directory.
- Added Run History UI controls for cross-run cleanup preview and exact-preview apply.
- Extended static UI contract and Playwright fallback smoke coverage.
- Added `docs/QUANT_LAB_CROSS_RUN_CLEANUP_GUARD_EXTENSION.md` as the concrete final summary, verification record, improvement points, and next-extension playbook for this run.

Verified:

- Baseline targeted Quant Lab API/pipeline tests: `18 passed`.
- Baseline JS syntax: passed.
- Compile gate: passed.
- Focused new regressions: `2 passed`.
- Targeted Quant Lab API/pipeline tests: `19 passed`.
- UI contract: passed with zero missing markers.
- Full suite: `python -m pytest tests -q`: `367 passed, 3 subtests passed`.
- Preflight: all critical dependencies operational.
- Production path: automated validation passed.
- Playwright fallback smoke: passed with zero console errors, screenshot `reports/browser_ui/quant_lab_ui_smoke_1777950609.png`, including `cross-run export cleanup preview`.

Remaining expansion work after this run:

- Qlib provider execution is still intentionally not implemented.
- Replay report history exists, but deeper side-by-side multi-report drilldown remains future UI work.
- Strategy schema migration beyond `quant_strategy_v1` still waits for a real v2 strategy contract.
- Signed package manifests can now be added on top of portable package manifests and guarded cleanup.
- Persisted cleanup audit reports can be added so cross-run cleanup decisions are retained after apply.

## Improvement Theme 1: Browser Acceptance Reliability

The application now has a real UI workflow, but the acceptance surface still depends on whether Browser Use can attach to the in-app browser. The recurring automation should separate three browser evidence levels:

1. Browser Use IAB verification.
2. Playwright fallback verification.
3. Static UI contract verification.

Only the first should satisfy explicit Browser Use acceptance. The fallback is still valuable, but it should remain labeled as fallback so release evidence does not overclaim.

Recommended work:

- Add a small `scripts/browser_acceptance_matrix.py` that records `browser_use_iab`, `playwright_fallback`, and `ui_contract` separately.
- Persist the browser backend error string and timestamp in `reports/browser_acceptance_latest.json`.
- Keep a screenshot artifact for fallback runs, but do not let screenshot existence imply Browser Use success.

## Improvement Theme 2: Quality Gate Resumability

`quality_review.py --suite all` is useful, but it is too long for a 50-minute hourly automation slice when local LLM calls or provider calls slow down. It should become resumable and shardable.

Recommended work:

- Add `--case-limit`, `--case-offset`, and `--resume-from` options.
- Write a partial result after every case, not only at suite end.
- Add a deterministic `--suite quant-smoke` that exercises research-to-quant handoff without running the full answer-quality benchmark.
- Preserve the full `--suite all` gate for release-candidate validation, but keep hourly automation on bounded shards.

This will avoid orphaned long-running Python processes and make the automation safe to run every hour.

## Improvement Theme 3: Artifact Lineage And Reproducibility

The current artifact bundle is the right foundation. The next improvement is to make each run reproducible without relying on implicit local state.

Recommended work:

- Store a `config_hash`, code version, schema version, and data snapshot summary in every manifest.
- Include factor parameter expansion in `config.json`, not just the original user request.
- Include input price date ranges, row counts, missing dates, stale flags, and provider status IDs.
- Add a `replay_backtest_from_manifest(run_id)` test helper that reconstructs a prior run from stored artifacts and asserts stable metrics.

This would make the Quant Lab more audit-friendly and reduce ambiguity when metrics change after the data mart updates.

## Improvement Theme 4: Trade Attribution Depth

The UI now renders recent trades and signals, but the deterministic engine still has limited per-asset execution attribution for some templates. This is acceptable for the current implementation contract, but deeper portfolio diagnostics need richer event rows.

Recommended work:

- Standardize a `TradeEvent` schema with `signal_date`, `execution_date`, `ticker`, `target_weight`, `previous_weight`, `delta_weight`, `price`, `cost`, `slippage`, and `reason`.
- Add per-rebalance selected and rejected asset rows for ranking strategies.
- Store rebalance snapshots separately from trade events.
- Add tests proving that execution rows never use same-bar close information for signal generation and execution.

This is the highest-value next quant-engine improvement because it tightens auditability without adding speculative modeling complexity.

## Improvement Theme 5: Strategy Lifecycle Governance

The strategy registry exists, but strategy governance is still lightweight. As more templates are added, the registry needs versioning and compatibility checks.

Recommended work:

- Add `schema_version` and `strategy_version` to every strategy definition.
- Validate saved strategies against typed schemas before persistence.
- Add migration helpers for old strategy definitions.
- Add `created_at`, `updated_at`, and `source` fields for user-created strategies.
- Add a route that dry-runs a strategy definition and returns factor availability, signal policy, and data sufficiency before saving.

This prevents UI-saved strategies from becoming untestable blobs over time.

## Improvement Theme 6: Portfolio Risk Model Hardening

The portfolio optimizer now works from the same universe and date range, but risk estimates should become more explicit as the system matures.

Recommended work:

- Add covariance shrinkage as an optional method and expose whether it was used.
- Add concentration, turnover, and max-weight constraint diagnostics.
- Add risk contribution charts in the UI.
- Add benchmark-relative risk metrics for optimized portfolios.
- Keep Black-Litterman and HRP optional until the simpler covariance path is well tested.

The key rule should remain unchanged: portfolio weights are deterministic outputs and should never be generated by the LLM.

## Improvement Theme 7: Data Freshness And Failure Semantics

The data health surface is already visible, but Quant Lab should become stricter about partial and stale states.

Recommended work:

- Add per-endpoint `freshness_policy` fields to Quant Lab responses.
- Include `latest_price_date`, `expected_latest_date`, and `market_calendar_lag_days` for every ticker.
- Distinguish `missing_asset`, `insufficient_history`, `stale_price`, `provider_empty`, and `provider_failed`.
- Add UI filters for hiding or showing partial assets, with the default set to show warnings rather than hide them.

This matters because stale data shown as success is a larger product risk than a failed request.

## Improvement Theme 8: Research-To-Trade Bridge

The current bridge correctly keeps research score optional and deterministic filters in charge. The next step is to make this bridge explicit enough to audit.

Recommended work:

- Store research-score provenance with evidence IDs, model, prompt version, as-of time, and expiry.
- Add a `research_score_status` enum: `disabled`, `fresh`, `expired`, `sparse_evidence`, `unavailable`, `invalid`.
- Add backtest diagnostics showing whether research score affected eligibility, ranking, or only labels.
- Add tests proving that failed factor validation blocks a trade even when research score is favorable.

The UI language should continue to use candidate/watch/reject framing rather than buy/sell recommendation language.

## Improvement Theme 9: Optional Qlib Adapter Boundary

Qlib remains intentionally disabled. If it is added later, it should be an adapter, not a replacement for the deterministic engine.

Recommended work:

- Add `QUANT_LAB_QLIB_ENABLED=false` and keep it default-disabled.
- Export data mart slices into a Qlib-compatible temporary provider format.
- Return `disabled` or `dependency_missing` when Qlib is unavailable.
- Keep Qlib results clearly labeled as provider-specific and separate from deterministic FinGPT engine results.
- Never allow Qlib to become a hidden dependency for app startup, legacy endpoints, or default Quant Lab workflows.

This preserves Windows workstation reliability and avoids split-brain data ownership.

## Suggested Next Milestones

### Milestone A: Automation Reliability

- Browser acceptance matrix.
- Resumable quality review.
- Cleanup guard for orphaned validation processes.
- Single latest-server port discovery report.

### Milestone B: Auditability

- Reproducible artifact replay.
- Trade event schema.
- Manifest schema versioning.
- Strategy schema validation.

### Milestone C: Quant Depth

- Rich rebalance attribution.
- Portfolio risk contribution charts.
- Stronger stale-data semantics.
- Research-score provenance.

### Milestone D: Optional Integrations

- Disabled-by-default Qlib adapter.
- Export integrity and retention policy for JSONL/CSV/Parquet artifacts.
- Additional strategy templates only after trade attribution and replay are stable.

## Final Recommendation

Stop the current compatibility-plan automation. The plan's implementation contract is complete in the available environment. Future work should start as a new improvement track with narrower milestones, because continuing the same automation would mix completed acceptance work with product-hardening work and make status reporting less clear.

2026-05-05 update: the immediately actionable hardening, replay/profile, strategy-governance, Qlib data-mart export, replay tolerance, strategy migration, replay history, JSONL/CSV export, optional Parquet artifact export, export integrity/retention, export verification/history, export cleanup preview, cross-run export storage reporting, offline export-package verification, and guarded cross-run cleanup items from this improvement document are now implemented and covered by targeted, full-suite, production-path, static UI, preflight, CLI, and fallback browser verification. Future work should continue from `docs/QUANT_LAB_CROSS_RUN_CLEANUP_GUARD_EXTENSION.md` as narrower product-depth increments rather than compatibility-plan completion.
