# AI Portfolio Implementation Checklist

Status values used in this document: `TODO`, `IN_PROGRESS`, `DONE`, `PARTIAL`, `BLOCKED`, `NOT_DONE`.

This document was created before implementation and was used as the working source of truth for the AI Portfolio feature. Items are marked `DONE` only when implementation and verification evidence exists.

## Feature Summary

Status: `DONE`

AI Portfolio is implemented as a policy-based portfolio management workflow inside the existing FinGPT / Quant Lab local research assistant. It is not a chatbot that decides allocations. The implementation separates:

- Quant Engine: universe loading, price loading, deterministic weights, risk/performance metrics, backtest availability, data-quality warnings.
- Rule Engine: allocation range, cash minimum, max single asset, sector availability, drift, turnover, and missing/restricted asset checks.
- AI Layer: structured Korean explanations generated from quant/rule outputs only.
- UI: policy selection, generation workflow, recommendation review, performance, compliance, rebalancing, reports, and history.

Real broker order execution is not implemented.

## Structure Discovery

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| D1 | Inspect backend routing and app registration pattern | `app/api/server.py`, `app/api/routers/*` | New router follows FastAPI registration conventions and supports repo `/api/v1/*` prefix plus user-requested compatibility path. | Code inspection, route tests. | `Get-Content app\api\server.py`; pytest route tests | DONE | Router registered at `/api/v1/ai-portfolio` and `/api/ai-portfolio`. |
| D2 | Inspect frontend shell/tab pattern | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css` | Reuse existing static dashboard tab/cards/API style. | Code inspection, UI contract. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` | DONE | Actual UI is static HTML/CSS/JS, not React, so implementation uses existing dashboard sections instead of a new React page tree. |
| D3 | Inspect Quant Lab and portfolio services available for reuse | `pipelines/portfolio/optimizer.py`, `pipelines/data_mart/storage/repository.py`, `core/utils/symbol_registry.py` | Reuse existing optimizer, data mart prices, and symbol registry where practical. | Code inspection, API tests. | `python -m pytest tests\test_portfolio_optimizer.py tests\test_quant_lab_api.py -q` | DONE | Existing optimizer and data mart repository are reused; no duplicate market-data subsystem added. |
| D4 | Inspect test framework and supported validation commands | `tests/*`, `scripts/check_ui_contract.py` | Determine backend/frontend verification surface. | Code inspection and command execution. | `python -m pytest tests -q` | DONE | Repo uses pytest and static UI contract checks. No npm/package.json build was found. |

