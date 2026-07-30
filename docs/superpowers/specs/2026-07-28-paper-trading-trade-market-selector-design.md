# Paper Trading Trade Market Selector Design

## Goal

Require the Trade page to send an explicit market for every new paper-trading order, so Hong Kong Connect orders are not silently treated as A-share orders.

## Scope

The Trade order form adds a market selector with two supported values:

- `a_share`, displayed as `A-share` and selected by default.
- `hk_connect`, displayed as `Hong Kong Connect`.

The selected value is included in every frontend order payload. The frontend `CreateOrderInput` contract requires the field, preventing future Trade form callers from accidentally relying on the backend compatibility default.

The backend request schema, router, market validation, order placement, and matching logic remain unchanged. They already accept and validate the explicit market value.

## Form Behavior

`OrderForm` owns a `Market` state value initialized to `a_share`. It renders the same labeled native select pattern already used by the position-import modal. The form always sends the selected value with symbol, side, quantity, price, and trade date.

No market is inferred from symbol length, exchange suffix, or provider data. The user selects the market deliberately, and the backend remains responsible for rejecting a market/symbol mismatch.

## Quantity Guidance

The existing message, `A-share orders should use 100-share lots.`, is shown only when the selected market is `a_share` and the entered quantity is not divisible by 100.

It is hidden for Hong Kong Connect orders. Hong Kong board-lot requirements vary by security and continue to be validated by the backend's HK metadata path. This work does not add a frontend metadata lookup or a guessed board-lot rule.

## Types and Tests

The shared frontend `Market` union is reused. `CreateOrderInput.market` becomes required, while backend request compatibility remains unchanged for non-frontend callers.

Tests establish:

1. The selector defaults to `a_share`, and a normal A-share submission includes `market: "a_share"`.
2. Selecting Hong Kong Connect submits `market: "hk_connect"` for a five-digit HK symbol such as `00700`.
3. The A-share 100-share guidance remains visible for an invalid A-share lot and is hidden for the same quantity when Hong Kong Connect is selected.
4. Existing comment, account-selection, date, and required-field behavior remains intact.

The evidence path is the focused Trade form test suite, the frontend lint command, and the Next.js production build. The build is required because it catches TypeScript constraints not exercised by Vitest alone.

## Non-goals

- No automatic market inference.
- No backend API or order-service changes.
- No HK board-lot metadata lookup in the frontend.
- No changes to existing orders or positions.
