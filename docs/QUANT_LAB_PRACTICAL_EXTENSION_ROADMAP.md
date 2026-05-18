# Quant Lab Practical Extension Roadmap

> Date: 2026-05-04 KST
> Scope: concrete post-completion extension plan after re-verifying `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: compatibility contract remains complete; this document starts the next improvement track.

## Current Verified Baseline

The Quant Lab compatibility implementation was rechecked against the current working tree and a fresh runtime process.

Verified commands:

- `python -m pytest tests -q`: `347 passed, 3 subtests passed`.
- `node --check app/web/app.js`: passed.
- `python scripts/check_ui_contract.py`: passed with zero missing markers.
- `python -m core.preflight`: all critical dependencies operational.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed and wrote fresh validation artifacts.
- `python scripts/browser_acceptance_matrix.py --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered" --output reports/browser_acceptance_latest.json`: passed the static UI contract and recorded Browser Use IAB as blocked, not passed.

Fresh-server runtime check:

- Server: `http://127.0.0.1:8134`.
- `GET /api/v1/health`: `status=ok`.
- `GET /api/v1/data/health`: `status=ok`.
- `GET /api/v1/quant/config`: returned 14 factors.
- `POST /api/v1/quant/features/preview`: `status=success`.
- `POST /api/v1/quant/signals/generate`: `status=success`, `signal_shift_bars=1`.
- `POST /api/v1/quant/backtest`: `status=success`.
- `GET /api/v1/quant/backtest/{run_id}/bundle`: returned `schema_version=quant_lab_artifact_v1`, code version, and data snapshot.
- `POST /api/v1/quant/strategy/dry-run`: accepted a no-lookahead strategy and returned `valid=true`.

## What This Run Added

### Browser Evidence Matrix

Added `scripts/browser_acceptance_matrix.py`.

Purpose:

- Keep Browser Use IAB evidence separate from Playwright fallback evidence and static UI contract evidence.
- Prevent fallback screenshots or static HTML checks from being reported as successful Browser Use verification.
- Persist the latest evidence to `reports/browser_acceptance_latest.json`.

Practical command:

```powershell
python scripts/browser_acceptance_matrix.py `
  --browser-use-status blocked `
  --browser-use-error "No Codex IAB backends were discovered" `
  --playwright-status not_run `
  --output reports/browser_acceptance_latest.json
```

Acceptance rule:

- Explicit Browser Use acceptance is satisfied only when `browser_use_iab.status == "passed"`.
- `playwright_fallback.status == "passed"` is useful evidence, but it is still fallback evidence.
- `ui_contract.status == "passed"` is a fast static gate, not browser interaction proof.

### Resumable Quality Review

Extended `quality_review.py` with:

- `--case-limit`
- `--case-offset`
- `--resume-from`
- partial report writing after each completed case

This makes hourly automation safer because it can run bounded shards instead of restarting the full answer-quality suite.

Practical commands:

```powershell
python quality_review.py --suite analysis --case-offset 0 --case-limit 3 --output reports/quality_review_analysis_000.json
python quality_review.py --suite analysis --case-offset 3 --case-limit 3 --output reports/quality_review_analysis_003.json
python quality_review.py --suite topic --case-offset 0 --case-limit 2 --measure-latency --output reports/quality_review_topic_000.json
```

Resume command:

```powershell
python quality_review.py `
  --suite all `
  --resume-from reports/quality_review_results.json `
  --output reports/quality_review_results.json
