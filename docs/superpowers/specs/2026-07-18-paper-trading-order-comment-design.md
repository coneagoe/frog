# Paper Trading Order Comment Design

## Goal

Allow each paper trading order to carry an optional `comment` that records the trading reason. The comment can be provided when placing the order or filled in later, and completed trades should also expose the comment for convenient review and export.

## Current Behavior

Paper trading orders and trades currently store structured trading data such as account, symbol, side, quantity, price, status, and dates. There is no field for a free-form trading reason. Users must record the reason outside the paper trading system.

## Scope

This change covers the backend, CLI, tests, and paper trading documentation:

- Add nullable `comment` persistence to paper orders and paper trades.
- Accept optional `comment` during order creation through the API and CLI.
- Copy an order comment into generated trade rows during matching.
- Allow an existing order comment to be updated or cleared after order creation.
- Synchronize comment updates from an order to trades generated from that order.
- Return `comment` in order and trade API responses and CLI output.

## Data Model

Add nullable text columns:

- `paper_orders.comment`
- `paper_trades.comment`

The default is `NULL` for existing and new records when no comment is provided. No comment is required to place an order or run matching.

## API Behavior

`CreateOrderRequest` accepts an optional `comment` string. The order response includes `comment` for create, list, and get operations.

Add an order comment update endpoint, for example:

```text
PATCH /paper/orders/{order_id}/comment
```

The request body contains a nullable or blank-able `comment`. Updating to an empty string clears the comment and stores `NULL` on the order and its linked trades.

When the order comment is updated, all trades linked to that order are updated to the same comment so trade queries stay aligned with the latest trading reason.

## Matching Behavior

When matching fills an accepted order, the generated `PaperTrade` copies `PaperOrder.comment` into `PaperTrade.comment`. This makes trade records self-contained for list queries, JSON responses, and exports.

## CLI Behavior

Order creation accepts an optional comment:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-18 --comment "突破买入"
```

Order comments can be added, changed, or cleared after creation:

```bash
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment "修正交易原因"
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment ""
```

Order list/get and trade list output should include the comment field. JSON output includes `comment` naturally from the API payload.

## Error Handling

Comment remains optional and must not affect existing order validation, account validation, position checks, or matching rules.

If an order ID does not exist when updating a comment, return the same not-found behavior used by other order operations. Updating a comment for an order with no trades should still succeed.

## Testing

Update tests to cover:

- Model/table column presence for order and trade comments.
- Repository persistence for order comments and trade comments.
- Order creation with and without comments.
- API order create/list/get responses include `comment`.
- CLI `order create --comment` forwards the comment in the request body.
- Matching copies the order comment to generated trades.
- Comment update changes the order comment and synchronizes generated trade comments.
- Clearing a comment works and does not break order or trade queries.

## Documentation

Update `docs/paper_trading.md` with:

- `order create --comment` usage.
- `order update-comment` usage.
- API request/response examples showing optional `comment` on orders and trades.

## Non-Goals

- No comment history/versioning.
- No separate note table.
- No requirement for comment on every order.
- No change to matching eligibility, fill price logic, fees, cash ledger, positions, or snapshots.
