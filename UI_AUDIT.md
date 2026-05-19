# UI Audit: FinGPT Local Research Assistant

## Current Stack

- The UI is a static FastAPI-served surface under `app/web`.
- There is no separate React, Next, Vite, Streamlit, or Gradio frontend build step.
- Main frontend entrypoints:
  - `app/web/index.html`
  - `app/web/styles.css`
  - `app/web/app.js`
  - `app/web/modules/*.js`
- Primary routes:
  - `/ui/`
  - `/docs`
  - `/api/v1/health`
- Main dashboard tabs:
  - Market Dashboard
  - Macro
  - Quant Lab
  - ML Forecast
  - AI Portfolio

## Verified Strengths

- Static route and DOM contracts are covered by `scripts/check_ui_contract.py` and `tests/test_ui_routing_contract.py`.
- Core dashboard renderers are now split into domain modules for Market, Macro, Forecast, Quant, and AI Portfolio.
- The browser smoke validates script loading, module globals, dashboard tab surfaces, and representative non-destructive actions.
- The app has a local internal chart path, reducing reliance on external TradingView embeds for smoke validation.
- AI Portfolio dashboard loading now has a cache/deduplication guard to reduce duplicate request fan-out.

## Main Risks

- `app/web/app.js` is still large and mixes routing, event binding, API orchestration, and rendering glue.
- `app/web/styles.css` still contains accumulated override layers. The final layer is the active visual source of truth, but older broad selectors should be removed only after broader visual regression coverage.
- Static HTML contains many cross-domain controls. Removing or renaming DOM ids can break existing event bindings and contract tests.
- External TradingView embeds can emit third-party console warnings or WebSocket failures, so browser acceptance should prefer the internal chart path unless the external embed itself is under test.
- Some workflows call provider-backed endpoints and can be slow. Browser smoke should avoid long-running or state-changing actions unless they have bounded runtime and explicit status output.

## Validation Commands

- `node --check app\web\app.js`
- `Get-ChildItem app\web\modules\*.js | ForEach-Object { node --check $_.FullName }`
- `python scripts\check_ui_contract.py`
- `python scripts\ai_portfolio_ui_smoke.py --base-url http://127.0.0.1:8000 --timeout-s 180`
- `python -m pytest -q`

## Recommended Next Steps

1. Split event binding and API orchestration out of `app/web/app.js` by dashboard domain.
2. Add domain-specific module fixture tests as renderer payloads grow.
3. Expand browser smoke only for workflows with explicit success/failure states and bounded runtime.
4. Remove obsolete CSS override blocks after snapshot coverage across desktop, mobile, modals, and all dashboard tabs.
5. Keep cache-busting script query strings in `app/web/index.html` aligned with the tested bundle version.
