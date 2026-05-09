# AI Portfolio Operational Expansion Notes

Status values: `DONE`, `PARTIAL`, `TODO`, `BLOCKED`.

This document records the current storage reality and the practical operations roadmap for AI Portfolio, Quant Lab, and the structured data mart.

## Verified Current Storage

Status: `DONE`

| Data Area | Current Store | Primary Write Path | Notes |
|---|---|---|---|
| Structured prices, macro, filings, news, provider status, data-quality checks | `data/research_mart.db` | SQLite | Canonical structured market data mart for the local workstation. |
| Normalized fundamentals, valuation, financial provider snapshots | `data/research_mart.db` | SQLite | Added in schema version 2 through `fundamentals_snapshots`, `valuation_metrics`, `financial_statements`, and `asset_metadata`. |
| AI Portfolio policies, recommendations, snapshots, rebalance signals, reports, history | `data/ai_portfolio/ai_portfolio.sqlite3` | SQLite | Current primary store. |
| AI Portfolio legacy JSON files | `history.json`, `policies.json`, `recommendations.json`, sibling collection files | Seed only | Read only when the matching SQLite collection is empty. Runtime writes go to SQLite. |
| Research run history | `data/runs.db`, `data/outputs/runs.db` | SQLite | Execution and output history; separate from AI Portfolio policy store. |
| Vector evidence | Qdrant collection | Qdrant | Document evidence retrieval remains separate from structured numeric data. |

## Implemented Operational Improvements

Status: `DONE`

