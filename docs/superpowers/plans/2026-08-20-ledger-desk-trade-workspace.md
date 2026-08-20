# Ledger Desk Trade Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish issue #77 by applying a light, dense Ledger Desk visual system across Paper Trading and moving Chart symbol into the Trade chart toolbar without changing business behavior.

**Architecture:** Preserve existing React page components, state ownership, API calls, URL filters, pagination, mutations, and order payloads. Centralize visual changes in `app/globals.css`, add only necessary semantic wrappers/classes, and keep chart symbol state in `TradePage` separate from `OrderForm` Symbol state.

**Tech Stack:** Next.js, React, TypeScript, CSS, Vitest, Testing Library, lightweight-charts.

## Global Constraints

- Keep account selection, form fields, order submission, API calls, filters, pagination, mutations, and URL semantics unchanged.
- Keep Chart symbol and OrderForm Symbol state independent.
- Use light neutral surfaces, dark ink, grey-green borders, success green, and error/risk red.
- Keep border radii at or below 8px and do not add nested decorative cards.
- Preserve reachable controls and horizontally scrollable tables on narrow layouts.
- Do not add browser-testing dependencies solely for this issue.
- Run frontend commands from `frontend/paper-trading`; use `uv run` for Python repository commands.

---

## Task 1: Establish Shared Ledger Desk Visuals

**Files:**
- Modify: `frontend/paper-trading/app/globals.css`
- Inspect if needed: `frontend/paper-trading/components/site-header.tsx`, `components/data-table.tsx`, `components/status-badge.tsx`, `components/error-banner.tsx`, `components/empty-state.tsx`

**Interfaces:** Existing class names remain the interface; pages keep their current props and data flow.

- [ ] Inventory selectors before editing:
  ```bash
  cd /data/frog
  rg -n 'className=|className:' frontend/paper-trading/features frontend/paper-trading/components
  ```
- [ ] Replace dark theme values in `globals.css` with light CSS tokens for surface, panel, ink, muted text, border, focus, success, and danger. Set `color-scheme: light`.
- [ ] Apply compact spacing, stable control heights, explicit `:focus-visible` styles, restrained panel/control/dialog/badge radii, and consistent table/filter/pagination states.
- [ ] Keep `.table-wrap` horizontally scrollable and make action/filter groups wrap at narrow breakpoints. Do not change JSX behavior.
- [ ] Verify obsolete constraints:
  ```bash
  cd /data/frog
  rg -n 'border-radius:\s*(?:9|1[0-9]|[2-9][0-9])px|color-scheme:\s*dark' frontend/paper-trading/app/globals.css
  ```
  Expected: no active shared UI matches.
- [ ] Run focused frontend tests after styling:
  ```bash
  cd /data/frog/frontend/paper-trading
  npm test -- --run
  ```
- [ ] Commit:
  ```bash
  git add frontend/paper-trading/app/globals.css frontend/paper-trading/components
  git commit -m "style: add Ledger Desk visual system"
  ```

## Task 2: Move Chart Symbol Into Trade Toolbar

**Files:**
- Modify: `frontend/paper-trading/features/trading/trade-page.tsx`
- Modify: `frontend/paper-trading/features/trading/price-chart.tsx`
- Modify: `frontend/paper-trading/features/trading/trade-page.test.tsx`
- Regression reference: `frontend/paper-trading/features/trading/order-form.test.tsx`

**Interfaces:** `TradePage` continues passing `symbol` to `PriceChart`; `OrderForm` continues owning its submitted Symbol value.

- [ ] Update the Trade test to assert that `Chart symbol` is inside the chart workspace toolbar, not a standalone panel, and that both symbol inputs retain independent values:
  ```tsx
  const chartSymbol = screen.getByLabelText("Chart symbol");
  const orderSymbol = screen.getByLabelText("Symbol");
  await user.type(chartSymbol, "600519.SH");
  await user.type(orderSymbol, "000001.SZ");
  expect(chartSymbol).toHaveValue("600519.SH");
  expect(orderSymbol).toHaveValue("000001.SZ");
  ```
- [ ] Run the focused test and confirm the structural assertion fails before implementation:
  ```bash
  cd /data/frog/frontend/paper-trading
  npm test -- --run features/trading/trade-page.test.tsx
  ```
- [ ] Remove the standalone Chart symbol panel from `trade-page.tsx`; place the existing labeled input inside a chart workspace toolbar and preserve its current state handler and attributes.
- [ ] Leave `OrderForm` symbol state and submission code unchanged. Ensure chart input changes cannot affect `createOrder` payloads.
- [ ] Update `price-chart.tsx` background, text, grid, and series colors for the light theme without changing data requests, cleanup, or symbol handling.
- [ ] Run regressions:
  ```bash
  npm test -- --run features/trading/trade-page.test.tsx features/trading/order-form.test.tsx
  ```
- [ ] Commit:
  ```bash
  git add frontend/paper-trading/features/trading
  git commit -m "feat: move chart symbol into trade toolbar"
  ```

## Task 3: Restyle Accounts and Analytics Presentation

