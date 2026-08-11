# ETF Account Fees And Market Contract Design

## Scope

Issue #44 adds the explicit `etf` paper-trading market and the account-level
ETF commission contract. It relies on the existing market-qualified security
identity and ETF eligibility lifecycle work.

The change preserves the behavior and persisted values of the existing
`a_share` and `hk_connect` markets. It does not infer market from a symbol.

## Market And Fee Contract

- Add `etf` to the persisted `Market` enum. API and CLI order callers select
  it explicitly with `market=etf`.
- Add nullable `etf_commission_rate` to `PaperAccount`, using
  `NUMERIC(20, 8)`. Null means that the account uses the ETF default rate of
  `0.00006`.
- Account creation accepts an optional `etf_commission_rate`; account fee
  updates accept it independently or alongside existing A-share and Hong Kong
  Connect fee fields; account responses expose it.
- ETF fee calculation charges commission only on both buys and sells. The
  commission is the monetary amount multiplied by the account override or the
  `0.00006` default, rounded to cents with the existing half-up convention.
  There is no minimum commission. Stamp duty and transfer fee are always zero.
- The persisted trade fee total remains the existing scalar total. ETF fee
  calculations use the existing three-field breakdown shape, with zero stamp
  duty and transfer fee.

## Service Integration

Order placement resolves `Market.ETF` and uses an ETF-specific branch for cash
reservation. ETF buys reserve order amount plus the ETF commission. ETF order
placement and matching dispatch to the ETF fee helper rather than the A-share
or Hong Kong Connect helpers.

The ETF implementation does not alter A-share lot, historical-order, or market
symbol checks beyond preventing the generic A-share path from handling an ETF
order. ETF-specific eligibility, market-data, tick, lot, matching-range, and
settlement rules are delivered by their separate issue #41 tickets.

## API, CLI, And Persistence

Extend the existing account schemas, account service, repository methods, and
accounts router with the optional ETF rate. Extend the CLI API client and the
`account create` and `account update_fee` commands with
`--etf-commission-rate`; it is sent only when supplied.

Extend the governed paper-trading enum migration to add `etf` to `paper_market`
and add the nullable account column during upgrade. Rollback removes the
account column only through the established migration preflight and rejects a
rollback if persisted ETF market data would make the enum downgrade unsafe.
Existing accounts receive a null rate and therefore use the documented ETF
default without modifying A-share or Hong Kong Connect fields.

## Tests And Verification

Add focused coverage for:

- `Market.ETF` persistence and schema migration/rollback behavior.
- Account creation, patch updates, and API responses for
  `etf_commission_rate`, including zero as a valid override.
- CLI forwarding and local validation of `--etf-commission-rate`.
- Default and overridden ETF commission on buy and sell fills, cent rounding,
  no minimum commission, and zero stamp duty and transfer fee.
- ETF buy reservation using the same fee calculation as matching.
- Existing A-share and Hong Kong Connect account fee and order fee behavior.

Run focused domain, storage, service, API, and CLI tests, followed by Ruff and
the relevant type checks. PostgreSQL migration tests may skip only when the
test database configuration is absent.
