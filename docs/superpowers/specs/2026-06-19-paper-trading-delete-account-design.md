# Paper Trading Delete Account Design

## Goal

Add a backend API to permanently delete a paper trading account and all data owned by that account.

## Scope

- Add `DELETE /paper/accounts/{account_id}` to the existing FastAPI paper trading backend.
- Physically delete account-owned rows for cash ledger entries, orders, trades, positions, position lots, snapshots, and matching runs.
- Return `204 No Content` when deletion succeeds.
- Return `404 Not Found` when the account does not exist.
- Do not add frontend UI in this change.

## Architecture

The existing account route delegates account operations to `AccountService`, which delegates persistence to `PaperTradingRepository`. Keep that layering: the API route validates HTTP semantics, `AccountService` owns account-level behavior, and `PaperTradingRepository` performs the ordered database deletes.

The repository will delete by `account_id` in an explicit child-to-parent order, then delete the `PaperAccount`. This avoids relying on implicit database cascade behavior and makes the destructive behavior visible in code and tests.

## Data Flow

1. Client calls `DELETE /paper/accounts/{account_id}` with the existing bearer token.
2. Router creates `PaperTradingRepository` and `AccountService`.
3. Service asks the repository to delete the account.
4. Repository checks account existence, deletes account-owned rows, deletes the account row, and flushes.
5. Router commits and returns `204 No Content`.

## Error Handling

- Missing account: return `404 Not Found` with a short message.
- Authentication remains unchanged because the router already requires `require_api_token`.
- Database errors propagate through the existing FastAPI/session handling; no custom retry or partial recovery is added.

## Testing

- Add a repository/service-level test proving deleting an account removes the account and its owned rows.
- Add an API test proving `DELETE /paper/accounts/{account_id}` returns `204` and the account no longer appears in `GET /paper/accounts`.
- Add an API test proving deleting an unknown account returns `404`.
- Use `uv run pytest` for focused tests, following existing repo conventions.

## Non-Goals

- No soft delete or archive state.
- No frontend account deletion button.
- No database migration or model-level cascade change.
- No bulk delete endpoint.
