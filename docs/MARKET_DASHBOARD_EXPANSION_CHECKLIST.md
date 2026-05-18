# Market Dashboard Expansion Checklist

## Scope

Expand `/ui/#market-dashboard` from a static market panel into an advisory dashboard that combines market tape, cross-asset signals, freshness state, heatmap context, news, and data-health evidence. The implementation keeps the existing FastAPI plus static `app/web` architecture and does not add trading or execution actions.

## Ground Rules

- Preserve the existing FastAPI and static UI structure.
- Label stale or unavailable data explicitly and keep it out of decision-usable counts.
- Prefer observable market data and rules-based signals over LLM predictions.
- Keep provider, freshness, and cache metadata visible in the API/UI contract.
- Treat dashboard output as advisory-only.

## Checklist

| ID | Task | Files | Status | Verification |
| --- | --- | --- | --- | --- |
| MD1 | Inspect current Market Dashboard UI/API structure | `app/web/index.html`, `app/web/app.js`, `app/api/routers/dashboard.py` | DONE | Live UI/API inspection |
| MD2 | Add Market Overview API contract | `core/schemas/dashboard.py`, `app/api/routers/dashboard.py`, `tests/test_dashboard_api.py` | DONE | Targeted pytest |
| MD3 | Add market tape and cross-asset signal UI | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css` | DONE | Browser smoke |
| MD4 | Surface stale/freshness/data-health summaries | `app/web/app.js`, `app/web/styles.css` | DONE | UI contract + browser smoke |
| MD5 | Guard static routing and UI markers | `tests/test_ui_routing_contract.py`, `scripts/check_ui_contract.py` | DONE | UI routing tests + contract script |
| MD6 | Reconcile verification and residual risks | this file | DONE | Checklist updated |
| MD7 | Split market collection and overview assembly into service/cache layer | `pipelines/dashboard/market_service.py`, `app/api/routers/dashboard.py`, `tests/test_dashboard_api.py` | DONE | Targeted pytest + py_compile |
| MD8 | Persist shared market snapshot cache in data mart storage | `pipelines/data_mart/storage/schema.py`, `pipelines/data_mart/storage/repository.py`, `pipelines/dashboard/market_service.py`, `tests/test_dashboard_api.py` | DONE | Persisted-cache unit coverage |
| MD9 | Add DB-backed provider refresh lock to reduce concurrent cache-miss fanout | `pipelines/data_mart/storage/schema.py`, `pipelines/data_mart/storage/repository.py`, `pipelines/dashboard/market_service.py`, `tests/test_dashboard_api.py` | DONE | Refresh-lock unit coverage |

## Target Acceptance

- `GET /api/v1/dashboard/market/overview` returns market tape, signal cards, freshness summary, heatmap summary, and advisory-only metadata without breaking existing endpoints.
- `/ui/#market-dashboard` renders the new overview cards with loading, error, empty, and stale states.
- Existing Market, Macro, Quant Lab, ML Forecast, and AI Portfolio tab routing remains intact.
- Repeated market requests use memory cache first, then persisted SQLite snapshot cache, then provider refresh.
- Concurrent cache misses use a short-lived SQLite refresh lock so one owner refreshes while other callers wait for the persisted snapshot.
- Targeted tests and browser verification pass, or any environment blocker is explicitly recorded.

## Verification Log

- `python -m pytest tests/test_dashboard_api.py tests/test_ui_routing_contract.py -q` -> `28 passed` before MD8.
- `node --check app/web/app.js` -> passed before MD8.
- `python scripts/check_ui_contract.py --output reports/market_dashboard_ui_contract.json` -> `status=passed`, `missing_markers=[]`, `missing_js_markers=[]` before MD8.
- Browser smoke on `http://127.0.0.1:8002/ui/?verify=market-overview#market-dashboard` -> market tape 9 items, signal cards 4 items, heatmap tiles 96, market cards 9, console errors 0 before MD8.
- Live API `GET /api/v1/dashboard/market/overview` after UI heatmap load -> tape 9, signals 4, freshness `ok`, heatmap `partial`, heatmap usable 236, latest heatmap `2026-05-08T19:55:00+00:00` before MD8.
- Market service/cache follow-up: `python -m py_compile app/api/routers/dashboard.py pipelines/dashboard/market_service.py core/schemas/dashboard.py` -> passed before MD8; `GET /api/v1/dashboard/market` supports `force` and returns cache metadata.
- `python -m py_compile app/api/routers/dashboard.py pipelines/dashboard/market_service.py core/schemas/dashboard.py pipelines/data_mart/storage/repository.py pipelines/data_mart/storage/schema.py` -> passed after MD8.
- `python -m pytest tests/test_dashboard_api.py tests/test_ui_routing_contract.py -q` -> `29 passed` after MD8.
- `python -m pytest tests/test_fingpt_annotation_repository.py tests/test_dashboard_api.py tests/test_ui_routing_contract.py -q` -> `44 passed` after schema-version test update.
- `python -m pytest tests -q` -> `611 passed, 3 subtests passed`.
- `node --check app/web/app.js` -> passed after MD8.
- `python scripts/check_ui_contract.py --output reports/market_dashboard_ui_contract.json` -> `status=passed`, `missing_markers=[]`, `missing_js_markers=[]` after MD8.
- Live API on `http://127.0.0.1:8002`: `GET /api/v1/dashboard/market?force=true` -> `cache_hit=false`, `cache_layer=provider`, 9 items; next `GET /api/v1/dashboard/market` -> `cache_hit=true`, `cache_layer=memory`, 9 items.
- Browser smoke on `http://127.0.0.1:8002/ui/?verify=market-final#market-dashboard` -> market tape 9 items, signal items 4, heatmap tiles 96, market cards 9, visible errors 0, console errors 0.
- MD9 adds `dashboard_refresh_locks`, `SCHEMA_VERSION=6`, lock acquire/release helpers, and service-side wait-for-owner behavior.
- `python -m pytest tests/test_dashboard_api.py tests/test_fingpt_annotation_repository.py tests/test_ui_routing_contract.py -q` -> `47 passed` after MD9 and UI marker contract update.
- `python scripts/check_ui_contract.py --output reports/market_dashboard_ui_contract.json` -> `status=passed`, market overview meta/tape/signals markers included.
- Live API on `http://127.0.0.1:8002`: `GET /api/v1/dashboard/market?force=true` -> `cache_hit=false`, `cache_layer=provider`, `refresh_lock=acquired`, 9 items; next `GET /api/v1/dashboard/market` -> `cache_hit=true`, `cache_layer=memory`, 9 items.
- Browser smoke on `http://127.0.0.1:8002/ui/?verify=market-lock-final#market-dashboard` -> market tape 9 items, signal items 4, heatmap tiles 96, market cards 9, visible errors 0, console errors 0.
- `python -m pytest tests -q` -> `614 passed, 3 subtests passed`.

## Remaining Risks

- Heatmap summary is `not_loaded` until the heatmap endpoint has populated the in-process heatmap cache; the UI renders the tape immediately, then refreshes overview after heatmap/news/data-health calls settle.
- Market snapshot cache now has memory, persisted SQLite, and short-lived DB refresh-lock layers. If a provider call hangs beyond the lock TTL, another worker may take over after expiry; this is intentional fail-open behavior to avoid a permanently stuck dashboard.
