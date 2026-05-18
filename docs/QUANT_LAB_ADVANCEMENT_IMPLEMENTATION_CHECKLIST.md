# Quant Lab Advancement Implementation Checklist

Scope: extend the existing FinGPT-native Quant Lab at `/ui/#quant-lab` without replacing the deterministic engine or adding a parallel quant stack.

## Implementation Items

| ID | Item | Files | Acceptance | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| QLA-1 | Reconfirm current Quant Lab baseline | `app/web/app.js`, `app/api/routers/quant_lab.py`, `pipelines/orchestration/quant_lab_pipeline.py` | Existing run history, replay, export, and strategy governance surfaces remain intact. | DONE | Baseline inspection found manifest lineage and replay helpers already present. |
| QLA-2 | Add run-context summary to the backtest result surface | `app/web/app.js` | Backtest results and reopened artifacts show strategy, universe, freshness, cost, lineage, and data snapshot context. | DONE | `data-testid="quant-run-context"` is rendered after opening a saved run or completing a backtest. |
| QLA-3 | Add two-run comparison backend | `pipelines/orchestration/quant_lab_pipeline.py`, `app/api/routers/quant_lab.py` | API compares two saved runs without mutating artifacts and returns metric deltas, config differences, diagnostics, and lineage. | DONE | Added `POST /api/v1/quant/backtests/compare` and read-only pipeline comparison. |
| QLA-4 | Add run-history compare workflow in the Quant Lab UI | `app/web/app.js`, `scripts/check_ui_contract.py`, `tests/test_ui_routing_contract.py` | Operator can select exactly two saved runs and render a comparison table from the UI. | DONE | Run history now has compare checkboxes, selection state, and comparison rendering. |
| QLA-5 | Add focused API/pipeline/UI contract tests | `tests/test_quant_lab_pipeline.py`, `tests/test_quant_lab_api.py`, `tests/test_ui_routing_contract.py` | Targeted Quant Lab tests pass. | DONE | `49 passed` for Quant Lab API, pipeline, and UI routing contract tests. |
| QLA-6 | Verify live UI on `127.0.0.1:8002` or a fresh local server | `scripts/quant_lab_ui_smoke.py` | Browser smoke or targeted Playwright check confirms no console errors and visible compare controls. | DONE | Full Quant Lab Playwright smoke passed on `8002` with run compare, cross-run cleanup preview, and `console_errors=[]`; targeted Playwright also rendered `quant_lab_run_compare_v1`. |

## Guardrails

- Do not make Qlib a default runtime dependency.
- Do not let an LLM decide portfolio weights or execution actions.
- Keep saved artifacts under `data/quant_lab/backtests/{run_id}`.
- Treat stale or partial data as visible decision context, not as silent success.
- Preserve the existing static `/ui/` architecture.