## Backend Data Model And Templates

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| B1 | Add AI Portfolio Pydantic models | `core/schemas/ai_portfolio.py` | Define InvestmentType, PortfolioPolicy, PortfolioRecommendation, PortfolioSnapshot, RebalanceSignal, PortfolioHistoryEvent, request/response schemas. | Import/compile and API response validation. | `python -m compileall -q core\schemas\ai_portfolio.py pipelines\ai_portfolio app\api\routers\ai_portfolio.py`; `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Includes statuses, automation levels, data-quality, constraints, weights, reports, and action requests. |
| B2 | Add investment type templates | `pipelines/ai_portfolio/templates.py` | Provide 10 required investment types with default ranges and quant/risk/rebalance defaults. | Template unit/API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Required IDs: conservative, moderate_conservative, balanced, balanced_growth, growth, aggressive, income, defensive, momentum, quant_balanced. |
| B3 | Add local persistence/store | `pipelines/ai_portfolio/store.py` | Persist policies, recommendations, snapshots, signals, reports, and history events in a durable local store. | API tests create/read/update records and verify SQLite persistence. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | SQLite-backed store at `AI_PORTFOLIO_DB_PATH` or `AI_PORTFOLIO_DATA_DIR/ai_portfolio.sqlite3`; legacy JSON collections are migrated once if present. |
| B4 | Document actual storage decision | `docs/AI_PORTFOLIO_IMPLEMENTATION_CHECKLIST.md`, `docs/AI_PORTFOLIO_OPERATIONAL_EXPANSION.md` | Document SQLite local store choice, legacy migration, current data locations, and remaining production storage boundary. | Manual doc review after implementation. | N/A | DONE | Local SQLite is now used instead of local JSON files. A separate remote multi-user DB migration remains future work, not a blocker for the local app. |
| B5 | Add normalized fundamentals data mart tables | `pipelines/data_mart/storage/schema.py`, `pipelines/data_mart/storage/repository.py` | Store provider fundamentals, valuation, financial snapshot, and asset metadata separately from prices. | Repository tests and data API tests. | `python -m pytest tests\test_fundamentals_card.py tests\test_ai_portfolio_api.py -q` | DONE | Added `asset_metadata`, `fundamentals_snapshots`, `valuation_metrics`, and `financial_statements` plus ticker/as-of indexes. |

## Deterministic Quant Engine And Rule Engine

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| Q1 | Add universe loading integration | `pipelines/ai_portfolio/engine.py`, `app/api/routers/ai_portfolio.py` | Load default, Quant Lab, S&P 500 top 200, ETF 100, Korea 300, crypto core, all-supported, and custom universes; expose preset metadata separately from direct input. | API tests, `/universes` smoke, UI contract. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Uses symbol registry, `GET /api/v1/ai-portfolio/universes`, `universe_source`, `universe_label`, and explicit `universe_not_found` warnings. |
| Q2 | Add price loading and return/risk calculations | `pipelines/ai_portfolio/engine.py`, `pipelines/data_mart/jobs/ensure_price_history.py` | Load data mart prices, automatically attempt missing-price hydration when enabled, compute returns and metrics where sufficient, and mark missing/insufficient data explicitly. | Synthetic data tests, missing data tests, hydration reporting test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Missing prices are no longer silently accepted; hydration result, still-unavailable tickers, and unavailable backtest state are all returned in `data_quality`. |
| Q3 | Add optimizer methods | `pipelines/ai_portfolio/engine.py` | Support equal/inverse/min-vol/risk-parity/max-sharpe/hybrid aliases with deterministic fallbacks. | Weight sum, policy range, and optimizer tests. | `python -m pytest tests\test_ai_portfolio_api.py tests\test_portfolio_optimizer.py -q` | DONE | Uses `pipelines.portfolio.optimizer.optimize_portfolio`; LLM never decides weights. |
| Q4 | Add policy constraint checker | `pipelines/ai_portfolio/rules.py`, `pipelines/ai_portfolio/engine.py` | Validate weight sum, allocation ranges, max single asset, sector when metadata exists, cash minimum, missing/restricted assets, drift, turnover. | Unit/API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | US heatmap sectors, ETF sector groups, cash/bond/alternative/KR categories, violations, and metadata coverage are returned in API and rendered by UI. |
| Q5 | Add backtest/performance snapshot calculation | `pipelines/ai_portfolio/engine.py`, `pipelines/ai_portfolio/service.py` | Generate backtest metrics only when sufficient common price history exists; otherwise mark unavailable. | API tests and live generate smoke. | Live POST `/api/v1/ai-portfolio/generate` | DONE | Live smoke returned `backtest_status=available`; missing data test returns unavailable state. |
| Q6 | Add rule-based rebalancing logic | `pipelines/ai_portfolio/rebalancing.py` | Generate signals from drift/cash/single-asset/turnover rules only; support approve/reject/defer. | Rebalance API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | No market-opinion or AI-only trigger. No broker execution. |
| Q7 | Keep generated default allocation policy-compliant when feasible | `pipelines/ai_portfolio/engine.py` | Adjust asset-class ranges and max single asset weight before returning recommendation. | Added regression test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | `default_multi_asset` + `balanced_growth` now returns constraint `pass` in tests and live smoke. |
| Q8 | Distinguish preset universe from direct input universe | `core/schemas/ai_portfolio.py`, `pipelines/ai_portfolio/engine.py`, `app/web/index.html`, `app/web/app.js` | UI and API clearly show whether the request uses a preset universe or a user-entered custom list. | API tests, UI contract, manual code review. | `python -m pytest tests\test_ai_portfolio_api.py tests\test_ui_routing_contract.py -q` | DONE | Direct input uses `custom:...`; preset selection disables the custom text box and reports that custom text is ignored. |

## AI Explanation Layer

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| A1 | Add prompt templates | `pipelines/ai_portfolio/prompts.py` | Add 5 templates: investment type, recommendation, performance report, rebalance explanation, constraint violation explanation. | Compile and API shape tests. | `python -m compileall -q pipelines\ai_portfolio` | DONE | Templates prohibit invented data and require practical Korean explanations. |
| A2 | Add deterministic explanation fallback | `pipelines/ai_portfolio/explainer.py` | Return Korean explanations from structured quant/rule outputs even when LLM is unavailable. | API tests require non-empty explanation. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Quant result remains valid if AI explanation provider is unavailable. |
| A3 | Separate quant results from AI explanation in API response | `core/schemas/ai_portfolio.py`, `pipelines/ai_portfolio/service.py` | Response keeps weights/risk/backtest/constraints separate from `ai_explanation`. | API tests and response inspection. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | LLM/explanation layer is not allowed to mutate weights or metrics. |

## Backend API

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| API1 | Register AI Portfolio router | `app/api/server.py`, `app/api/routers/ai_portfolio.py` | Expose endpoints under `/api/v1/ai-portfolio` and `/api/ai-portfolio`. | Route tests and live HTTP smoke. | HTTP smoke recorded in `reports/ai_portfolio_live_smoke.json` | DONE | Temporary live server returned 200 for health, UI, and investment types. |
| API2 | Implement investment type endpoints | `app/api/routers/ai_portfolio.py` | `GET investment-types`, `GET investment-types/{id}` return templates or 404. | API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | |
| API2a | Implement universe metadata endpoint | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/engine.py` | `GET universes` returns preset/direct-input source metadata, counts, sample assets, and request hints. | API tests and smoke output. | `python -m pytest tests\test_ai_portfolio_api.py -q`; `GET /api/v1/ai-portfolio/universes` | DONE | Prevents UI confusion between preset universes and direct user symbol input. |
| API3 | Implement policy CRUD and activate/deactivate | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/service.py` | Create/list/get/update/activate/deactivate policies and record history. | API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | |
| API4 | Implement generate endpoint | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/service.py` | Generate deterministic weights, metrics, constraints, explanation, warnings, data quality. | API tests and live POST smoke. | Live POST `/api/v1/ai-portfolio/generate` | DONE | Live smoke returned policy ID, recommendation ID, 6 weights, constraint `pass`, price data `true`, backtest `available`. |
| API5 | Implement recommendation endpoints | `app/api/routers/ai_portfolio.py` | List recommendations by policy and detail by recommendation ID. | API route coverage and service tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | |
| API6 | Implement performance endpoints | `app/api/routers/ai_portfolio.py` | List snapshots and create snapshot. | API route and service tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Snapshot is deterministic from latest recommendation/backtest where available. |
| API7 | Implement rebalancing endpoints | `app/api/routers/ai_portfolio.py` | Check rebalance, list signals, approve/reject/defer update status/history. | API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | User confirmation flow only. |
| API8 | Implement reports/history endpoints | `app/api/routers/ai_portfolio.py` | Generate report, list reports, list history events. | API tests and UI contract. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Reports are markdown text in local store. |
| API9 | Implement AI Portfolio store status endpoint | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/store.py` | Expose SQLite primary store status, collection counts, and legacy JSON seed-only policy. | API test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | `GET /api/v1/ai-portfolio/store/status`. |
| API10 | Implement normalized fundamentals endpoint | `app/api/routers/data.py` | Expose latest normalized fundamentals/valuation/financial provider snapshot by ticker. | API test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | `GET /api/v1/data/fundamentals/{ticker}`. |

## Frontend UI

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| UI1 | Add visible AI Portfolio tab | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css` | New `AI Portfolio` dashboard tab exists and can be addressed by `#ai-portfolio` / `?tab=ai-portfolio`. | Static UI contract and route tests. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json`; `python -m pytest tests\test_ui_routing_contract.py -q` | DONE | |
| UI2 | Add Overview section | `app/web/index.html`, `app/web/app.js` | Shows active/no-active portfolio, type, status, risk/rebalance state, updated/check times, quick actions. | UI contract. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` | DONE | Explicit no active portfolio state. |
| UI3 | Add Create Portfolio workflow | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css` | Investment type cards, preset universe selector, direct-input universe field, basic settings, advanced settings, generate button. | UI contract and JS syntax check. | `node --check app\web\app.js` | DONE | Implemented as a dense single-page workflow matching existing static UI architecture. Direct input is disabled unless `직접 입력` is selected. |
| UI4 | Add Recommendation panel | `app/web/index.html`, `app/web/app.js` | Allocation bars/table, risk/backtest metrics, constraint check, AI explanation. | UI contract. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` | DONE | Unavailable metrics are rendered as `unavailable` / `insufficient data`. |
| UI5 | Add Performance section | `app/web/index.html`, `app/web/app.js` | Shows return, benchmark, volatility, MDD, Sharpe, Sortino and equity curve when available. | UI contract and API data. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` | DONE | No fake metrics when backtest is unavailable. |
| UI6 | Add Policy Compliance section | `app/web/index.html`, `app/web/app.js` | Shows rule check, violations, missing data, data quality, universe source, price availability, hydration status, and metadata coverage. | UI contract. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` | DONE | Warnings and data activation status are visible in the AI Portfolio surface. |
| UI7 | Add Rebalancing Center | `app/web/index.html`, `app/web/app.js` | Current/target weights, drift signal, approve/reject/defer buttons. | UI contract and API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Buttons call backend action endpoints; no broker execution path. |
| UI8 | Add Reports and History | `app/web/index.html`, `app/web/app.js` | Generate weekly/monthly/rebalance reports and render event timeline. | UI contract and API route tests. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` | DONE | |
| UI9 | Add loading/error/insufficient data states | `app/web/app.js`, `app/web/styles.css` | API failures and insufficient data are explicit. | Static contract, backend missing-data test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | |
| UI10 | Add AI Portfolio operations status panel | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css` | Show SQLite store, legacy JSON seed policy, price rows, fundamentals snapshots, valuation metrics, and financial snapshot activation. | Static UI contract. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` | DONE | Includes manual refresh button. |

## Tests And Verification

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| T1 | Add backend tests for templates, policies, generate, constraints, rebalance, history, universe source, hydration, SQLite persistence, store status, and normalized fundamentals endpoint | `tests/test_ai_portfolio_api.py` | Cover required backend behavior, missing-data states, direct-input distinction, data activation reporting, non-mojibake Korean output, local SQLite persistence, store status, and fundamentals data API. | Pytest. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Latest targeted run: 18 passed. |
| T2 | Add/update frontend contract tests | `scripts/check_ui_contract.py`, `tests/test_ui_routing_contract.py` | Verify AI Portfolio tab, universe mode controls, operations panel, and key UI markers exist. | UI contract and pytest. | `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json`; `python -m pytest tests\test_ui_routing_contract.py -q` | DONE | Latest UI contract output has missing markers `[]` and includes operations/diff/hydration controls. |
| T3 | Run targeted API/UI/Quant tests | Tests and scripts | New feature and key Quant Lab surfaces pass. | Command output. | `python -m pytest tests\test_ai_portfolio_api.py tests\test_ui_routing_contract.py tests\test_portfolio_optimizer.py tests\test_quant_lab_api.py -q` | DONE | Latest targeted run: 54 passed. |
| T4 | Run full regression suite | Full pytest, compile, JS syntax, UI contract | Existing suite remains green. | Command output. | `python -m pytest tests -q`; `node --check app\web\app.js`; compileall | DONE | Latest full suite: 480 passed, 3 subtests passed. |
| T5 | Live server/API/UI smoke | Temporary local Uvicorn servers | New API responds and UI route is reachable; browser workflow can load the tab and operations workflow. | HTTP calls, Browser Use live UI check, and prior Playwright browser smoke. | HTTP smoke recorded in `reports/ai_portfolio_live_smoke.json`; Browser Use live check on `http://127.0.0.1:8002/ui/#ai-portfolio` | DONE | Browser Use confirmed hydrate/retry/snapshot buttons, policy/diff/operations surfaces, no console warnings/errors, and UI-triggered `snapshot_job` completed. |