| Area | Change | Target Files | Verification |
|---|---|---|---|
| Normalized fundamentals storage | Added `asset_metadata`, `fundamentals_snapshots`, `valuation_metrics`, and `financial_statements` tables plus ticker/as-of indexes. | `pipelines/data_mart/storage/schema.py` | `python -m pytest tests\test_fundamentals_card.py -q` |
| Repository API | Added `upsert_asset_metadata`, `upsert_fundamentals_card`, `latest_fundamentals`, and `fundamentals_availability`. | `pipelines/data_mart/storage/repository.py` | `python -m pytest tests\test_fundamentals_card.py tests\test_ai_portfolio_api.py -q` |
| Fundamentals collection path | `collect_fundamentals_card` now persists provider snapshots to SQLite by default and keeps retrieval-item conversion intact. | `pipelines/collect/fundamentals_card.py` | `python -m pytest tests\test_fundamentals_card.py -q` |
| Structured context grounding | Structured context now exposes latest fundamentals and metrics as numeric context when available. | `pipelines/data_mart/context/structured_context.py` | `python -m pytest tests\test_structured_context.py -q` |
| Data API | Added `GET /api/v1/data/fundamentals/{ticker}` and expanded health summary with fundamentals availability. | `app/api/routers/data.py` | `python -m pytest tests\test_ai_portfolio_api.py -q` |
| AI Portfolio store transparency | Added `GET /api/v1/ai-portfolio/store/status`, including SQLite primary store, collection counts, and legacy JSON seed policy. | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/store.py` | `python -m pytest tests\test_ai_portfolio_api.py -q` |
| UI operations surface | Added an AI Portfolio operations card for SQLite store, legacy JSON, prices, fundamentals, valuation, and financial snapshot activation. | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css` | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` |
| SQLite file-handle safety | Data mart and AI Portfolio SQLite connections now close at context-manager exit. | `pipelines/data_mart/storage/db.py`, `pipelines/ai_portfolio/store.py` | Windows cleanup regression in `tests/test_fundamentals_card.py` |

## Operating Model

Status: `PARTIAL`

The current design is appropriate for a local, single-user workstation:

- SQLite is the primary source of truth for structured local data and AI Portfolio state.
- Legacy JSON files remain only as one-time migration seeds.
- Price hydration is synchronous/on-demand through `ensure_price_history` and is reported in `data_quality.hydration`.
- Fundamentals are persisted as provider snapshots, not audited financial statements.
- Rebalancing remains user-confirmed or paper-only; no broker execution exists.

The next production step is not more UI text. It is operational scheduling, remote storage, stronger audit identifiers, and metadata normalization.

## Storage Operationalization Roadmap

Status: `TODO`

Recommended migration target: PostgreSQL or Supabase Postgres.

Minimum relational tables:

- `ai_portfolio_policies`
- `ai_portfolio_recommendations`
- `ai_portfolio_snapshots`
- `ai_portfolio_rebalance_signals`
- `ai_portfolio_reports`
- `ai_portfolio_history_events`
- `market_assets`
- `market_prices_daily`
- `market_fundamentals_snapshots`
- `market_valuation_metrics`
- `market_financial_statement_snapshots`
- `market_provider_status`
- `market_data_quality_checks`

Required indexes:

- `policy_id`
- `recommendation_id`
- `signal_id`
- `ticker`
- `as_of`
- `created_at`
- `updated_at`
- `status`
- `(ticker, date)`
- `(ticker, as_of DESC)`
- `(policy_id, created_at DESC)`
- `(collection, updated_at)` if JSON-style payload storage is retained during migration.

Migration constraints:

- Keep Qdrant as evidence/vector retrieval storage.
- Keep raw provider response retention separate from normalized tables.
- Do not move secrets or provider keys to the browser.
- Keep local SQLite export/import support for workstation reproducibility.

## Data Activation Pipeline

Status: `DONE`

Current behavior:

- AI Portfolio generation can call `ensure_price_history`.
- Hydration status is returned as explicit data quality.
- Still-missing tickers are not hidden.
- Fundamentals are collected through `collect_fundamentals_card` and can now be persisted to the data mart.
- `POST /api/v1/ai-portfolio/operations/hydrate` runs an explicit manual data activation operation.
- Operation results are persisted in the AI Portfolio SQLite `operations` collection.
- The UI exposes manual full hydration and current missing-data retry actions.

Next production job design:

1. Universe expansion job loads preset and active policy universes.
2. Price hydration job runs daily before market open, after close, and on manual demand.
3. Fundamentals hydration job runs less frequently, for example weekly or on explicit refresh.
4. Failed tickers are written to `provider_status` and exposed as retry candidates.
5. UI exposes retry buttons per provider category.
6. Each run stores `request_id`, `universe_hash`, `provider`, `row_count`, `failed_count`, `started_at`, and `finished_at`.

## Universe Metadata Normalization

Status: `PARTIAL`

Current behavior:

- Preset and direct-input universes are separated.
- Broad asset class, market, sector, ETF group, and Korean market bucket metadata are attached where deterministic metadata exists.
- Metadata coverage is surfaced in AI Portfolio data quality.

Next metadata tables:

- `asset_identity`: ticker, local symbol, ISIN, CUSIP, exchange, currency, active, delisted_at.
- `asset_classification`: asset_class, sector, industry, country, theme, ETF category.
- `etf_exposure`: ETF ticker, underlying asset class, sector exposure, country exposure, duration bucket.
- `kr_equity_profile`: Korean name, market, sector, industry, preferred/common stock flag.
- `crypto_profile`: symbol, chain/category, quote currency, provider mapping.

## Performance Snapshot Automation

Status: `PARTIAL`

Current behavior:

- Snapshot API exists.
- Snapshots can be created on demand.
- `POST /api/v1/ai-portfolio/operations/snapshots` runs a policy-specific or active-policy snapshot job.
- Snapshot job results are persisted in the AI Portfolio `operations` collection.

Next behavior:

- Active policies get daily NAV snapshots.
- Store portfolio value, period return, benchmark return, volatility, drawdown, drift, risk contribution, and data coverage.
- Snapshot job should run after price hydration succeeds.
- Missing prices should produce `insufficient_data`, not estimated NAV.

## Rebalancing Operations Policy

Status: `PARTIAL`

Current behavior:

- Rebalance signals are rule-based.
- User can approve, reject, or defer.
- No broker execution path exists.

Next state-machine expansion:

- `manual`: recommendation only.
- `alert_only`: signal can be created but never applied.
- `confirm_before_apply`: signal can become `approved` and then `applied_paper`.
- `auto_paper_rebalance`: signal can become `applied_paper` automatically only inside paper portfolio state.

Additional fields:

- `decision_reason`
- `expires_at`
- `next_review_at`
- `approved_by`
- `rejected_reason`
- `deferred_until`
- `turnover_estimate`
- `post_trade_policy_check`

## LLM Explanation Guardrails

Status: `PARTIAL`

Current behavior:

- Deterministic Korean explanation is the default.
- The LLM does not set weights, returns, drawdown, volatility, or compliance state.

Production guardrails:

- Only pass structured inputs: weights, risk metrics, backtest metrics, constraint check, data quality, and policy.
- Validate generated output against a schema.
- Reject output containing unsupported numeric claims.
- Enforce Korean output unless the user explicitly changes language.
- Log `prompt_template_id`, `input_hash`, `output_hash`, and `grounding_fields`.
- Keep deterministic fallback as the safe path when the LLM fails.

## Auditability And Observability

Status: `PARTIAL`

Current behavior:

- AI Portfolio history events exist.
- Provider status and data-quality checks exist in the data mart.

Next required fields:

- `request_id`
- `config_hash`
- `universe_hash`
- `price_data_coverage`
- `fundamentals_coverage`
- `data_snapshot_timestamp`
- `model_or_engine_version`
- `optimizer_method`
- `constraint_policy_hash`
- `latency_ms`
- `error_code`

Operational checks:

- SQLite integrity check.
- Data mart row-count deltas.
- Hydration dry-run.
- API contract snapshot.
- Playwright smoke for AI Portfolio create/generate/rebalance/report flow.

## UI Expansion Roadmap

Status: `PARTIAL`

Recommended next UI additions:

- Active portfolio list. `DONE`
- Policy comparison. `PARTIAL`
- Previous recommendation vs current recommendation diff. `DONE`
- Missing data retry panel. `DONE`
- Rebalance before/after comparison. `DONE`
- Price/fundamentals coverage heatmap.
- Snapshot timeline.
- Report export to markdown.
- Store status page with SQLite path, row counts, and migration warnings.

## 2026-05-08 Operational Closure Pass

Status: `DONE`

| Area | Implemented Now | Verification |
|---|---|---|
| Operational audit fields | Added `audit`, `request_id`, `config_hash`, `constraint_policy_hash`, `universe_hash`, data snapshot timestamps, and engine versions to policy/recommendation/snapshot/signal/report payloads and recommendation history events. | `python -m pytest tests\test_ai_portfolio_api.py -q` |
| AI Portfolio operations store | Added SQLite `operations` collection while keeping legacy JSON seed-only behavior. | `test_data_activation_persists_metadata_and_operations` |
| Manual data activation | Added `POST /operations/hydrate` with metadata persistence, optional price hydration, optional fundamentals hydration, dry-run support, and stored operation output. | `test_data_activation_persists_metadata_and_operations` |
| Universe metadata normalization | Added `asset_identity`, `asset_classification`, `etf_exposure`, `kr_equity_profile`, and `crypto_profile` tables plus repository upsert. | `test_data_activation_persists_metadata_and_operations` |
| Snapshot job | Added `POST /operations/snapshots` for active-policy or selected-policy snapshot creation. | `test_snapshot_job_and_recommendation_diff` |
| Recommendation diff | Added `GET /recommendations/{policy_id}/diff` and UI panel showing previous vs latest weight changes. | `test_snapshot_job_and_recommendation_diff`, UI contract |
| Rebalance state details | Added signal expiry, next review, turnover estimate, post-trade policy check, decision reason, actor, approval/reject/defer metadata, and action audit. | `test_rebalance_action_body_records_reason_actor_and_audit` |
| Operations UI | Added policy list, hydrate/retry buttons, snapshot job button, operations history, and recommendation diff surfaces. | `node --check app\web\app.js`; `python scripts\check_ui_contract.py --output reports\ui_contract_ai_portfolio_ops.json` |

## 2026-05-09 SEC Financials And Filing Refresh

Status: `DONE`

| Area | Change | Verification |
|---|---|---|
| SEC storage | Added `sec_company_registry` and `sec_financial_facts`, extended `filings`, and added additive SQLite migration guards for existing local DBs. | `tests/test_data_mart_schema.py`, `tests/test_data_mart_repository.py`, `tests/test_sec_company_data.py` |
| SEC provider | Added SEC EDGAR ticker-map, submissions, and companyfacts collection for 10-K, 10-Q, and 8-K. | Live SEC smoke and targeted tests |
| Universe operation | Added `POST /api/v1/ai-portfolio/operations/sec-refresh` so the current policy, selected universe, or direct ticker list can be refreshed on demand. | `test_sec_data_refresh_operation_records_result_without_network` |
| Automatic refresh | Added a stdlib in-process data mart scheduler that starts with FastAPI, waits a non-blocking startup delay, then refreshes the configured universe and Macro platform data on a 24-hour interval. | `/api/v1/data/auto-refresh/status`, `/api/v1/macro/refresh/status` |
| Data API/UI | Added `/api/v1/data/sec/{ticker}`, SEC rows to data health, and an AI Portfolio SEC refresh button. | `node --check app\web\app.js`; `python scripts\check_ui_contract.py --output reports\sec_data_ui_contract.json` |

Live seed performed during implementation:

- `custom:AAPL,MSFT,SPY,005930.KS`: 2 SEC-covered companies collected, 2 non-company assets skipped, 1,031 rows inserted and 52 updated.
- `sp500_top_200`, `max_assets=50`: 50 companies collected, 24,246 rows inserted and 2,469 updated.
- Final local data mart counts from `repository.data_health()`: `filings=7,768`, `sec_company_registry=200`, `sec_financial_facts=89,615`, `fundamentals_snapshots=206`, `financial_statements=206`.

Operational notes:

- The scheduler defaults to `DATA_MART_AUTO_REFRESH_ENABLED=true`, `DATA_MART_AUTO_REFRESH_SEC_ENABLED=true`, `DATA_MART_AUTO_REFRESH_MACRO_ENABLED=true`, `DATA_MART_AUTO_REFRESH_UNIVERSE_ID=all_supported`, `DATA_MART_AUTO_REFRESH_MAX_ASSETS=250`, `DATA_MART_AUTO_REFRESH_INTERVAL_HOURS=24`, and `DATA_MART_AUTO_REFRESH_INITIAL_DELAY_S=120`.
- Pytest contexts disable the scheduler unless `DATA_MART_AUTO_REFRESH_ENABLED` is explicitly set, so test runs do not silently call SEC.
- SEC fair-access behavior still depends on a valid `SEC_USER_AGENT`; replace the default contact string before sustained automated use.
- ETF, crypto, cash, and non-US exchange assets are recorded as skipped where SEC company 10-K/10-Q/8-K data is not applicable.

Remaining production-only work:

- Remote PostgreSQL/Supabase migration is still not implemented because the current app is a local single-user workstation and no remote DB credentials or deployment target were provided.
- OS/CI-level scheduled jobs are still not installed; local FastAPI now has an in-process scheduler for workstation use.
- Rich ETF holdings exposure, ISIN/CUSIP, delisting status, and detailed Korean sector taxonomy require provider-specific metadata sources beyond the current deterministic universe registry.

## Validation Runbook

Status: `DONE`

Current targeted validation commands:

```powershell
python -m compileall -q pipelines\data_mart pipelines\collect pipelines\ai_portfolio app\api\routers\data.py app\api\routers\ai_portfolio.py
node --check app\web\app.js
python -m pytest tests\test_fundamentals_card.py tests\test_structured_context.py tests\test_ai_portfolio_api.py -q
python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json
```

Recommended nightly expansion:

```powershell
python -m pytest tests -q
python scripts\check_ui_contract.py --output reports\nightly_ui_contract.json
python -m pipelines.data_mart.jobs.ensure_price_history --dry-run
```
