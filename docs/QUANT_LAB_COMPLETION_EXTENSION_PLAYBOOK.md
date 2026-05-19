# Quant Lab Completion And Extension Playbook

> Date: 2026-05-05 KST
> Scope: final re-analysis and practical expansion plan for `QUANT_LAB_FINCEPT_COMPATIBILITY_DESIGN.md` and `QUANT_LAB_FUTURE_IMPROVEMENT_ANALYSIS.md`
> Status: compatibility contract complete; concrete hardening items implemented; remaining work is product-depth expansion.

## Final Completion Summary

The two source documents now describe an implemented FinGPT-native Quant Lab rather than a speculative plan.

Confirmed implementation boundaries:

- Canonical market data remains `data/research_mart.db`.
- Qdrant remains document evidence storage only.
- Quant metrics, signals, backtests, portfolio weights, and risk diagnostics are deterministic code outputs.
- LLM/research output is optional confirmation metadata and cannot directly compute trades or portfolio weights.
- Close-based signals execute at the next bar through explicit `signal_date` and `execution_date` separation.
- Qlib is not a startup dependency and is disabled unless explicitly enabled.

The latest hardening run added:

- Per-asset trade events.
- Rebalance snapshots.
- Explicit freshness policy diagnostics.
- Research-score provenance.
- Stronger portfolio risk diagnostics.
- Disabled-by-default Qlib adapter status route.

## Verified In This Run

- `python -m pytest tests/test_backtest_engine.py tests/test_portfolio_optimizer.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py -q`: `20 passed`.
- `python -m py_compile core/schemas/quant.py pipelines/backtest/validation.py pipelines/backtest/engine.py pipelines/orchestration/quant_lab_pipeline.py pipelines/signals/research_score.py pipelines/portfolio/optimizer.py pipelines/adapters/qlib_adapter.py app/api/routers/quant_lab.py core/config/settings.py`: passed.
- `python -m pytest tests -q`: `349 passed, 3 subtests passed`.
- `node --check app/web/app.js`: passed.
- `python scripts/check_ui_contract.py`: passed with zero missing UI markers.
- `python -m core.preflight`: all critical dependencies operational.
- `python scripts/browser_acceptance_matrix.py --browser-use-status blocked --browser-use-error "No Codex IAB backends were discovered" --output reports/browser_acceptance_latest.json`: generated separated browser evidence; Browser Use IAB remained blocked.
- `powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1`: automated validation passed.
- Fresh server on `http://127.0.0.1:8135`: health ok, Qlib status disabled, feature preview success, research-score signal generation success, Quant backtest success, bundle reload success, portfolio risk diagnostics success.

## Key Files Now Owning The Contract

Core schemas:

- `core/schemas/quant.py`
- `core/schemas/portfolio.py`

API:

- `app/api/server.py`
- `app/api/routers/quant_lab.py`
- `app/api/routers/backtest.py`
- `app/api/routers/portfolio.py`
- `app/api/routers/data.py`
- `app/api/routers/dashboard.py`

Quant engine:

- `pipelines/orchestration/quant_lab_pipeline.py`
- `pipelines/factors/catalog.py`
- `pipelines/factors/core.py`
- `pipelines/signals/base.py`
- `pipelines/signals/rule_based.py`
- `pipelines/signals/research_score.py`
- `pipelines/backtest/engine.py`
- `pipelines/backtest/validation.py`
- `pipelines/backtest/artifacts.py`
- `pipelines/portfolio/optimizer.py`

Strategy and adapters:

- `pipelines/strategies/registry.py`
- `pipelines/strategies/storage.py`
- `config/quant_strategies/defaults.yaml`
- `pipelines/adapters/qlib_adapter.py`

UI and validation:

- `app/web/index.html`
- `app/web/app.js`
- `app/web/styles.css`
- `scripts/check_ui_contract.py`
- `scripts/browser_acceptance_matrix.py`
- `quality_review.py`

## Verification Matrix

Fast targeted gate:

```powershell
python -m pytest tests/test_backtest_engine.py tests/test_portfolio_optimizer.py tests/test_quant_lab_pipeline.py tests/test_quant_lab_api.py -q
python -m py_compile core/schemas/quant.py pipelines/backtest/validation.py pipelines/backtest/engine.py pipelines/orchestration/quant_lab_pipeline.py pipelines/signals/research_score.py pipelines/portfolio/optimizer.py pipelines/adapters/qlib_adapter.py app/api/routers/quant_lab.py core/config/settings.py
```

Full deterministic gate:

```powershell
python -m pytest tests -q
node --check app/web/app.js
python scripts/check_ui_contract.py
python -m core.preflight
powershell -ExecutionPolicy Bypass -File scripts\verify_production_path.ps1
```

Browser evidence gate:

```powershell
python scripts/browser_acceptance_matrix.py `
  --browser-use-status blocked `
  --browser-use-error "No Codex IAB backends were discovered" `
  --output reports/browser_acceptance_latest.json
