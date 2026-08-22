# Paper Trading Positions Return And Sorting

## Scope

Update the Positions card on the paper trading frontend Accounts page. Remove
the cost column, add a position-level unrealized return column, and make every
visible column sortable. The backend API contract and all other account and
analytics surfaces remain unchanged.

## User-visible behavior

The Positions table contains these columns, in order:

1. Symbol
2. Stock
3. Total
4. Frozen
5. Return

The Cost column is not rendered.

Return is the position's unrealized return only. It is calculated as:

```text
unrealized_pnl / cost_amount * 100%
```

`realized_pnl` is intentionally excluded. When `cost_amount` is zero, either
required value is unavailable, or the result cannot be calculated, the table
renders `—`.

Return formatting uses two decimal places:

- Positive: `+12.34%`
- Negative: `-8.50%`
- Zero: `0.00%`
- Unavailable: `—`

Positive and negative values use the existing success and danger color tokens,
respectively. Zero uses the normal text color and unavailable values use the
muted color. The explicit sign means color is not the only signal of direction.

## Sorting interaction

The initial order is the order returned by the API; there is no default sort.
Each visible column has an accessible sortable header. The first click on a
column sorts ascending, and the next click on that same column sorts descending.
Clicking another column switches to single-column sorting on that column and
removes the previous column's sort indicator. There is no third, unsorted click
state.

The active sort direction is exposed through the header indicator and
`aria-sort`. Text columns use text comparison; quantity and return columns use
numeric comparison. Missing values sort after available values in both
ascending and descending order.

Sorting state is reset when the selected account changes or fresh position data
is loaded, so the table returns to the new API order. No sorting state is
persisted across accounts or refreshes.

## Implementation boundaries

The change is localized to the frontend Positions table and its supporting
styles/tests, primarily:

- `frontend/paper-trading/features/trading/trading-tables.tsx`
- `frontend/paper-trading/app/globals.css`
- the relevant trading/accounts frontend tests

The implementation should reuse the existing position response fields and
formatting conventions. It should not add a backend return-rate field, change
the generic table behavior, or introduce sign-aware coloring for unrelated
money and analytics values.

## Verification

Tests must cover:

- the Cost column is absent and Return is present;
- positive, negative, zero, and unavailable return formatting;
- success/danger/default/muted sign classes;
- all visible columns sort ascending and descending;
- a new column replaces the previous sort state;
- missing values remain last in either direction;
- the initial API order is preserved;
- account changes and refreshed position data reset sorting;
- existing account loading, switching, and compact table behavior remains
  intact.

Run the frontend focused tests, then frontend lint and build. Run the existing
Accounts visual E2E test if the environment supports the configured Next.js
test server.
