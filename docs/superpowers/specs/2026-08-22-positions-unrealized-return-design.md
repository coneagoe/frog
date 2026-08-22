# Positions Unrealized Return

## Scope

Update the paper trading Accounts page Positions table for issue #80. The
table will show unrealized return in place of cost while retaining the compact
layout and the order supplied by the positions API.

## Design

`PositionTable` will render columns in this order: `Symbol`, `Stock`, `Total`,
`Frozen`, and `Return`. The existing `Position` payload is sufficient; no API
or backend changes are needed.

For each position, return is calculated as:

`unrealized_pnl / cost_amount * 100`

Realized PnL is deliberately excluded. Values are rendered with two decimal
places and a percent suffix. Positive values include `+`, negative values keep
their minus sign, and zero has no sign. Zero cost, missing unrealized PnL,
non-numeric inputs, and non-finite calculation results render a muted em dash.

Positive, negative, zero, and unavailable values use the existing semantic
success, danger, default, and muted visual states. The rendered text itself
also carries direction through its sign where applicable.

## Testing

Frontend tests will verify the exact column headers and order, removal of the
Cost column, calculation from unrealized PnL only, two-decimal formatting and
sign handling, semantic classes, unavailable boundary cases, backend row
order, and preservation of the compact table classes.

## Out Of Scope

- Backend response or database changes.
- Position sorting or transformation.
- Changes to non-Accounts position tables or unrelated layout styling.
