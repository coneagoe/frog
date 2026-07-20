# Paper Trading Order Delete Design

## Goal

Allow users to delete a paper trading order from the backend and frontend, including filled orders, while keeping account cash, trades, positions, lots, round trips, matching runs, validity checks, and snapshots consistent.

## Current Behavior

Paper trading supports creating, listing, fetching, canceling, and commenting on orders. Account deletion already cascades through paper trading tables, but there is no order-level delete endpoint. Filled orders create derived state through matching: trades, cash ledger entries, position rows, position lots, round trips, matching run metadata, and account snapshots.

## Scope

This change covers backend API/service/storage logic, frontend order history UI, tests, CLI support if it currently exposes the order command group, and paper trading documentation.

- Add a destructive order delete operation.
- Permit deleting filled, canceled, rejected, and open orders.
- After deletion, rebuild the entire account history from surviving orders.
- Keep the account row, account fee settings, initial cash ledger entry, and imported starting positions intact.
- Refresh frontend order data after successful deletion and expose clear errors on failure.

## Chosen Approach

Use account-scoped full history rebuild after deleting an order. This is safer than targeted row cleanup because positions and lots are not linked directly to a trade, snapshots are derived by date, matching runs are metadata-only, and round trips already have an account rebuild pattern.

To preserve imported starting holdings while still clearing trade-derived holdings, add an explicit source marker to positions and lots. Imported rows are marked `imported`; rows created by matching are marked `trade`.

The rebuild resets account-derived paper trading state and replays the remaining orders in deterministic order. This trades some performance for correctness and simpler verification, which is acceptable for paper trading account sizes.

## Backend Behavior

Add:

```text
DELETE /paper/orders/{order_id}
```

Behavior:

- Return `204 No Content` after a successful delete.
- Return `404 Not Found` when the order ID does not exist.
- Delete the selected order regardless of status.
- Rebuild the owning account from surviving order history in `(trade_date, id)` order while preserving each surviving order's original status semantics.
- Commit the delete and rebuild in one transaction.

## Rebuild Semantics

The rebuild keeps source-of-truth inputs and removes derived state.

Keep:

- `paper_accounts` row and fee settings.
- Initial deposit cash ledger entry with note `initial_cash`.
- Imported starting position lots/positions, marked `imported`, because they represent external starting state rather than derived matching output.
- Surviving orders.

Clear and regenerate:

- `paper_trades`
- matching-derived `paper_cash_ledger` rows except `initial_cash`
- matching-derived positions/lots created from orders, while preserving imported starting positions/lots marked `imported`
- `paper_account_snapshots`
- `paper_position_round_trips`
- `paper_matching_runs`
- `paper_trade_validity_checks`

Surviving canceled and rejected orders stay canceled or rejected and are not replayed as executable orders. Surviving filled, partially filled, accepted, and new orders are reset only as needed for deterministic matching replay.

When clearing rebuild state, imported lots are reset to their original baseline (`remaining_quantity = original_quantity`). Aggregate `paper_positions` rows are deleted and rebuilt from the imported lots before order replay, because positions can contain both imported baseline and trade-derived changes after matching. The delete service must load the target order, clear dependent derived rows, then stage the order delete before replaying surviving orders. This avoids SQLAlchemy autoflush deleting an order while `paper_trades.order_id` or `paper_trade_validity_checks.order_id` still reference it.

## Data Model

Add source marker columns:

- `paper_positions.source`, string, non-null, default `trade`
- `paper_position_lots.source`, string, non-null, default `trade`

`AccountService.import_positions()` writes `source="imported"` for imported positions and lots. `MatchingService` writes or updates `source="trade"` for positions and lots created from matched orders. Existing rows default to `trade`, which is conservative for current historical data because there is no previous reliable imported/trade discriminator.

Implementation should introduce explicit repository/service helpers rather than duplicating ad hoc delete queries in the router. The service owns orchestration: get order, delete it, rebuild account, and return whether deletion happened.

## Frontend Behavior

The Orders history page adds a Delete action next to existing Cancel/Edit actions. Clicking Delete shows a browser confirmation explaining that deleting a filled order recalculates account history. On confirmation, the frontend calls the delete endpoint, disables the row action while pending, and reloads the selected account's order list. Errors are shown through the existing `ErrorBanner`.

Copy should be plain and explicit:

```text
Delete this order? Filled trades, cash ledger, positions, and snapshots for this paper account will be recalculated.
```

## CLI Behavior

If the CLI order command group remains in scope, add:

```bash
uv run tools/paper_trading_cli.py order delete --order-id 123
```

Text output should be concise, for example `Deleted order 123`. JSON output may return `null` or `{ "deleted": true, "order_id": 123 }`; tests should lock whichever pattern is simpler for the current CLI structure.

## Error Handling

- Missing order ID returns API 404 and frontend displays the parsed API error.
- Rebuild failures roll back the transaction, leaving the pre-delete account state intact.
- Delete does not silently skip inconsistent state. If a surviving order cannot be replayed because market data is unavailable or validation rejects it, the matching service handles it with the same behavior as normal matching runs.

## Testing

Backend tests should cover:

- Deleting a missing order returns 404.
- Deleting an unfilled/canceled order removes it and leaves the account queryable.
- Deleting a filled order removes its trade and recalculates cash, positions, lots, round trips, matching runs, validity checks, and snapshots from remaining orders.
- Rebuild preserves the initial cash ledger entry.
- Delete endpoint commits once and returns 204.

Frontend tests should cover:

- Delete button appears for orders.
- Canceling the browser confirmation does not call the API.
- Confirming deletion calls the API and reloads orders.
- Delete failure renders `ErrorBanner`.

CLI tests should cover the new `order delete` command if CLI support is implemented.

## Documentation

Update `docs/paper_trading.md` with the delete endpoint and CLI usage, including the recalculation warning.

## Non-Goals

- No soft-delete or restore flow.
- No audit log for deleted orders.
- No bulk delete UI.
- No direct trade-row deletion.
- No DAG, scheduler, retry, or SLA changes.