```

Operational note:

- A zero-case shard is only a CLI/preflight smoke. It is not answer-quality evidence.
- Release-candidate answer-quality evidence still requires real cases with `gate_failures=0`.

### Artifact Lineage And Replay

Quant Lab backtest artifacts now include stronger lineage in `manifest.json`:

- `schema_version`
- `config_hash`
- `code_version.git_commit`
- `code_version.git_dirty`
- `data_snapshot.source`
- `data_snapshot.price_counts`
- `data_snapshot.latest_dates`
- `data_snapshot.latest_as_of`
- missing and excluded assets
- cost model

The saved `config.json` now also includes:

- `schema_version=quant_lab_config_v1`
- expanded feature specs
- engine config
- validation output

Added replay helper:

- `pipelines.orchestration.quant_lab_pipeline.replay_backtest_from_manifest(run_id)`

Acceptance rule:

- A replay on the same data snapshot should reproduce deterministic metrics.
- If metrics differ, inspect the manifest data snapshot and git dirty state before trusting the comparison.

### Strategy Lifecycle Guard

Strategy persistence now normalizes user-saved strategies with:

- `schema_version=quant_strategy_v1`
- `strategy_version`
- `source`
- `created_at`
- `updated_at`

It rejects strategies that do not use `execution.trade_at=next_bar_close`.

Added route:

- `POST /api/v1/quant/strategy/dry-run`

Purpose:

- Validate a strategy before saving it.
- Report unsupported factor IDs.
- Confirm no-lookahead execution policy.

Practical payload:

```json
{
  "strategy_id": "runtime_check_v1",
  "features": {
    "momentum_63d": {"id": "momentum_63d"}
  },
  "execution": {
    "trade_at": "next_bar_close"
  }
}
```

## Remaining Improvement Points

The original compatibility plan is complete. The remaining work is product hardening and should be tracked as a new improvement track.

### 1. Trade Attribution Depth

Current status:

- Backtests save trades, signals, equity curve, drawdown curve, weights, diagnostics, and manifest.
- Trade rows are still compact and template-dependent.

Recommended next implementation:

- Add a typed `TradeEvent` schema with:
  - `signal_date`
  - `execution_date`
  - `ticker`
  - `previous_weight`
  - `target_weight`
  - `delta_weight`
  - `execution_price`
  - `transaction_cost`
  - `slippage_cost`
  - `reason`
  - `lookahead_policy`
- Emit one event per asset per rebalance.
- Store `rebalance_snapshots.json` separately from `trades.json`.
- Add tests proving execution price comes after the signal date.

Best first test:

```powershell
python -m pytest tests/test_backtest_engine.py tests/test_quant_lab_pipeline.py -q
```

### 2. Data Freshness Semantics

Current status:

- Feature preview and backtest diagnostics expose missing and stale assets.
- Runtime manifest records latest dates and price counts.

Recommended next implementation:

- Add `freshness_policy` to Quant Lab API responses.
- Add per-ticker:
  - `latest_price_date`
  - `expected_latest_date`
  - `market_calendar_lag_days`
  - `freshness_status`
  - `failure_reason`
- Use explicit failure reasons:
  - `missing_asset`
  - `insufficient_history`
  - `stale_price`
  - `provider_empty`
  - `provider_failed`
- Update UI filters so partial assets are visible by default, not silently hidden.

### 3. Research Score Provenance

Current status:

- Research score remains optional and cannot directly become a trade.
- This is correct, but provenance is still thin.

Recommended next implementation:

- Add `research_score_status`:
  - `disabled`
  - `fresh`
  - `expired`
  - `sparse_evidence`
  - `unavailable`
  - `invalid`
- Store:
  - evidence IDs
  - model
  - prompt version
  - score as-of time
  - expiry time
- Add tests proving favorable research score cannot override failed factor or price validation.

### 4. Portfolio Risk Hardening

Current status:

- Portfolio optimizer remains deterministic.
- Backtest and optimizer workflows share the same practical UI surface.

Recommended next implementation:

- Add optional covariance shrinkage and expose whether it was used.
- Add concentration and max-weight diagnostics.
- Add risk contribution output and UI chart.
- Add benchmark-relative risk metrics.
- Keep HRP and Black-Litterman optional until shrinkage and risk contribution tests are stable.

### 5. Optional Qlib Adapter

Current status:

- Qlib remains intentionally disabled and out of the default path.
- This is not a blocker.

Recommended next implementation only after the above hardening:

- Add `QUANT_LAB_QLIB_ENABLED=false`.
- Return `disabled` when the flag is false.
- Return `dependency_missing` when Qlib is enabled but not importable.
- Export data mart slices into temporary Qlib-compatible provider files.
- Keep Qlib results separate from deterministic FinGPT results.

## Practical Milestones

### Milestone A: Automation Reliability

Deliverables:

- Browser acceptance matrix in the validation gate.
- Quality review shards in automation.
- Latest server port report.
- Cleanup guard for old validation processes.

Done when:

- `reports/browser_acceptance_latest.json` is produced every run.
- Quality review can resume without re-running completed cases.
- Automation report separates Browser Use, fallback browser, and static UI evidence.

### Milestone B: Auditability

Deliverables:

- Reproducible replay check from artifact manifest.
- Typed trade event schema.
- Rebalance snapshots.
- Manifest schema version tests.

Done when:

- A saved run can be replayed on the same data snapshot with stable metrics.
- Trade events explain each weight change.
- Manifest carries enough state to diagnose metric drift.

### Milestone C: Quant Depth

Deliverables:

- Stronger freshness policy.
- Research score provenance.
- Risk contribution diagnostics.
- Benchmark-relative portfolio metrics.

Done when:

- Partial/stale data cannot be mistaken for clean success.
- Research score impact is auditable.
- Portfolio risk is explained by contribution, not only weights.

### Milestone D: Optional Integrations

Deliverables:

- Disabled-by-default Qlib adapter.
- Optional Parquet export for large artifacts.
- Additional strategy templates.

Done when:

- Missing Qlib never breaks app startup.
- Data mart remains canonical.
- Provider-specific outputs are labeled separately from deterministic engine outputs.

## Suggested Next Commands

Fast local gate:

```powershell
python -m pytest tests/test_browser_acceptance_matrix.py tests/test_quality_review.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py tests/test_strategy_registry.py -q
node --check app/web/app.js
python scripts/check_ui_contract.py
```

Full deterministic gate:

```powershell
python -m pytest tests -q
python -m core.preflight
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
```

Fresh runtime smoke:

```powershell
$env:FINGPT_WEB_PORT = "8134"
python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8134
```

Then verify:

- `/api/v1/health`
- `/api/v1/data/health`
- `/api/v1/quant/config`
- `/api/v1/quant/features/preview`
- `/api/v1/quant/signals/generate`
- `/api/v1/quant/backtest`
- `/api/v1/quant/backtest/{run_id}/bundle`
- `/api/v1/quant/strategy/dry-run`

## Decision

Do not continue the completed compatibility automation as if Phases 1-8 are still open. Start a new improvement track around automation reliability, auditability, and quant depth. Keep optional integrations behind flags and outside the default workstation path until the deterministic engine has deeper attribution and replay coverage.