## Acceptance Criteria Mapping

| # | Approval Criterion | Checklist IDs | Final Status | Notes |
|---|---|---|---|---|
| 1 | Visible AI Portfolio tab/page exists | UI1 | DONE | Verified by UI contract and route test. |
| 2 | User can select investment type | UI3, API2, B2 | DONE | Cards render from templates and update defaults. |
| 3 | Investment type loads default policy values | UI3, B2 | DONE | JS populates risk/rebalance/quant fields on selection. |
| 4 | User can edit quant options | UI3, B1 | DONE | Basic and advanced policy fields included. |
| 5 | System can generate/attempt portfolio from existing universe | Q1, API4, UI4 | DONE | Live generate smoke passed. |
| 6 | Missing data is not silently fabricated | Q1, Q2, Q5, UI9 | DONE | Missing price test asserts explicit unavailable state. |
| 7 | Generated allocation is visible | UI4, API4 | DONE | Allocation bars/table implemented. |
| 8 | Risk/performance metrics visible when possible | Q2, Q5, UI5 | DONE | Backtest metrics and curve render when available. |
| 9 | Missing metrics marked unavailable | Q5, UI5, UI9 | DONE | UI renders unavailable state. |
| 10 | Constraint compliance checked and shown | Q4, UI6 | DONE | Rule results and violations visible. |
| 11 | AI explanation uses structured quant result only | A1, A2, A3 | DONE | Explanation layer receives structured outputs; no weight mutation. |
| 12 | Rebalancing check exists | Q6, API7, UI7 | DONE | API and UI action implemented. |
| 13 | Signal includes trigger and changes | Q6, API7, UI7 | DONE | Test asserts `weight_drift` and recommended changes. |
| 14 | User can approve/reject/defer signal | API7, UI7 | DONE | API tests cover all three actions. |
| 15 | Major actions recorded in history | B3, API8, UI8 | DONE | Tests assert policy/recommendation events. |
| 16 | Tests or verification checks added | T1, T2 | DONE | Backend and UI contract tests added. |
| 17 | Checklist is created/updated | This file | DONE | Created before implementation and updated after verification. |
| 18 | No real broker order execution | API7, Q6 | DONE | Rebalance is manual/alert/paper only. |
| 19 | Quant, rule, AI, UI responsibilities separated | Q*, A*, UI* | DONE | Separate modules under `pipelines/ai_portfolio`. |
| 20 | Builds and existing Quant Lab not broken | T4, T5 | DONE | Full pytest passed; UI contract passed. |

