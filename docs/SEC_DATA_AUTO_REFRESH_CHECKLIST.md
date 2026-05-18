# SEC Financials And Filing Auto Refresh Checklist

Status: `DONE`

Scope: collect SEC-backed financial facts and 10-K, 10-Q, 8-K filing metadata for the current AI Portfolio universe, persist them in the structured data mart, and keep them refreshable through manual operations plus an in-process scheduled refresh loop.

## Architecture Findings

| ID | Finding | Status | Notes |
|---|---|---|---|
| D1 | AI Portfolio universes are loaded through `pipelines.ai_portfolio.engine.load_universe`. | DONE | Use this as the source for current preset, active-policy, and direct-input universes. |
| D2 | Structured market data is stored in `data/research_mart.db`. | DONE | Reuse data mart schema/repository instead of adding another persistence layer. |
| D3 | Existing filings support only basic metadata. | DONE | Extend it with CIK, accession, report date, fiscal period, primary document, description, and raw SEC payload. |
| D4 | Existing fundamentals snapshots are provider snapshots, not audited SEC facts. | DONE | Add `sec_company_registry` and `sec_financial_facts`, then derive a normalized `sec_companyfacts` snapshot for common fields. |
| D5 | Existing scheduler is in-process and stdlib-only. | DONE | Follow the watchlist scheduler pattern for local workstation auto refresh. |

## Implementation Tasks

| ID | Task | Target Files | Status | Evidence |
|---|---|---|---|---|
| S1 | Add SEC company registry, detailed filing columns, and SEC fact storage. | `pipelines/data_mart/storage/schema.py`, `pipelines/data_mart/storage/db.py`, `pipelines/data_mart/storage/repository.py` | DONE | Targeted repository/schema tests passed. |
| S2 | Add SEC EDGAR provider for ticker map, submissions, and companyfacts. | `pipelines/data_mart/providers/sec_edgar_provider.py` | DONE | Live SEC smoke passed. |
| S3 | Add universe-level SEC update job with explicit skipped/failed statuses. | `pipelines/data_mart/jobs/update_sec_company_data.py` | DONE | `tests/test_sec_company_data.py` passed; live smoke recorded ok/skipped counts. |
| S4 | Add AI Portfolio operation endpoint for SEC refresh. | `core/schemas/ai_portfolio.py`, `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/service.py` | DONE | `POST /api/v1/ai-portfolio/operations/sec-refresh`; API test passed. |
| S5 | Add in-process auto refresh scheduler. | `core/config/settings.py`, `pipelines/data_mart/scheduler.py`, `app/api/server.py` | DONE | `/api/v1/data/auto-refresh/status` returned enabled with `all_supported`. |
| S6 | Expose SEC counts and latest data through the data API and AI Portfolio UI. | `app/api/routers/data.py`, `app/web/index.html`, `app/web/app.js`, `scripts/check_ui_contract.py` | DONE | UI contract passed; `/api/v1/data/sec/AAPL` returned 200/ok. |
| S7 | Add tests for schema/repository/job/API/scheduler-safe behavior. | `tests/` | DONE | 35 targeted tests passed. |
| S8 | Update operational docs and reconcile this checklist. | `docs/AI_PORTFOLIO_OPERATIONAL_EXPANSION.md`, this file | DONE | This checklist reconciled; operational doc updated. |

## Approval Criteria

| ID | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | Manual SEC refresh can collect 10-K, 10-Q, and 8-K metadata for SEC-covered US companies. | DONE | S&P 500 top 200 companies now have SEC data in the local mart. |
| A2 | SEC companyfacts are persisted as auditable facts with taxonomy, concept, unit, fiscal period, accession, filed date, and value. | DONE | `sec_financial_facts` reached 89,615 rows after live/automatic refresh. |
| A3 | A normalized latest SEC financial snapshot is available alongside existing provider snapshots without replacing raw facts. | DONE | `fundamentals_snapshots` and `financial_statements` include `sec_companyfacts` rows. |
| A4 | Non-SEC assets such as Korean equities, crypto, cash, or ETFs are skipped explicitly, not counted as failed companies. | DONE | Live smoke produced `ok: 2`, `skipped: 2` for AAPL/MSFT/SPY/005930.KS. |
| A5 | Auto refresh is configurable and starts with the FastAPI app without blocking startup. | DONE | Scheduler status endpoint showed `enabled=true`, `universe_id=all_supported`. |
| A6 | UI contract includes the SEC refresh control and SEC data counts. | DONE | `python scripts\check_ui_contract.py --output reports\sec_data_ui_contract.json` passed. |

## Validation Ladder

| Step | Command | Status | Result |
|---|---|---|---|
| V1 | `python -m compileall -q pipelines\data_mart pipelines\ai_portfolio app\api\routers core\schemas` | PASSED | No compile errors. |
| V2 | `python -m pytest tests\test_data_mart_schema.py tests\test_data_mart_repository.py tests\test_sec_company_data.py tests\test_data_mart_api.py tests\test_ai_portfolio_api.py -q` | PASSED | 35 passed. |
| V3 | `node --check app\web\app.js` | PASSED | No syntax errors. |
| V4 | `python scripts\check_ui_contract.py --output reports\sec_data_ui_contract.json` | PASSED | `missing_markers=[]`. |
| V5 | Live SEC smoke on a small universe, for example `custom:AAPL,MSFT,SPY,005930.KS`. | PASSED | `ok: 2`, `skipped: 2`, 1,031 inserted and 52 updated. |
| V6 | Live SEC seed on `sp500_top_200`, `max_assets=50`. | PASSED | 50 ok; 24,246 inserted and 2,469 updated. |
| V7 | `python -m pytest tests -q` | PASSED | 561 passed, 3 subtests passed. |
| V8 | Browser verification on `http://127.0.0.1:8136/ui/#ai-portfolio` | PASSED | SEC button and SEC company/fact/filing metrics visible; console warnings/errors were 0. |

## Live Seed Result

As of the validation run, local `data/research_mart.db` contained:

- `sec_company_registry`: 200
- `filings`: 7,768
- `sec_financial_facts`: 89,615
- `fundamentals_snapshots`: 206
- `financial_statements`: 206

The full automatic refresh is configured for `all_supported` with `max_assets=250`, a 24-hour interval, and a 120-second non-blocking startup delay. Pytest contexts now disable the scheduler unless `DATA_MART_AUTO_REFRESH_ENABLED` is explicitly set, so test runs do not silently call SEC.
