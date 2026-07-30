# Paper Trading Fee Update API Summary

> Temporary reference for frontend work.

## What Changed

Paper trading now supports updating account fee fields after account creation.

The change is API-first and affects the account flow only. Order, trade, matching, snapshot, and analytics endpoints are unchanged.

## API Changes

### 1) Create account still supports fee fields

`POST /paper/accounts`

Request body can include:

- `name`
- `initial_cash`
- `fee_preset`
- `commission_rate`
- `min_commission`
- `stamp_duty_rate`
- `transfer_fee_rate`

If fee fields are omitted, the backend uses the default `a_share` preset.

### 2) New fee update endpoint

`PATCH /paper/accounts/{account_id}`

Use this to update an existing account's fee fields.

Request body supports only these optional fields:

- `commission_rate`
- `min_commission`
- `stamp_duty_rate`
- `transfer_fee_rate`

Rules:

- Send at least one fee field.
- `fee_preset` is not accepted here.
- Values must be non-negative decimals.
- Omitted fields keep their current values.

Example:

```json
{
  "commission_rate": "0.0002",
  "min_commission": "3.00"
}
```

### 3) Account response already includes fee fields

`GET /paper/accounts`
`GET /paper/accounts/{account_id}`

Account responses already return:

- `fee_preset`
- `commission_rate`
- `min_commission`
- `stamp_duty_rate`
- `transfer_fee_rate`

No response-shape change is needed for the frontend.

## Behavior Notes for Frontend

- Fee updates only affect **future** orders and trades.
- Existing trades, cash ledger entries, and snapshots are **not** recalculated.
- If a user updates fees in the account UI, the view should refresh the account details after success.
- If the update payload is empty, the API returns 422.
- If the account ID does not exist, the API returns the existing 404 shape.

## Frontend Impact Checklist

- Add an edit action on the Accounts page for fee fields.
- Reuse the account details payload for form prefill.
- Submit `PATCH /paper/accounts/{account_id}` with only changed fields.
- Show server validation errors for empty payload / invalid decimals.
- Refresh account details after a successful update.

## Examples

### Update fees via curl

```bash
curl -X PATCH http://localhost:8000/paper/accounts/1 \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"commission_rate":"0.0002","min_commission":"3.00"}'
```

### Response example

```json
{
  "id": 1,
  "name": "demo",
  "initial_cash": "100000.00",
  "fee_preset": "a_share",
  "commission_rate": "0.00020000",
  "min_commission": "3.0000",
  "stamp_duty_rate": "0.00050000",
  "transfer_fee_rate": "0.00001000",
  "status": "active",
  "base_currency": "CNY"
}
```

## Reference Files

- API router: `paper_trading/api/routers/accounts.py`
- Request/response schema: `paper_trading/schemas/accounts.py`
- CLI mirror: `tools/paper_trading_cli.py`