## Changed Files

Status: `DONE`

- `app/api/server.py`: registered AI Portfolio router under `/api/v1/ai-portfolio` and `/api/ai-portfolio`.
- `app/api/routers/ai_portfolio.py`: new API router.
- `core/schemas/ai_portfolio.py`: schemas/models plus universe source, hydration, metadata coverage, and universe preset response fields.
- `pipelines/ai_portfolio/__init__.py`: new package marker.
- `pipelines/ai_portfolio/templates.py`: investment type templates.
- `pipelines/ai_portfolio/store.py`: SQLite persistence with legacy JSON migration.
- `pipelines/ai_portfolio/rules.py`: policy compliance checks.
- `pipelines/ai_portfolio/prompts.py`: AI prompt templates.
- `pipelines/ai_portfolio/explainer.py`: deterministic Korean explanation fallback.
- `pipelines/ai_portfolio/engine.py`: deterministic universe, data activation/hydration, metadata coverage, optimization, risk/backtest, data-quality logic.
- `pipelines/ai_portfolio/rebalancing.py`: rule-based rebalancing.
- `pipelines/ai_portfolio/service.py`: orchestration/service layer.
- `pipelines/data_mart/storage/schema.py`: normalized fundamentals, valuation, financial snapshot, and asset metadata tables.
- `pipelines/data_mart/storage/repository.py`: normalized fundamentals repository APIs and expanded health counts.
- `pipelines/data_mart/storage/db.py`: context-managed SQLite connections close cleanly after use.
- `pipelines/collect/fundamentals_card.py`: fundamentals collection persists normalized provider snapshots.
- `pipelines/data_mart/context/structured_context.py`: structured context can include latest fundamentals snapshot metrics.
- `app/api/routers/data.py`: normalized data health and fundamentals endpoint.
- `app/web/index.html`: AI Portfolio tab and sections, including separate preset universe selector and direct-input symbol list.
- `app/web/app.js`: AI Portfolio client state, universe source mode, API calls, renderers, actions.
- `app/web/styles.css`: AI Portfolio layout, direct-input disabled state, and data-quality states.
- `scripts/check_ui_contract.py`: UI markers for AI Portfolio.
- `tests/test_ui_routing_contract.py`: AI Portfolio route/static contract assertions.
- `tests/test_ai_portfolio_api.py`: backend/API tests.
- `tests/test_fundamentals_card.py`: normalized fundamentals persistence regression.
- `docs/AI_PORTFOLIO_IMPLEMENTATION_CHECKLIST.md`: this checklist.
- `docs/AI_PORTFOLIO_OPERATIONAL_EXPANSION.md`: current storage map and production operations roadmap.