```

Runtime smoke:

```powershell
$env:FINGPT_WEB_PORT = "8135"
powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1
```

Then verify:

- `GET /api/v1/health`
- `GET /api/v1/data/health`
- `GET /api/v1/quant/config`
- `GET /api/v1/quant/qlib/status`
- `POST /api/v1/quant/features/preview`
- `POST /api/v1/quant/signals/generate`
- `POST /api/v1/quant/backtest`
- `GET /api/v1/quant/backtest/{run_id}/bundle`
- `POST /api/v1/quant/strategy/dry-run`
- `POST /api/v1/portfolio/optimize`

## Practical Expansion Point 1: Trade Attribution UI

Current backend state:

- `pipelines/backtest/engine.py` emits one trade event per asset weight change.
- Momentum ranking also emits rebalance snapshots.
- The Quant Lab artifact bundle exposes `trades` and `weights`.

Recommended UI work:

- Add a Rebalance Attribution table below Recent trades.
- Render:
  - signal date
  - execution date
  - ticker
  - previous weight
  - target weight
  - delta weight
  - price
  - cost
  - reason
  - selected or rejected status
- Add a filter for `enter`, `increase`, `decrease`, and `exit`.

Acceptance tests:

```powershell
node --check app/web/app.js
python scripts/check_ui_contract.py
python -m pytest tests/test_ui_routing_contract.py tests/test_quant_lab_api.py -q
```

Runtime acceptance:

- Run a momentum ranking backtest.
- Confirm each selected and rejected asset can be traced to the rebalance snapshot.
- Confirm no row has `signal_date >= execution_date`.

## Practical Expansion Point 2: Freshness Policy Strict Mode

Current backend state:

- Quant Lab diagnostics include `freshness_policy`, `asset_freshness`, `latest_price_dates`, `expected_latest_date`, and `market_calendar_lag_days`.
- Stale assets are visible in diagnostics and manifests.

Recommended next work:

- Add request flag `require_fresh_prices=true`.
- If enabled, return `status=partial` or `failed` when any ticker exceeds `max_market_calendar_lag_days`.
- Keep default behavior warning-first so local historical testing still works.

Files:

- `core/schemas/quant.py`
- `pipelines/backtest/validation.py`
- `pipelines/orchestration/quant_lab_pipeline.py`
- `tests/test_quant_lab_pipeline.py`
- `tests/test_quant_schema_contract.py`

Acceptance tests:

```powershell
python -m pytest tests/test_quant_lab_pipeline.py tests/test_quant_schema_contract.py -q
```

## Practical Expansion Point 3: Research Score Provenance UI

Current backend state:

- `signal_preview()` can load latest run history from `data/runs.db`.
- Research score status can be `disabled`, `fresh`, `expired`, `sparse_evidence`, `unavailable`, or `invalid`.
- Provenance includes run id, model, prompt/schema version, evidence IDs, as-of time, and expiry.

Recommended UI work:

- Add a Research Confirmation panel in Quant Lab Signal Matrix.
- Show status per ticker.
- Show evidence count and latest run id.
- Show whether research score affected ranking or only labels.

Risk rule:

- Favorable research score must never override missing factors, stale blocked data, or no-lookahead validation.

Acceptance tests:

```powershell
python -m pytest tests/test_signal_generation.py tests/test_quant_lab_pipeline.py -q
node --check app/web/app.js
python scripts/check_ui_contract.py
```

## Practical Expansion Point 4: Portfolio Risk Depth

Current backend state:

- Optimizer returns weights, risk contributions, portfolio metrics, correlation matrix, concentration HHI, effective number of positions, capped assets, and max-weight diagnostics.

Recommended next work:

- Add optional covariance shrinkage:
  - `covariance_method=sample`
  - `covariance_method=diagonal_shrinkage`
  - `shrinkage_alpha=0.1`
- Add benchmark-relative metrics:
  - beta to benchmark
  - tracking error
  - information ratio
  - benchmark excess return
- Render risk contribution bars beside weights.

Files:

- `core/schemas/portfolio.py`
- `pipelines/portfolio/optimizer.py`
- `app/api/routers/portfolio.py`
- `app/web/app.js`
- `tests/test_portfolio_optimizer.py`

Acceptance tests:

```powershell
python -m pytest tests/test_portfolio_optimizer.py tests/test_quant_lab_api.py -q
```

## Practical Expansion Point 5: Qlib Adapter Execution

Current backend state:

- `GET /api/v1/quant/qlib/status` returns `disabled` by default.
- Missing Qlib does not break startup.
- Data source policy is `data_mart_export_only`.

Only proceed if explicitly requested.

Required rules:

- Keep `QUANT_LAB_QLIB_ENABLED=false` by default.
- Do not import Qlib at module import time.
- Export data-mart slices into a temporary provider directory.
- Label all Qlib outputs as provider-specific.
- Do not use Qlib outputs in default `/api/v1/quant/backtest`.

Potential files:

- `pipelines/adapters/qlib_export.py`
- `pipelines/adapters/qlib_runner.py`
- `tests/test_qlib_adapter_disabled.py`
- `tests/test_qlib_adapter_export.py`

Acceptance tests:

```powershell
python -m pytest tests/test_quant_lab_api.py tests/test_qlib_adapter_disabled.py -q
python -m core.preflight
```

## Automation Operating Plan

For hourly or recurring automation, keep each run bounded:

1. Read `C:\Users\yygg1\.codex\automations\automation-2\memory.md`.
2. Check `git status --short`.
3. Run fast targeted tests first.
4. Implement one narrow product-depth increment.
5. Run the targeted tests again.
6. Run static UI checks if UI changed.
7. Update this playbook or the relevant source MD only with verified facts.
8. Update automation memory with exact commands and outcomes.

Do not repeat already completed compatibility work unless a regression appears.

## Remaining Limitations

- Browser Use IAB remains environment-blocked when the local backend reports `No Codex IAB backends were discovered`; fallback browser or static UI evidence must stay labeled as fallback.
- `quality_review.py --suite all` remains a long-running research-output quality gate, not a deterministic Quant Lab compatibility blocker.
- Qlib execution is intentionally unimplemented until explicitly requested.
- UI can surface the new trade attribution, freshness, and research-provenance fields more clearly.

## Decision

The compatibility design and immediately actionable future-improvement items are complete in the current environment. The next useful work is not another architecture rewrite; it is incremental product depth:

- richer UI surfacing of attribution/provenance,
- stricter opt-in data freshness enforcement,
- benchmark-relative portfolio risk,
- and optional provider adapters only behind explicit flags.
