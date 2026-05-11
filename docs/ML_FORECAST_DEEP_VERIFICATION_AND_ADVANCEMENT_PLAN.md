# ML Forecast Deep Verification and Advancement Plan

Updated: 2026-05-09

This document records the verified state of FinGPT `ML Forecast`, the priority closures already implemented, and the next professional hardening path. It is intentionally operational: every completion claim should remain traceable to code, tests, artifacts, or browser/API verification.

## 1. Verified State

- UI: `/ui/#ml-forecast`
- API: `/api/v1/forecast/*` and compatibility prefix `/api/forecast/*`
- Experiment artifacts: `data/forecast_lab/experiments`
- Data snapshot artifacts: `data/forecast_lab/data_snapshots`
- Model artifacts: `data/forecast_lab/model_artifacts`
- Macro regime artifacts: `data/forecast_lab/macro_regime`
- Model registry: SQLite `data/forecast_lab/model_registry.sqlite3`
- Validation default: walk-forward with purge window, embargo, and `shuffle=false`
- Execution policy: advisory-only, no broker/order execution

Latest local verification from this workstream:

- Forecast tests: `32 passed`
- Forecast + UI routing targeted tests: `55 passed`
- UI contract: passed, no missing markers
- `node --check app\web\app.js`: passed
- targeted `ruff check`: passed
- previous full gate: `python scripts\validation_gate.py` recorded `automated_passed=true`

## 2. Completed Priority Closures

### SQLite Registry and Audit

- Registry storage moved to SQLite.
- `model_registry` and `registry_audit` tables are created automatically.
- Legacy JSON registry migration remains available when the SQLite registry is empty.
- Promote/deprecate/upsert events are recorded in the audit table.

### Artifact Integrity and Promotion Policy

- Model artifacts use SHA-256 plus local HMAC integrity manifests.
- `/api/v1/forecast/model-registry/verify-artifact` verifies hash, byte size, and signature.
- Promotion checks artifact integrity, leakage status, data quality, confidence, OOS folds, turnover, and drift.
- Tampered artifacts are blocked from promotion with a controlled `409 Conflict`.

### Data Snapshot Governance

- Every successful or failed forecast run now gets a `data_snapshot_id`.
- Snapshot payload includes price coverage, benchmark coverage, macro coverage, feature schema hash, and `source_coverage_hash`.
- Snapshot artifacts are stored under `data/forecast_lab/data_snapshots/{data_snapshot_id}.json`.
- Experiment and model artifacts carry the same snapshot id/hash for reproducibility.

### Forecast Calibration

- Classification paths preserve raw and calibrated probability.
- OOS reliability-bin calibration is applied to direction-style targets.
- Residual conformal intervals are stored as `p10`, `p50`, `p90`, and `conformal_interval`.

### Purged Combinatorial CV Diagnostic

- `walk_forward_plus_purged_cv` is available as a validation option.
- Walk-forward remains the OOS forecast/backtest path.
- Purged combinatorial CV is recorded as an additional diagnostic in `training_result.purged_combinatorial_cv` and stability metrics.
- Unit tests verify purge/embargo exclusion around combinatorial test groups.

### Macro Regime Artifact

- Macro context is saved as a versioned regime artifact when macro features are enabled.
- Asset class, macro risk score, sensitivity score, and trend inputs are kept as structured context.
- Macro remains warning-only and does not automatically flip a signal.

### AI Provider Safety

- Deterministic interpretation remains the default.
- Provider-backed output must pass numeric grounding, advisory-only wording, and latency SLA checks.
- `FORECAST_AI_MAX_LATENCY_S` controls fail-closed fallback timing.
- Validation gate includes Forecast AI provider policy verification.

### Frontend Governance Visibility

- Dataset panel shows data snapshot id and source coverage hash.
- Experiment history shows data snapshot id.
- Model Registry panel shows artifact verify result and registry audit timeline.
- Promotion failures are rendered as structured, readable errors.

## 3. Current Security Posture

| Threat | Current Control | Status |
|---|---|---|
| Path traversal in experiment/model artifact ids | Safe id regex and resolved path containment | Controlled |
| Model artifact tampering | SHA-256, byte-size, HMAC signature verification | Controlled |
| Unsafe model promotion | Promotion eligibility policy and audit trail | Controlled |
| LLM numeric hallucination | Numeric grounding guard and deterministic fallback | Controlled |
| Direct trading instruction | Advisory-only schema and language guard | Controlled |
| Leakage/random split | Walk-forward default, purge, embargo, feature shift | Controlled |
| Stale runtime confusion | Build metadata and validation gate evidence | Improved |

## 4. Architecture Assessment

Backend status: good for a local research lab.

