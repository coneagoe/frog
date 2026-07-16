# Paper Trading Account Fee Update Design

## Goal

Allow an existing paper trading account to update its fee configuration after creation.

Fee changes must apply only to transactions that happen after the update. Existing orders, trades, cash ledger entries, positions, and snapshots must not be recalculated.

## Scope

This design covers updating the fee fields stored on a paper trading account and exposing that capability through the API and CLI.

It does not introduce fee presets for updates, per-order fee overrides, or any historical recalculation.

## Current Behavior

Paper trading fee values are stored directly on the `paper_accounts` row and are read by order freezing and trade settlement logic.

Today, fee configuration can be set when an account is created, but there is no account update path for modifying fee values later.

## Requirements

- Allow updating an existing account's fee fields.
- Support partial updates: callers may provide one or more fee fields.
- Do not require or accept `fee_preset` in the update flow.
- Do not recalculate historical data.
- New orders and future trade settlement must use the updated fee values.
- Historical orders, trades, and cash movements must remain unchanged.

## API Contract

Add a PATCH endpoint for account fee updates:

```http
PATCH /paper/accounts/{account_id}
```

Request body supports only these optional fields:

```json
{
  "commission_rate": 0.0002,
  "min_commission": 3.0,
  "stamp_duty_rate": 0.001,
  "transfer_fee_rate": 0.00001
}
```

Rules:

- At least one field must be provided.
- All values must be non-negative decimals.
- Missing fields leave the existing account values unchanged.
- The response returns the updated account with its effective fee values.
- Unknown account IDs return the existing 404 response shape.

## Data Model

No new tables are required.

The existing fee columns on `paper_accounts` remain the source of truth:

- `fee_preset`
- `commission_rate`
- `min_commission`
- `stamp_duty_rate`
- `transfer_fee_rate`

The update flow only changes the numeric fee fields. `fee_preset` remains unchanged.

## Service Flow

1. The API validates the PATCH request body.
2. The account service loads the account by ID.
3. The repository updates only the requested fee fields.
4. The updated account is returned to the caller.

Order and matching services continue to read fee values from the account row at the time they perform their work.

This means:

- A buy order created after the update uses the new fee values when freezing cash.
- A trade matched after the update uses the new fee values when computing fees and settlement.
- A trade that already happened is not revised.

## CLI Contract

Add a CLI command for fee updates, for example:

```bash
uv run tools/paper_trading_cli.py account update-fee \
  --account-id 1 \
  --commission-rate 0.0002 \
  --min-commission 3
```

The command:

- accepts the same fee fields as the API;
- allows partial updates;
- requires `--account-id`;
- sends only the provided fields.

## Validation

- Reject negative fee values.
- Reject empty update requests.
- Keep existing account creation validation unchanged.
- Do not allow `fee_preset` in the update request schema.

## Testing

Add tests for:

- repository fee update success with full and partial payloads;
- repository validation for negative and empty updates;
- service update behavior on existing and missing accounts;
- API PATCH success, validation errors, and 404 behavior;
- CLI request construction for partial fee updates;
- behavior boundary proving that old trades remain unchanged while new orders use the updated fee values.

## Documentation

Update the paper trading backend docs to describe fee updates after account creation and the CLI update command.

## Non-Goals

- No fee preset switching during updates.
- No historical trade fee recalculation.
- No account-wide edits beyond the fee fields.
- No per-order override of fee logic.
