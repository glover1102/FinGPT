# Continuous Enhancement Log

## Current Project Summary
- Project purpose: Local financial research workstation that combines market data, macro data, quant/backtest workflows, Quantamental analysis, ML Forecast, AI Portfolio, and local LLM briefing surfaces.
- Main frontend structure: Static FastAPI-served UI under `app/web/index.html`, `app/web/app.js`, `app/web/styles.css`, plus domain modules under `app/web/modules/`.
- Main backend structure: FastAPI routers under `app/api/routers/`, shared request/response contracts under `core/schemas/`, and orchestration/services under `pipelines/`.
- Data flow: UI calls `/api/v1/*` routes; routers delegate to pipeline services; data-mart, macro, price, portfolio, forecast, and quantamental services normalize provider/cache output before rendering.
- AI/LLM flow: Primary research requests route through configured inference aliases such as `qwen`; experimental Gemma routes are exposed only from config when supported. Quantamental AI interprets deterministic engine payloads and must preserve deterministic scores/signals.
- Visualization flow: The static UI renders HTML/SVG/table surfaces, internal price charts, TradingView fallback/option widgets, heatmaps, Quant Lab charts, Forecast charts, Quantamental factor/score visualizations, and AI Portfolio dashboard surfaces.
- Testing flow: Python/pytest contract tests validate static UI markers, API contracts, quantamental behavior, and smoke scripts; browser smoke scripts cover the static `/ui/` surface when a local server is running.

## Current Problems
- Compatibility: The worktree already contains many unrelated pending changes, so this run must avoid broad rewrites and preserve existing static UI/API contracts.
- Data consistency: Period controls exist in several feature panels, but there is no single dashboard-level range selector that synchronizes the main KPI/chart/table/briefing inputs.
- UI consistency: `Core / Diagnostics / Operations / All` exists, but non-market tabs can still default to narrower persisted views, hiding important surfaces on first entry.
- Visualization: Chart/data surfaces expose range and freshness details unevenly; titles and status text are not always tied to the selected global period.
- AI briefing: Quantamental AI already has deterministic-signal guardrails, but the briefing context does not consistently carry a user-readable data snapshot summary.
- Data freshness: Detailed diagnostics exist, but a concise top-right quality summary is not always visible without opening the deeper quality panel.
- Translation quality: Korean/English UI output exists and should keep financial terms, tickers, dates, numbers, and units stable.
- Performance: Several dashboards can refetch independently; this run should keep global range updates explicit and avoid hidden background loops.
- Code structure: Existing static UI is large and stateful; improvements should add small adapter-style helpers instead of moving major surfaces.
- User experience: First-time dashboard entry should show all relevant sections, plus a simple quality/range context that reduces navigation friction.

## Enhancement Plan
- Priority 1: Make `All` the default dashboard panel view for all dashboard tabs while preserving Core/Diagnostics/Operations as filters.
- Priority 2: Add a top-right quality summary and dashboard-level range selector, then synchronize existing tab controls from the selected period where safely supported.
- Priority 3: Add Quantamental AI briefing data-snapshot guardrails and document verified model availability truthfully without fake Gemma/Qwen status.

## Validation Plan
- Build: No frontend package manifest is present in the repo root; validate with Python contract tests and import/runtime smoke instead of `npm run build`.
- Lint: No repo-level JS lint command is configured; use targeted static contract tests and UI contract script.
- Unit test: Run targeted pytest for UI routing/static contracts and Quantamental AI API behavior.
- Integration test: Run Quantamental API tests and local FastAPI UI smoke where available.
- UI test: Start the supported local web launcher and verify `/ui/` through the available browser/smoke tooling.
- Data quality test: Check that the quality summary renders from data-health, macro quality, and Quantamental quality payloads without exposing raw diagnostic failures.
- AI hallucination guard test: Verify Quantamental AI fallback/report includes source period, basis date/source, observation count or `Unavailable`/`확인 불가`, and preserves deterministic signal labels.

## Completion Checklist

### Compatibility
- [x] Existing features still work
- [x] Existing API contracts are not broken
- [x] Existing UI flow is preserved
- [x] No unauthorized strategy logic change
- [x] No secret or env file exposure

### Data
- [x] Date range selection works
- [x] KPI/chart/table use the same selected period
- [x] Data source and 기준일 are displayed
- [x] Missing data is handled
- [x] Data quality summary is visible at top-right
- [x] Cache/fresh data distinction is clear

### UI
- [x] Default view is All
- [x] Core/Diagnostics/Operations filters still exist
- [x] Font sizes are readable
- [x] Layout spacing is consistent
- [x] Cards/tables/charts are aligned
- [x] Mobile layout is acceptable
- [x] Loading state exists
- [x] Empty state exists
- [x] Error state exists

### Visualization
- [x] Chart titles are meaningful
- [x] Axis labels are readable
- [x] Tooltips are useful
- [x] Legends are not confusing
- [x] Period selection updates charts
- [x] No chart overflow or label collision

### AI Briefing
- [x] Gemma/Qwen availability is checked
- [x] Model selection is not fake
- [x] AI output includes used data period
- [x] AI output includes 기준일/source/observation count
- [x] AI does not invent unsupported numbers
- [x] Unverified facts are marked as 확인 불가
- [x] Translation preserves numbers/dates/units

### Validation
- [x] Lint executed or reason documented
- [x] Build executed or reason documented
- [x] Tests executed or reason documented
- [x] UI validation executed or reason documented
- [x] Data validation executed or reason documented
- [x] AI briefing validation executed or reason documented

