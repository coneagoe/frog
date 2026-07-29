# Task 2 / Ticket #3 Report

## Changed files

- `frontend/paper-trading/lib/types.ts` — added the backend valuation fields to `Position` while retaining `realized_pnl` for API compatibility.
- `frontend/paper-trading/features/trading/trading-tables.tsx` — replaced the Positions table's `Realized PnL` column with `Unrealized PnL`, rendering the API value through the existing money formatter and `Unavailable` for null.
- `frontend/paper-trading/features/trading/trading-tables.test.tsx` — added focused coverage for the heading, API-supplied value, and unavailable state.

The pre-existing untracked plan document was not modified.

## TDD evidence

### RED

Command:

```text
npm test -- features/trading/trading-tables.test.tsx
```

Summary: RED as expected. The suite ran 8 tests with 3 failures: the table still exposed `Realized PnL`, and neither the API value nor `Unavailable` was rendered.

### GREEN

Command:

```text
npm test -- features/trading/trading-tables.test.tsx
```

Summary: GREEN. The focused suite passed 8/8 tests in 1 test file.

## Design and interaction decisions

- Kept the existing Positions table order, right alignment, `MoneyText` formatting, and visual hierarchy unchanged.
- Used the backend's `unrealized_pnl` directly; no frontend price selection or PnL arithmetic was added.
- Kept `mark_price` and `price_source` in the type for the API contract, without rendering them in this card.
- Used the exact explicit `Unavailable` marker when the API supplies a null unrealized PnL.

## Commit

Commit SHA: `8e6bb59`

Commit subject: `feat: show unrealized pnl for positions`

## Concerns

- The focused test output includes the existing Vite CJS API deprecation notice; it does not affect test results.
- Other account-page fixtures in the repository still use the pre-Ticket #2 Position shape and were not changed because this task is scoped to the focused Positions table tests and the requested frontend files.
