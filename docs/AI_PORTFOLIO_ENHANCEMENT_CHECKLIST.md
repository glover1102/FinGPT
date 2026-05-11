# AI Portfolio Enhancement Checklist

Status values used in this document: `TODO`, `IN_PROGRESS`, `DONE`, `PARTIAL`, `BLOCKED`, `NOT_DONE`.

This checklist tracks the first enhancement pass for the existing AI Portfolio tab. The scope is local workstation operations only. Remote PostgreSQL or Supabase migration, broker order execution, and autonomous real-money rebalancing remain out of scope unless explicitly re-enabled.

## Scope

Status: `DONE`

First-pass target:

- Add a backend dashboard surface for AI Portfolio operations.
- Expose selected policy, operation summaries, data coverage, and snapshot timeline in one API response.
- Render coverage heatmap and snapshot timeline inside the static `/ui/#ai-portfolio` page.
- Preserve advisory-only behavior and explicit `unavailable` / `partial` states.
- Add API, UI contract, and syntax verification.

## Implementation Checklist

| ID | Area | Target Files | Expected Behavior | Verification | Status | Notes |
|---|---|---|---|---|---|---|
| E1 | Architecture reconfirmation | `app/api/routers/ai_portfolio.py`, `pipelines/ai_portfolio/service.py`, `core/schemas/ai_portfolio.py`, `app/web/*` | Reuse existing FastAPI router, service layer, Pydantic schemas, SQLite store, and static UI. | Code inspection | DONE | Current stack is static HTML/JS plus FastAPI, not React. |
| E2 | Dashboard schemas | `core/schemas/ai_portfolio.py` | Typed response models describe policy summary, coverage rows, snapshot timeline, operation summary, and dashboard response. | `compileall`, API pytest | DONE | Added compact dashboard response models. |
| E3 | Dashboard service/API | `pipelines/ai_portfolio/service.py`, `app/api/routers/ai_portfolio.py` | `GET /api/v1/ai-portfolio/dashboard` returns selected policy, counts, coverage rows, recent operations, and timeline without huge provider payloads. | API test, live API smoke | DONE | Recent operations are compacted and omit raw `details_json`. |
| E4 | Static UI surfaces | `app/web/index.html`, `app/web/app.js`, `app/web/styles.css` | AI Portfolio operations card shows coverage heatmap and snapshot timeline with loading, empty, partial, and ok states. | UI contract, `node --check`, browser smoke | DONE | Snapshot/data operations invalidate and reload dashboard state. |
| E5 | Tests/contracts | `tests/test_ai_portfolio_api.py`, `tests/test_ui_routing_contract.py`, `scripts/check_ui_contract.py` | API and static contract assert the new dashboard endpoint and UI markers. | Targeted tests, full pytest | DONE | Full `tests` suite passed after the change. |
| E6 | Documentation reconciliation | `docs/AI_PORTFOLIO_OPERATIONAL_EXPANSION.md`, this file | Roadmap reflects the newly completed first-pass dashboard enhancement and remaining production work. | Manual reread | DONE | 2026-05-11 operational dashboard section added. |

## Validation Ladder

Status: `DONE`

- `python -m compileall -q core/schemas/ai_portfolio.py pipelines/ai_portfolio app/api/routers/ai_portfolio.py` - passed.
- `node --check app/web/app.js` - passed.
- `python -m pytest tests/test_ai_portfolio_api.py -q` - `20 passed`.
- `python -m pytest tests/test_ui_routing_contract.py -q` - `23 passed`.
- `python scripts/check_ui_contract.py --output reports/ai_portfolio_enhancement_ui_contract.json` - passed with no missing markers.
- `python -m ruff check core\schemas\ai_portfolio.py pipelines\ai_portfolio\service.py app\api\routers\ai_portfolio.py tests\test_ai_portfolio_api.py tests\test_ui_routing_contract.py scripts\check_ui_contract.py` - passed.
- `python -m pytest tests -q` - `610 passed, 3 subtests passed`.
- Live HTTP smoke for `/api/v1/ai-portfolio/dashboard?limit=5` on port `8142` - `status=success`, timeline present, compact operations omit `details_json`.
- Browser smoke for `http://127.0.0.1:8142/ui/#ai-portfolio` - coverage heatmap and snapshot timeline rendered with no fetch error.

## Acceptance Criteria

Status: `DONE`

- DONE - Dashboard endpoint is available under the existing AI Portfolio router.
- DONE - Response does not embed massive provider `details_json` payloads.
- DONE - UI shows data coverage as an operational heatmap instead of only text.
- DONE - UI shows recent snapshots as a timeline and marks missing snapshots explicitly.
- DONE - Snapshot and data operation buttons refresh the new dashboard state.
- DONE - Tests, contract checks, live HTTP smoke, and browser smoke pass.
