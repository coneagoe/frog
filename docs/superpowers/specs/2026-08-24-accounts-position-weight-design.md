# Accounts Positions: Individual Stock Weight

## Goal

Add an individual-stock position-weight column to the Positions card on the
paper trading frontend Accounts page.

The displayed weight is the stock's current market value as a percentage of
the selected account's net asset value (NAV):

```text
weight = total_quantity * mark_price / account.nav * 100
```

## Scope

- The new column is shown in the Accounts page Positions card.
- The shared `PositionTable` remains the rendering owner so its column layout
  stays consistent with other uses.
- The selected account's existing `nav` value is passed into the table.
- No backend endpoint or response schema changes are required.
- No order, account, valuation, or portfolio behavior changes are included.

## Data Flow

`features/accounts/accounts-page.tsx` already owns the selected account and
renders the Positions card. It will pass the selected account NAV to
`features/trading/trading-tables.tsx` through a focused table prop.

For each position, the table will derive market value from `total_quantity`
and `mark_price`, then divide by the selected account NAV. The calculation is
performed only for display and does not mutate API data.

## Display and Fallbacks

- Column label: `Weight`.
- Value format: percentage with the table's existing percentage formatting
  convention and a stable, compact precision suitable for the dense table.
- If NAV is missing, zero, non-finite, or otherwise unusable, display the
  existing unavailable-value marker (`—`).
- If `mark_price` is unavailable or the quantity/value inputs are invalid,
  display `—` rather than a misleading zero or percentage.
- Account switching must recalculate the values against the newly selected
  account's NAV.

## Testing

Update the Accounts page and shared table tests to cover:

- The new column appears in the expected table order.
- A valid position renders market value divided by the selected account NAV
  as a percentage.
- Switching accounts uses the new account NAV for the calculation.
- Missing/unavailable valuation and invalid or unavailable NAV render `—`.

Existing return, sorting, account-loading, and position-loading behavior must
remain unchanged.

## Alternatives Considered

1. **Frontend-derived value (selected):** concentrated change using existing
   fields, without changing the API contract.
2. **Backend-derived value:** centralizes the calculation but requires
   account-aware response/schema changes for a display-only metric.
3. **Accounts-specific table implementation:** avoids changing the shared
   table but duplicates position-column logic and risks inconsistent views.