**Files:**
- Modify only when necessary: `features/accounts/accounts-page.tsx`, `features/accounts/account-list.tsx`, account form/modal files, `features/analytics/analytics-page.tsx`, analytics summary/table/chart files.
- Tests: `features/accounts/accounts-page.test.tsx`, `features/analytics/analytics-page.test.tsx`.

**Interfaces:** Existing account and analytics request/mutation interfaces remain unchanged.

- [ ] Review current markup and add only semantic classes needed for page headers, action groups, metric grids, table sections, dialogs, and chart surfaces.
- [ ] Apply Task 1 classes to account lists, selected-account details, action groups, positions tables, dialogs, empty/error/success states, analytics metrics, tables, and unavailable-data messages.
- [ ] Update `asset-chart.tsx` colors if it assumes dark surfaces; retain all data, series, fallback, and loading logic.
- [ ] Ensure action groups wrap and metric grids collapse without clipping at narrow widths.
- [ ] Run:
  ```bash
  cd /data/frog/frontend/paper-trading
  npm test -- --run features/accounts/accounts-page.test.tsx features/analytics/analytics-page.test.tsx
  ```
- [ ] Commit:
  ```bash
  git add frontend/paper-trading/features/accounts frontend/paper-trading/features/analytics
  git commit -m "style: refine accounts and analytics workspace"
  ```

## Task 4: Restyle Orders and Trades Presentation

**Files:**
- Modify only when necessary: `features/history/orders-page.tsx`, `features/history/trades-page.tsx`, `features/trading/trading-tables.tsx`, `components/data-table.tsx`.
- Tests: `features/history/orders-page.test.tsx`, `features/history/trades-page.test.tsx`.

**Interfaces:** Existing date presets, URL synchronization, request parameters, pagination, stale-response protection, and mutation refreshes remain unchanged.

- [ ] Establish the behavior baseline:
  ```bash
  cd /data/frog/frontend/paper-trading
  npm test -- --run features/history/orders-page.test.tsx features/history/trades-page.test.tsx
  ```
- [ ] Add only semantic layout classes for account selectors, filter/date rows, table wrappers, action cells, and pagination groups. Retain `.table-wrap` for wide tables.
- [ ] Do not alter hooks, effects, query construction, validation, mutation callbacks, or rendered table data.
- [ ] Re-run the same history tests and confirm all endpoint/filter/pagination assertions pass.
- [ ] Commit:
  ```bash
  git add frontend/paper-trading/features/history frontend/paper-trading/features/trading/trading-tables.tsx frontend/paper-trading/components/data-table.tsx
  git commit -m "style: compact order and trade histories"
  ```

## Task 5: Responsive and Tooling Verification

**Files:** No source changes required unless visual inspection reveals an issue in a touched file.

- [ ] Discover available tooling:
  ```bash
  cd /data/frog
  rg --files frontend tools scripts .github | rg 'playwright|screenshot|visual|detector|ui'
  cd frontend/paper-trading
  npm ls @playwright/test playwright
  ```
- [ ] If supported screenshot/UI-detector tooling exists, inspect `/accounts`, `/trade`, `/orders`, `/trades`, and `/analytics` at approximately `1440x900`, `768x900`, and `390x844`. Confirm chart toolbar placement, predictable Trade stacking, reachable controls, table scrolling, filter/pagination wrapping, dialogs, focus states, and restrained colors/radii. Batch-fix findings and repeat the visual round.
- [ ] If tooling is unavailable, record that gap and perform static responsive inspection of CSS breakpoints and changed markup. Do not add a new browser dependency solely for this issue.

## Task 6: Simplify Review and Final Gates

**Files:** All files touched by Tasks 1-4.

- [ ] Invoke the `simplify` skill after behavior is understood and focused tests pass. Review only for unnecessary state/props/wrappers, duplicated styles, decorative markup, or behavior-preserving CSS consolidation. Apply only issue-scoped simplifications.
- [ ] Run final frontend gates:
  ```bash
  cd /data/frog/frontend/paper-trading
  npm run lint
  npm test
  npm run build
  ```
- [ ] Run repository hooks:
  ```bash
  cd /data/frog
  uv run pre-commit run --all-files
  ```
- [ ] Re-run affected tests and final lint/build after any simplification.
- [ ] Inspect status and stage only intended frontend files; exclude existing `PRODUCT.md`, `backups/`, and `data/`:
  ```bash
  git status --short
  git add frontend/paper-trading
  git commit -m "feat: finish Ledger Desk trade workspace"
  ```

## Acceptance Checklist

- [ ] Standalone Chart symbol panel removed; input is in chart toolbar.
- [ ] Chart symbol and order-form Symbol remain independent; order payload uses order-form Symbol.
- [ ] Accounts, Orders, Trades, Analytics, and Trade share the light dense visual system.
- [ ] Desktop and narrow layouts preserve reachable controls, table scrolling, and pagination.
- [ ] Changed UI has no radius above 8px or nested decorative cards.
- [ ] Screenshot/UI-detector availability and result are reported.
- [ ] Frontend lint, tests, production build, and applicable repository hooks pass.
