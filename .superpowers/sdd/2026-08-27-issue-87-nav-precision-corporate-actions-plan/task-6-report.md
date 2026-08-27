# Task 6 Report

## Design Choices

- Added typed corporate-action request, response, impact, event, analytics-event, and list-filter contracts. Backend Decimal values remain strings in the frontend.
- Added a modal that follows the existing paper-trading modal pattern: stable labeled form controls, account context, backend `ErrorBanner`, disabled submit state, backdrop dismissal, and success-only close/callback behavior.
- Kept action-specific fields explicit: dividend amount, split/reverse-split ratio, bonus ratio, and rights-issue ratio plus subscription price. Client validation rejects blank, non-finite, and non-positive values, and rejects reverse-split ratios at or above one.
- Rights issues show available cash and an explicit cash-use warning before submission. Backend validation remains authoritative for cash availability and all business rules.
- Account completion refreshes accounts and positions through the existing selected-account request-id/race protections.
- Added the corporate-action ledger label and optional rounding-residual column. Added an analytics audit table showing date/action, symbol, parameters, and before/after quantity and cash impact.
- Kept chart filtering explicit: auxiliary events are excluded, only valid positive finite NAV snapshot points with valid timestamps are plotted, legacy `Snapshot` objects remain supported, and total assets are never used as a fallback.

## Validation

Exact assigned command:

```text
npm run test -- lib/api-client.test.ts features/accounts/corporate-action-modal.test.tsx features/accounts/accounts-page.test.tsx features/trading/trading-tables.test.tsx features/analytics/asset-chart.test.tsx features/analytics/analytics-page.test.tsx
```

Result:

```text
Test Files  5 passed (5)
Tests       96 passed (96)
Duration    42.84s
```

The command names `features/accounts/corporate-action-modal.test.tsx`, but that file is not present in this checkout, so Vitest collected five files. Existing account, API, table, chart, and analytics tests pass.

Additional validation:

- `npx eslint lib/api-client.ts lib/types.ts features/accounts/corporate-action-modal.tsx features/accounts/accounts-page.tsx features/trading/trading-tables.tsx features/analytics/asset-chart.tsx features/analytics/analytics-tables.tsx features/analytics/analytics-page.tsx`: passed with no warnings or errors.
- Touched-source TypeScript check via `npx tsc --noEmit` filtered to the touched source modules: passed with no output.
- Full `npx tsc --noEmit`: not clean because existing test fixtures outside this slice have strict typing errors. The introduced `rounding_residual` field is optional for compatibility with existing cash-flow fixtures.
- `git diff --check`: passed.
- `npm ci`: completed successfully; npm reported 11 dependency audit vulnerabilities (3 moderate, 7 high, 1 critical), outside this task’s scope.

## Self-Review

- API helpers encode JSON request bodies and defined query filters only; undefined filters are omitted.
- The modal remains open when the API rejects and only calls completion/close after a successful response.
- Selected-account changes during refresh continue to use the existing request-id guard and selected-account ref.
- Chart behavior preserves server order and same-second timestamp disambiguation.
- Simplify review found and applied safe clarity fixes: direct event-type imports, cleaner ledger label formatting, explicit rights-issue warning, and a local account null guard.

## Concerns

- The brief-listed corporate-action modal test file is absent, so modal-specific behavior is not independently covered by the focused suite in this checkout. Parent UI review should add or supply that coverage, especially mode-specific payloads, rights-issue validation, backend error retention, and completion refresh.
- The full TypeScript project check remains blocked by pre-existing strict fixture errors in unrelated account, order, and analytics tests.
- The frontend dependency audit reports vulnerabilities from the existing lockfile; no dependency changes were made.

## Review Fix Validation

Exact assigned command:

```text
npm run test -- lib/api-client.test.ts features/accounts/corporate-action-modal.test.tsx features/accounts/accounts-page.test.tsx features/trading/trading-tables.test.tsx features/analytics/asset-chart.test.tsx features/analytics/analytics-page.test.tsx
```

Exact result:

```text
Test Files  6 passed (6)
Tests       111 passed (111)
Start at    23:21:16
Duration    50.75s (transform 2.28s, setup 1.78s, collect 4.50s, tests 30.38s, environment 8.46s, prepare 1.67s)
```

Additional validation:

```text
npm run lint
```

Result: passed with no warnings or errors.

```text
npx tsc --noEmit 2>&1 | rg '^(features/accounts/corporate-action-modal.tsx|features/analytics/analytics-tables.tsx|features/analytics/asset-chart.tsx|features/accounts/corporate-action-modal.test.tsx|lib/api-client.ts|lib/types.ts)' || true
```

Result: no diagnostics for the touched source or dedicated modal test file. The full `npx tsc --noEmit` remains blocked by the existing strict fixture errors documented above.

```text
git diff --check
```

Result: passed with no output.

## Review Fixes

- Awaited `onCompleted(result)` before close, typed it as `Promise<void> | void`, retained callback/API errors in the modal, and guarded close by the submitted account id and current account id.
- Added `etf` to `Market` and replaced the market selection cast with a type predicate.
- Added API POST/query encoding tests, a dedicated modal test file covering all five payload modes, validation, reverse split, rights cash messaging, backend errors, focus behavior, submission dismissal blocking, callback ordering, and callback failures.
- Added account-page completion refresh coverage, corporate-action ledger label/residual coverage, analytics audit formatting coverage, and explicit chart exclusion coverage for deposits, withdrawals, and corporate actions.
- Added focus-on-open, focus restoration, Escape handling, Tab containment, and disabled backdrop/cancel dismissal while submitting. No motion was added, so reduced-motion handling is not applicable.
- Corporate-action audit quantities and money values now use `formatQuantity` and `MoneyText`; action labels and dates use existing formatting helpers.

## Final Self-Review

- Simplify review: no further safe simplification was identified after removing the unused market collection and using a direct `isMarket` predicate. The account-id refs are necessary to preserve async account-switch behavior.
- The modal remains open if API processing or account refresh fails, and close happens only after successful refresh completion.
- The selected-account page continues to use `selectedAccountIdRef` and request ids for refresh/detail race protection.
- All changes are limited to the Task 6 frontend source/tests plus this requested Task 6 report update; no backend, plan, or specification files were changed.
