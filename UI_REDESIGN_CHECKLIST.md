# UI Redesign Checklist

## Layout

- [x] Preserve the existing static FastAPI UI architecture.
- [x] Preserve dashboard tab ids, form ids, and `data-testid` values.
- [x] Keep the research control surface and result surface visually distinct.
- [x] Keep AI Portfolio, Market, Macro, Quant Lab, and ML Forecast reachable from the main dashboard tabs.
- [x] Keep mobile and desktop layouts usable without horizontal page overflow.

## Visual System

- [x] Add a consistent final visual treatment layer in `app/web/styles.css`.
- [x] Keep button, input, card, table, and status styles consistent.
- [x] Preserve domain-specific colors for positive, negative, warning, and unavailable states.
- [x] Avoid decorative changes that hide controls or imply unsupported behavior.

## Functional Preservation

- [x] Do not change API route names or backend schemas for UI-only changes.
- [x] Do not remove existing event bindings.
- [x] Do not add fake metrics, fake sources, or non-working buttons.
- [x] Keep provider-backed and advisory-only states visible.
- [x] Keep local internal chart behavior available as a fail-open path.

## Modularization

- [x] Extract Market tape and signal renderers.
- [x] Extract Macro provider-health renderer.
- [x] Extract Forecast jobs renderer.
- [x] Extract Quant export-storage renderer.
- [x] Extract AI Portfolio dashboard metadata and operation-list renderers.
- [x] Remove duplicated renderer bodies from `app/web/app.js` after fixture coverage.

## Validation

- [x] JavaScript syntax check for `app/web/app.js`.
- [x] JavaScript syntax check for `app/web/modules/*.js`.
- [x] Static UI contract check.
- [x] Domain module fixture test.
- [x] Browser smoke for script loading, module globals, tab surfaces, and safe dashboard actions.
- [x] Full pytest suite.

## Deferred

- [ ] Split dashboard event binding and API orchestration by domain.
- [ ] Add deeper workflow smokes for bounded actions with explicit completion states.
- [ ] Remove obsolete CSS override blocks after visual regression coverage is broad enough.