## Added Backend Endpoints

Status: `DONE`

All endpoints are available under both `/api/v1/ai-portfolio` and `/api/ai-portfolio`.

- `GET /investment-types`
- `GET /investment-types/{investment_type_id}`
- `GET /universes`
- `GET /policies`
- `POST /policies`
- `GET /policies/{policy_id}`
- `PUT /policies/{policy_id}`
- `POST /policies/{policy_id}/activate`
- `POST /policies/{policy_id}/deactivate`
- `POST /generate`
- `GET /recommendations/{policy_id}`
- `GET /recommendations/{policy_id}/diff`
- `GET /recommendations/detail/{recommendation_id}`
- `GET /operations`
- `POST /operations/hydrate`
- `POST /operations/snapshots`
- `GET /performance/{policy_id}`
- `POST /performance/{policy_id}/snapshot`
- `POST /rebalance/check`
- `GET /rebalance/signals/{policy_id}`
- `POST /rebalance/{signal_id}/approve`
- `POST /rebalance/{signal_id}/reject`
- `POST /rebalance/{signal_id}/defer`
- `POST /reports/generate`
- `GET /reports/{policy_id}`
- `GET /history/{policy_id}`

Compatibility query aliases were also added for recommendations, reports, history, and signals where helpful for UI usage.

## Added Frontend Components / Sections

Status: `DONE`

The project uses static `app/web` sections rather than React components, so the actual implementation is:

- AI Portfolio dashboard tab.
- Overview / active portfolio card.
- Create Portfolio policy form.
- Investment type card grid.
- Advanced quant settings.
- Recommendation panel.
- Allocation chart/table.
- Risk and performance metrics panel.
- Policy compliance panel.
- Rebalancing center.
- Report panel.
- History timeline.
- Loading, warning, error, and insufficient-data states.

## Added Data Models

Status: `DONE`

- `InvestmentType`
- `PortfolioPolicy`
- `PortfolioRecommendation`
- `PortfolioSnapshot`
- `RebalanceSignal`
- `PortfolioHistoryEvent`
- `DataQuality`
- `UniversePreset`
- `ConstraintCheck`
- `PortfolioWeight`
- `RecommendedChange`
- Request/response models for policy, generate, rebalance, and reports.

## Added AI Prompt Templates

Status: `DONE`

- Investment type explanation.
- Portfolio recommendation explanation.
- Performance report.
- Rebalancing explanation.
- Constraint violation explanation.

## Added Or Reused Quant Engine Functions

Status: `DONE`

Added in `pipelines/ai_portfolio/engine.py`:

- `load_universe`
- `universe_presets`
- `load_price_data`
- `calculate_returns`
- `_price_hydration_result`
- `_metadata_coverage`
- `_optimize_core`
- `_template_fallback_weights`
- `_reserve_cash_weight`
- `_enforce_asset_class_ranges`
- `_enforce_max_weight`
- `run_backtest`
- `generate_recommendation`

Reused:

- `pipelines.portfolio.optimizer.optimize_portfolio`
- `pipelines.data_mart.storage.repository.get_prices`
- `core.utils.symbol_registry`

## Added Rebalancing Logic

Status: `DONE`

Added in `pipelines/ai_portfolio/rebalancing.py`:

