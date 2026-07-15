# Paper Trading Account Fee Configuration Design

## Goal

Allow paper trading accounts to define fee parameters at creation time. The feature must keep existing account creation requests working without changes, and accounts that omit fee fields must use the built-in `a_share` fee preset, whose values match the current hardcoded fee model.

## Scope

This design covers account-level fee configuration for newly created paper trading accounts, including a built-in preset for A-share accounts. It does not include editing fees after account creation, per-order fee overrides, user-managed fee profiles, or recalculating historical trades.

## Current Behavior

Paper trading fees are calculated by `paper_trading.domain.fees.calculate_a_share_fees`. The function accepts an optional `FeeConfig`, but production services currently call it without one.

The first built-in preset is `a_share`. Its values are the current hardcoded defaults:

- `commission_rate`: `0.0003`
- `min_commission`: `5.00`
- `stamp_duty_rate`: `0.0005`
- `transfer_fee_rate`: `0.00001`

`OrderService` uses the default fee configuration when freezing cash for buy orders. `MatchingService` uses the default fee configuration when creating trades and settling cash or positions.

## Data Model

Add four nullable-safe fee columns to `paper_accounts` with server defaults matching the current fee model:

- `fee_preset String(30) not null default 'a_share'`
- `commission_rate Numeric(20, 8) not null default 0.0003`
- `min_commission Numeric(20, 4) not null default 5.00`
- `stamp_duty_rate Numeric(20, 8) not null default 0.0005`
- `transfer_fee_rate Numeric(20, 8) not null default 0.00001`

The SQLAlchemy `PaperAccount` model exposes these fields. Existing rows receive the `a_share` preset and fee values through migration or schema initialization, so old accounts continue to behave the same.

`paper_trading.domain.fees` owns the built-in preset definitions. `a_share` is the default preset for account creation.

## API Contract

`POST /paper/accounts` accepts the existing request body:

```json
{
  "name": "demo",
  "initial_cash": "100000.00"
}
```

It also accepts optional fee fields:

```json
{
  "name": "demo",
  "initial_cash": "100000.00",
  "fee_preset": "a_share",
  "commission_rate": "0.00025",
  "min_commission": "5.00",
  "stamp_duty_rate": "0.0005",
  "transfer_fee_rate": "0.00001"
}
```

`fee_preset` is optional and defaults to `a_share`. If callers pass fee fields, those fields override the preset values for the created account. `AccountResponse` returns `fee_preset` and the four effective fee fields so callers can verify the account configuration.

## CLI Contract

`tools/paper_trading_cli.py account create` gains optional flags:

- `--fee-preset`
- `--commission-rate`
- `--min-commission`
- `--stamp-duty-rate`
- `--transfer-fee-rate`

When omitted, the CLI sends no fee override fields and the backend applies the `a_share` preset. When provided, the CLI sends `fee_preset` as a string, parses each fee value as `Decimal`, and sends fee values as strings in the JSON request body.

## Service Flow

Account creation passes optional `fee_preset` and fee values from schema to service to repository. Repository creation resolves the preset first, then applies caller-provided fee field overrides, then stores the effective values on the account.

Order placement and matching use the fee configuration stored on the account:

- Buy order cash freeze calculates estimated fees with the account fee configuration.
- Trade creation during matching calculates final fees with the same account fee configuration.
- Sell settlement deducts account-configured fees from proceeds.

This keeps order acceptance, frozen cash, trade fees, and settlement consistent for a given account.

## Validation

Fee values must be non-negative decimals. `min_commission` may be zero. Rates may be zero to support fee-free test accounts. Negative values are invalid at API/schema level.

`fee_preset` must be one of the built-in preset names. Unknown preset names are invalid at API/schema level.

## Testing

Add or update focused tests for:

- Account repository/service/API creation with default fee fields.
- Account creation with the `a_share` preset.
- Account creation with explicit fee fields.
- CLI `account create` request body with optional fee flags.
- Buy order frozen cash using account-specific fees.
- Matching trade fees using account-specific fees.
- Backward compatibility for existing tests that create accounts without fee parameters.

## Documentation

Update `docs/paper_trading.md` with the new account creation request fields and CLI flags.

## Non-Goals

- No API or CLI support for updating fees after account creation.
- No per-order fee overrides.
- No reusable fee profile table.
- No historical trade fee recalculation.