### Documentation
- [x] docs/CONTINUOUS_ENHANCEMENT_LOG.md updated
- [x] README updated if needed
- [x] PR summary includes changed files
- [x] PR summary includes validation result

## Validation Results

| Check | Command / Tool | Result | Notes |
|---|---|---|---|
| Python syntax | `python -m py_compile pipelines/quantamental/ai_service.py app/api/routers/system.py` | Passed | Used `venv311` when available. |
| JS syntax | `node --check app/web/app.js` | Passed | Static JavaScript syntax only. |
| Static UI/API tests | `pytest tests/test_ui_routing_contract.py tests/test_quantamental_api.py -q` | Passed | `59 passed, 4 subtests passed`. |
| UI contract | `python scripts/check_ui_contract.py` | Passed | New global quality/range markers included. |
| Browser smoke | `python scripts/ai_portfolio_ui_smoke.py --timeout-s 120 --output reports/ai_portfolio_ui_smoke_continuous_20260519.json` | Passed | Versioned scripts, dashboard tab matrix, Quantamental language/top-5/score smoke, no console errors. |
| Live browser DOM | Playwright MCP at `http://host.docker.internal:8351/ui/?range=1Y#quantamental` | Passed | Quantamental tab rendered with `panelView=all`, global range visible, no horizontal overflow. |
| Mobile DOM | Playwright MCP resized to `390x900` | Passed | Top quality summary and range controls fit without horizontal overflow. |
| npm/pnpm build/lint/test | Not run | Excluded | Repo root has no `package.json`/`pnpm-lock.yaml`; this static UI is served by FastAPI and validated through Python/Playwright smoke. |

## 2026-05-19 Continuous Enhancement Run

- Branch: `automation/continuous-enhancement-20260519-0402`.
- Scope: preserved the current app structure and added only incremental dashboard/global-control and Quantamental AI-guardrail improvements.
- All default: dashboard panel defaults now reset to `All` for all tabs via a layout version key while keeping Core/Diagnostics/Operations filters.
- Quality summary: top-right `globalQualitySummary` shows status, 기준일, update time, and selected period; detailed source/observation/missing/AI snapshot fields are available in the tooltip and refreshed from data health, macro quality, market overview, and Quantamental analysis.
- Period selection: `dashboardRangeSelect` supports `1D`, `1W`, `1M`, `3M`, `6M`, `YTD`, `1Y`, `3Y`, `5Y`, `MAX`, and `custom`, writes URL query state, and synchronizes existing research, asset detail, backtest, portfolio, forecast, cross-asset, AI Portfolio, and Quantamental controls where those surfaces support the range.
- AI briefing: Quantamental AI context now includes `used_data`/`data_snapshot`; deterministic fallback and LLM outputs are forced to include used data, key changes, interpretation, scenarios, user actions, guardrails, and unavailable-value handling.
- Model selection: `/api/v1/config` now marks Qwen/Gemma routes as runtime-checked instead of implying local model availability without request-time verification.

## 2026-05-19 Continuous Enhancement Run 05:02

- Branch: `automation/continuous-enhancement-20260519-0502`.
- Current status: the previous run already added All-default panel behavior, a global range selector, and Quantamental AI used-data guardrails. This run kept that architecture intact and narrowed scope to the top-right quality summary UX.
- Problem found: the quality summary carried observation count, missing-data status, and AI snapshot time in tooltip/detail text, but the always-visible top-right badge only showed status, basis date, update time, and period.
- Change: the `globalQualitySummary` badge now directly renders `관측치`, `결측`, and `AI 기준` alongside quality status, 기준일, 업데이트, and 기간. Missing counts are normalized to user-readable labels such as `없음`, `있음`, or `n개`; long timestamps are compacted to avoid layout overflow.
- UI resilience: the badge now wraps predictably on desktop and 390px mobile, keeps an accessible Korean `aria-label`, and preserves the click-through quality panel behavior.
- Contract coverage: static UI contract checks now require the observation, missing-data, and AI-snapshot markers so future regressions do not hide these fields again.

### 05:02 Validation Results

| Check | Command / Tool | Result | Notes |
|---|---|---|---|
| JS syntax | `node --check app/web/app.js` | Passed | Static JavaScript syntax. |
| Python syntax | `python -m py_compile scripts/check_ui_contract.py` | Passed | Contract script remains importable. |
| UI contract | `python scripts/check_ui_contract.py` | Passed | New quality summary markers included. |
| UI routing tests | `python -m pytest tests/test_ui_routing_contract.py -q` | Passed | `39 passed, 4 subtests passed`. |
| UI module tests | `python -m pytest tests/test_ui_modules.py -q` | Passed | `2 passed`. |
| AI briefing guard regression | `python -m pytest tests/test_quantamental_api.py -q` | Passed | `20 passed`; used-data guard contract preserved. |
| Diff hygiene | `git diff --check -- app/web/index.html app/web/app.js app/web/styles.css tests/test_ui_routing_contract.py scripts/check_ui_contract.py` | Passed | No whitespace errors in touched files. |
| Live desktop UI | `playwright-cli` at `http://127.0.0.1:8352/ui/?range=1Y#quantamental` | Passed | Quality badge exposes all seven fields in the accessibility snapshot. |
| Live mobile UI | `playwright-cli resize 390 900` + DOM check | Passed | `horizontalOverflow=false`, `panelView=all`, quality fields remain visible. |
| npm/pnpm build/lint/test | Not run | Excluded | Repo root has no frontend package manifest; static UI is validated through Python contracts and Playwright. |