- Drift-based rebalance check.
- Cash minimum violation check.
- Single asset limit violation check.
- Turnover warning.
- `manual`, `alert_only`, `confirm_before_apply`, `auto_paper_rebalance` policy levels.
- Approve/reject/defer status update through API.

No real broker order execution was added.

## Added Tests

Status: `DONE`

- `tests/test_ai_portfolio_api.py`
  - investment templates load
  - policy creation and overrides
  - invalid allocation range rejection
  - generate weights sum and history
  - preset universe metadata and direct-input distinction
  - SQLite store persistence
  - AI Portfolio store status endpoint and legacy JSON seed-only policy
  - normalized fundamentals data API endpoint
  - data quality fields for universe source, availability, metadata coverage, and hydration
  - default multi-asset policy compliance
  - constraint checker violations
  - missing price data explicit unavailable state
  - Korean output mojibake regression
  - rebalance trigger/no-trigger/action updates
- `tests/test_ui_routing_contract.py`
  - AI Portfolio tab/static markers
  - AI Portfolio hash/query tab routing
- `scripts/check_ui_contract.py`
  - AI Portfolio UI marker checks
  - AI Portfolio operations panel marker checks

## Executed Commands

Status: `DONE`

- `python -m pytest tests\test_ai_portfolio_api.py -q` -> latest `18 passed`
- `python -m pytest tests\test_fundamentals_card.py -q` -> `5 passed`
- `python -m pytest tests\test_fundamentals_card.py tests\test_structured_context.py -q` -> `7 passed`
- `python -m pytest tests\test_fundamentals_card.py tests\test_structured_context.py tests\test_ai_portfolio_api.py -q` -> `21 passed`
- `python -m pytest tests\test_ui_routing_contract.py -q` -> `17 passed`
- `python -m pytest tests\test_ai_portfolio_api.py tests\test_ui_routing_contract.py tests\test_portfolio_optimizer.py tests\test_quant_lab_api.py -q` -> latest `54 passed`
- `python -m pytest tests -q` -> latest `480 passed, 3 subtests passed`
- `node --check app\web\app.js` -> passed
- `python -m compileall -q pipelines\data_mart pipelines\collect pipelines\ai_portfolio app\api\routers\data.py app\api\routers\ai_portfolio.py` -> passed
- `python scripts\check_ui_contract.py --output reports\ai_portfolio_ui_contract.json` and `python scripts\check_ui_contract.py --output reports\ui_contract_ai_portfolio_ops_final.json` -> `status=passed`, `missing_markers=[]`
- `GET /api/v1/ai-portfolio/universes` via TestClient -> returned preset/direct-input metadata including `source_type`, counts, sample assets, and request hints
- Playwright universe-mode smoke -> `reports/ai_portfolio_universe_mode_smoke.json`, status `passed`; preset input disabled, custom input enabled only for direct input, no console errors
- HTTP live smoke -> `reports/ai_portfolio_live_smoke.json`, status `passed`, health 200, UI 200, 10 investment types, generate returned a recommendation with 6 weights.
- Playwright browser smoke -> `reports/ai_portfolio_browser_smoke.json`, status `passed`, AI Portfolio tab/generate/recommendation/compliance/rebalance/report checked, no console errors.
- Browser Use live UI check -> `http://127.0.0.1:8002/ui/#ai-portfolio`, operation buttons/surfaces visible, UI-triggered `snapshot_job` completed, no console warnings/errors.

## Known Limits

Status: `DONE`

- Local persistence is now SQLite with legacy JSON migration. A remote multi-user database migration is intentionally not implemented because this app remains a local single-user workflow in the current repo.
- AI explanations intentionally use deterministic structured Korean output by default. This is a grounding control, not a missing dependency: LLM prompt templates exist, but weights, metrics, and compliance output are never delegated to an LLM.
- Sector metadata coverage is now reported explicitly. US heatmap sectors, ETF groups, cash/bond/alternative classes, and broad KR market buckets are populated; any remaining metadata gap is visible through `data_quality.metadata_coverage`.
- Price data activation is attempted through `ensure_price_history` when `AI_PORTFOLIO_HYDRATE_MISSING` is enabled. Provider/network failures and still-unavailable assets are surfaced in `data_quality.hydration` and warnings instead of being hidden.
- Backtest/performance metrics still require common available price history. When the provider cannot supply enough history, the UI and API keep the allocation visible but mark performance metrics as `unavailable`.

## 2026-05-07 Operational Expansion Pass

Status: `DONE`