- Forecast logic is separated under `pipelines/forecast`.
- API transport is isolated in `app/api/routers/forecast.py`.
- Schemas are explicit in `core/schemas/forecast.py`.
- Optional dependencies fail closed as unavailable instead of crashing.
- Registry and artifact integrity are auditable.

Frontend status: good, but nearing static-JS scale limits.

- The ML Forecast tab follows the existing dashboard/card/table/chart conventions.
- The UI now exposes data snapshot, registry integrity, and registry audit state.
- If this surface grows further, the next step should be feature-module extraction from `app/web/app.js`.

Quant/ML status: research-lab usable.

- OOS forecast, signal generation, signal quality, and cost-aware backtest are implemented.
- Walk-forward remains the trusted trading-signal validation path.
- Purged CV is currently diagnostic, which avoids duplicated OOS predictions driving backtests.

## 5. Next Advancement Roadmap

### Phase A: Job Architecture

Goal: move long-running training away from synchronous request paths.

- Status: DONE 2026-05-11 for local workstation scope.
- Background forecast job queue
- Job status endpoint
- Cancellation and retry
- Progress/status polling
- Runtime budget controls per model family

Completion criteria:

- A slow LSTM/XGBoost run can be submitted through `/api/v1/forecast/jobs` without blocking the initiating request.
- Users can cancel, retry, list, and inspect jobs with structured status and errors.

### Phase B: Experiment Detail Drawer

Goal: make one experiment fully auditable from the UI.

- Status: DONE 2026-05-11 for the static `/ui/` surface.
- Experiment detail drawer
- Data snapshot panel
- Feature schema and target summary panel
- Leakage and validation audit panel
- Artifact integrity and registry audit panel

Completion criteria:

- A user can answer "what exact data/config/model produced this signal" without opening JSON files.

### Phase C: Calibration Reports

Goal: make forecast uncertainty more defensible.

- Horizon-specific calibration reports
- Reliability chart for classification targets
- Conformal interval coverage report
- Residual distribution by regime

Completion criteria:

- Probability and interval quality can be judged across folds and horizons.

### Phase D: Promotion Policy Presets

Goal: make model governance configurable but fail-closed.

- Target/horizon/model-family thresholds
- Required minimum folds and OOS rows
- Drift status policy
- Turnover and transaction-cost caps
- Manual override record, if multi-user governance is added

Completion criteria:

- Promotion decisions are reproducible and explainable.

### Phase E: Macro Regime v2

Goal: make macro context quantitative and calibratable.

- Rates, inflation, growth, liquidity, credit composite scores
- Asset-class sensitivity calibration
- Macro conflict score
- Regime-specific fold and signal metrics

Completion criteria:

- Macro conflict is a measured diagnostic rather than a generic warning.

### Phase F: Team-Grade Artifact Security

Goal: move from local integrity to deployable attestation.

- `FORECAST_ARTIFACT_SIGNING_KEY` rotation policy
- KMS-backed signing option
- Registry backup/export
- Integrity report export

Completion criteria:

- A promoted model artifact can be verified outside the developer machine.

### Phase G: Release Validation

Goal: make browser validation part of release readiness.

- Release-candidate browser UI gate enabled by default
- ML Forecast flow included in the browser gate
- Screenshot/console evidence stored in reports

Completion criteria:

- A release candidate cannot pass while the ML Forecast tab is broken or hidden.

## 6. Recommended Runbook

Minimal ML Forecast checks:

```powershell
python -m compileall -q pipelines\forecast app\api\routers\forecast.py core\schemas\forecast.py scripts\validation_gate.py
node --check app\web\app.js
python -m pytest tests\test_forecast_lab.py -q
python scripts\check_ui_contract.py
```

Deeper checks:

```powershell
python -m pytest .\tests -q
python -m ruff check scripts\validation_gate.py tests\test_validation_gate.py pipelines\forecast app\api\routers\forecast.py core\schemas\forecast.py tests\test_forecast_lab.py tests\test_ui_routing_contract.py
python scripts\validation_gate.py
```

Local UI check:

```powershell
$env:FINGPT_WEB_PORT=8130
powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1
```

Then open:

- `http://127.0.0.1:8130/ui/#ml-forecast`
- Preview Dataset
- Build Features
- Train / Forecast
- Inspect Data Snapshot
- Inspect Model Registry / Artifact Verify / Audit Timeline

## 7. Bottom Line

`ML Forecast` is now a verified research-lab implementation with data loading, data quality checks, feature/target generation, leakage controls, walk-forward OOS validation, calibrated forecasts, advisory signals, cost-aware backtests, diagnostic visualizations, guarded AI interpretation, signed artifacts, SQLite model registry, data snapshot governance, and registry audit visibility.

The next professional step is not adding more model names. The next step is operational maturity: background jobs, experiment drill-down, calibration reports, model governance presets, macro regime calibration, signing-key operations, and release-grade browser validation.