| Expansion Point | Implemented Change | Current Status | Remaining Production Step |
|---|---|---|---|
| Storage operationalization | Confirmed SQLite as primary store, exposed `/store/status`, documented legacy JSON as seed-only, and closed SQLite file handles at context exit. | DONE | PostgreSQL/Supabase migration remains a multi-user production step. |
| Data activation pipeline | Added normalized fundamentals persistence and exposed fundamentals availability in data health/UI operations. | DONE | Scheduler for daily price/fundamentals hydration remains future work. |
| Universe metadata | Added asset metadata table and fundamentals availability coverage into AI Portfolio metadata quality. | PARTIAL | Detailed Korean industry, ETF exposure, currency, active/delisted metadata should be normalized in dedicated tables. |
| Performance snapshots | Existing snapshot API remains available and documented. | PARTIAL | Daily active-policy snapshot scheduler remains future work. |
| Rebalancing operations | User-confirmed signal flow remains enforced; no broker execution. | PARTIAL | Add reason fields, expiry, next review, and stricter automation-level state transitions. |
| LLM explanation layer | Deterministic Korean explanation remains default; structured data only. | DONE | Optional LLM output should be schema-validated and blocked from unsupported numeric claims. |
| Audit logs | History events exist and operational roadmap now specifies request/config/universe/data hashes. | PARTIAL | Add request_id/config_hash/universe_hash to every persisted event. |
| UI expansion | Added operations status card for store/data activation. | DONE | Add active portfolio list, policy diff, recommendation diff, and missing-data retry workflow. |
| Validation | Added targeted tests for normalized fundamentals and store status. | DONE | Nightly hydration dry-run, SQLite integrity check, and Playwright core flow should become scheduled checks. |

## Future Work

Status: `NOT_DONE`

- Add remote relational storage only if this becomes multi-user or needs concurrent policy editing beyond local SQLite.
- Add scheduled snapshot collection and automatic alert generation.
- Add richer exchange/sector/industry metadata for Korean equities beyond broad KOSPI/KOSDAQ buckets.
- Add markdown export button for AI Portfolio reports if the existing export pattern is extended.
- Add optional LLM adapter call behind the deterministic explanation fallback, with strict schema-grounding and language enforcement.

## 2026-05-08 Follow-Up Operational Completion

Status: `DONE`

| ID | Checklist Item | Target Files | Expected Behavior | Verification Method | Commands | Final Status | Notes / Blocker |
|---|---|---|---|---|---|---|---|
| O1 | Persist operational audit fields | `core/schemas/ai_portfolio.py`, `pipelines/ai_portfolio/audit.py`, `pipelines/ai_portfolio/engine.py`, `pipelines/ai_portfolio/rebalancing.py`, `pipelines/ai_portfolio/service.py` | Policies, recommendations, snapshots, rebalance signals, reports, and key history events carry request/config/universe/data hashes or audit payloads. | API tests inspect recommendation and history audit values. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Remote trace collector not required for local runtime. |
| O2 | Add operations collection to SQLite store | `pipelines/ai_portfolio/store.py` | Data activation and snapshot jobs are stored in SQLite, not JSON. | Store status and operations API tests. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Legacy JSON remains seed-only. |
| O3 | Add manual data activation operation | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/service.py` | Manual hydrate endpoint can persist universe metadata, optionally hydrate prices/fundamentals, record result, and expose retry candidates. | API operation test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Network/provider failures remain explicit operation output, not fake success. |
| O4 | Normalize universe metadata tables | `pipelines/data_mart/storage/schema.py`, `pipelines/data_mart/storage/repository.py` | Persist identity, classification, ETF category exposure, Korean profile, and crypto profile rows. | API operation test checks table counts. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Detailed holdings/ISIN/CUSIP still requires external metadata provider. |
| O5 | Add snapshot job endpoint | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/service.py` | Create snapshots for a selected policy or active policies and store operation result. | API job test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | OS scheduler/CI cron is a deployment task, not a local code blocker. |
| O6 | Add recommendation diff endpoint | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/service.py` | Compare latest vs previous recommendation weights by policy. | API diff test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | |
| O7 | Expand rebalance action state | `core/schemas/ai_portfolio.py`, `pipelines/ai_portfolio/rebalancing.py`, `pipelines/ai_portfolio/service.py`, `app/api/routers/ai_portfolio.py` | Signals include expiry, next review, turnover, post-trade check; approve/reject/defer accepts reason/actor/deferred fields. | API action-body test. | `python -m pytest tests\test_ai_portfolio_api.py -q` | DONE | Still no broker execution. |
| O8 | Add operations UI | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css`, `scripts/check_ui_contract.py` | UI shows policy list, operation history, hydrate/retry buttons, snapshot job, and recommendation diff panel. | JS syntax and UI contract. | `node --check app\web\app.js`; `python scripts\check_ui_contract.py --output reports\ui_contract_ai_portfolio_ops.json` | DONE | |

Executed follow-up commands:

- `python -m compileall core\schemas\ai_portfolio.py pipelines\ai_portfolio app\api\routers\ai_portfolio.py pipelines\data_mart\storage\schema.py pipelines\data_mart\storage\repository.py` -> passed
- `python -m pytest tests\test_ai_portfolio_api.py -q` -> `18 passed`
- `node --check app\web\app.js` -> passed
- `python scripts\check_ui_contract.py --output reports\ui_contract_ai_portfolio_ops.json` -> `status=passed`, `missing_markers=[]`, 72 markers checked

Updated known limits after this pass:

- Remote PostgreSQL/Supabase migration remains `NOT_DONE` by design because this repository is currently configured for local SQLite and no remote deployment target was provided.
- Automated daily scheduling remains `NOT_DONE` as infrastructure wiring; manual hydrate and snapshot endpoints/UI are `DONE`.
- Provider-grade metadata enrichment for ETF holdings, ISIN/CUSIP, delisting state, and detailed Korean taxonomy remains `PARTIAL` because it needs licensed or external metadata sources.

## Sequential MD Re-Verification

Status: `DONE`

| Section | Verification Result | Final Status |
|---|---|---|
| Structure Discovery | Re-read against current backend/static UI structure; no React route assumption remains. | DONE |
| Backend Data Model And Templates | Rechecked schemas after adding `UniversePreset`, universe source fields, hydration, metadata coverage, SQLite persistence, and operational audit fields. | DONE |
| Deterministic Quant Engine And Rule Engine | Rechecked universe presets, custom universe separation, price hydration, optimizer, constraints, data quality warnings, and rebalance state metadata. | DONE |
| AI Explanation Layer | Rechecked deterministic Korean output and regression coverage against mojibake in API payloads. | DONE |
| Backend API | Rechecked route list and added `/universes`, `/operations`, `/operations/hydrate`, `/operations/snapshots`, and `/recommendations/{policy_id}/diff`. | DONE |
| Frontend UI | Rechecked AI Portfolio tab, preset/direct-input controls, data activation status, operations panel, recommendation diff, and UI contract markers. | DONE |
| Tests And Verification | Re-ran targeted, full, compile, JS syntax, static UI contract checks, and Browser Use live UI operations check. | DONE |
| Known Limits | Converted closed limits to implemented behavior and retained only explicit deployment/provider boundaries. | DONE |

## Improvement And Fix Closure

Status: `DONE`

| Issue / Improvement Point | Change Made | Verification |
|---|---|---|
| Direct input universe and preset universe were easy to confuse. | Renamed UI labels to distinguish `유니버스 프리셋` from `직접 입력 티커 목록`, disabled direct-input text unless `직접 입력` is selected, and returned `universe_source` / `universe_label` in API data quality. | `tests/test_ai_portfolio_api.py`, `tests/test_ui_routing_contract.py`, `scripts/check_ui_contract.py` |
| Data activation was only a passive price lookup. | Integrated `ensure_price_history` into AI Portfolio price loading and added explicit hydration status, attempted count, hydrated count, still-unavailable count, provider failure reporting, and manual hydrate/retry operations. | `test_price_hydration_attempt_is_reported`, operation API tests, full pytest |
| Local JSON persistence was a durability limitation. | Replaced collection files with SQLite-backed persistence, added an `operations` SQLite collection, and retained legacy JSON as seed-only migration input. | SQLite row-count assertions and store-status tests |
| Sector metadata was too implicit. | Added deterministic sector/class metadata from heatmap classifications, ETF groups, cash/bond/alternative/KR buckets, normalized identity/classification/profile tables, and metadata coverage output. | API generate tests, operation tests, compliance render |
| Korean output could regress into mojibake. | Added regression coverage that AI Portfolio template/explanation payloads do not contain mojibake markers. | `test_ai_portfolio_korean_text_is_not_mojibake` |
| UI did not expose whether data was available, hydrated, or unavailable. | Overview, compliance, and operations panels now show universe source, price availability ratio, hydration status, missing count, sector metadata coverage, policy list, recommendation diff, and operation history. | UI contract, JS syntax check, Browser Use live UI check |
| Rebalancing approval flow lacked operational detail. | Signals now include expiry, next review, turnover estimate, post-trade check, action reason, actor, defer-until, and audit payloads. | Rebalance action-body API test |
| Recommendation changes were hard to audit. | Added latest-vs-previous recommendation diff endpoint and UI panel. | Recommendation diff API test, UI contract |

## Final Completion Table

| Category | Count / Items | Status | Notes |
|---|---:|---|---|
| Completed checklist items | 61 | DONE | Discovery, backend, quant/rules, AI layer, API, UI, tests, storage, universe separation, data activation reporting, normalized fundamentals, audit fields, operations jobs, recommendation diff, and operations visibility. |
| Partially completed operational expansion items | 3 | PARTIAL | Provider-grade metadata depth, external scheduler/cron deployment, and remote multi-user database migration remain production/deployment expansion work. |
| Blocked items | 0 | DONE | No implementation blocker remains. |
| Not-done expansion items | 3 deployment/provider items | NOT_DONE | PostgreSQL/Supabase migration, OS/CI scheduler wiring, and licensed/provider-grade metadata enrichment are intentionally outside the local code implementation boundary. |
| Failed or skipped verification | 0 | DONE | Full pytest, JS syntax, compileall, UI contract, API smoke, Browser Use live UI operation check, and previous broader Playwright smoke artifacts passed. |
| Known limits | 3 | DONE | All are explicit deployment/provider boundaries, not hidden incomplete local implementation. |