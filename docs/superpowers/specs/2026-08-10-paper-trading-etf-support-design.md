# Paper Trading China ETF Support Design

## Scope

Add support for non-money-market ETFs listed on the Shanghai and Shenzhen stock
exchanges. ETF orders use an explicit `market=etf` value. This includes
domestically listed cross-border ETFs. This phase does not support money-market
ETFs, ETFs listed outside Shanghai and Shenzhen, automatic market inference
from a symbol, or ETF-specific T+0 classification.

## Goals

- Accept valid domestic non-money-market ETF orders through the existing paper
  trading workflow.
- Keep ETF market data and metadata separate from A-share stock data.
- Apply ETF-specific fees and trading rules without changing existing A-share
  or Hong Kong Stock Connect behavior.
- Preserve ETF market identity across orders, trades, positions, validity
  checks, snapshots, account summaries, and round-trip analytics.

## Market And Metadata

Add `Market.ETF = "etf"` to the paper trading market enum. The API and CLI
require callers to select this market explicitly.

For `market=etf`, validate the six-digit symbol against the existing ETF basic
metadata. The symbol must identify a currently listed Shanghai or Shenzhen
ETF. Use an explicit adapter that maps the provider's raw `exchange` and
`list_status` values to supported classifications; do not infer eligibility
from code prefixes or substring matching. The adapter allows only TuShare's
known Shanghai and Shenzhen exchange values (`SH`, `SZ`) and listed status
(`L`). Unknown, missing, or unsupported values are rejected.

TuShare `etf_type` describes an investment channel such as domestic or QDII;
it does not reliably classify money-market ETFs. Add an ETF eligibility table
as the authoritative non-money-market classification. It records the bare
six-digit symbol, classification status, review metadata, and the latest
lifecycle data needed for audit. Its statuses are `unknown`, `supported`,
`money_market`, and `disabled`.

The daily ETF basic-information synchronization reconciles this table after a
successful provider refresh: newly discovered listed ETF codes become
`unknown`; codes no longer listed become `disabled`; and provider name,
exchange, and listing-status changes are refreshed without overwriting a
reviewed `supported` or `money_market` classification. Only `supported` rows
with an eligible current ETF basic record may be ordered. An absent ETF record
returns `ETF_NOT_FOUND`; `money_market` and `disabled` rows return
`UNSUPPORTED_ETF_TYPE`; and an `unknown` row returns `ETF_ELIGIBILITY_UNREVIEWED`.

Provide paper trading CLI operations to list and inspect eligibility records and
to set an eligible code's status to `supported` or `money_market`; no new web
UI or external service is required. Symbols with exchange suffixes such as
`.SH` or `.SZ` are rejected at the ETF entry point. Existing A-share and Hong
Kong symbol validation remains unchanged.

ETF display names are resolved from ETF basic metadata. The paper trading
records retain the existing market field and persist `etf` on every derived
record.

## Market Data

Extend the market data provider's explicit market routing for `etf`:

- Daily bars and latest daily closes use the existing ETF-specific daily data
  storage that the ETF download DAG already populates.
- The provider uses the same stored price-adjustment convention as that data
  pipeline for matching and valuation. Order prices, fills, position cost, and
  snapshots therefore use one consistent price basis.
- ETF valuation and matching never fall through to A-share stock history.
- ETF bars provide open, high, low, and close values. A-share limit-price data
  is not loaded for ETFs.

If an exact-date ETF bar is unavailable during matching, preserve the accepted
order, record the existing daily-bar diagnostic and warning, and allow a later
same-date retry once data arrives.

## Fees

Add account-level `etf_commission_rate` and `etf_min_commission` configuration
with defaults matching the existing commission and minimum-commission
convention. Expose both fields when creating, updating, and retrieving an
account. ETF transactions charge commission only: no stamp duty and no transfer
fee on either buy or sell.

Existing A-share and Hong Kong fee fields and calculations remain unchanged.
Existing accounts receive the ETF defaults through the migration/default path;
their current behavior does not change.

## Trading Rules

- ETF order quantity must be positive and divisible by 100.
- ETF limit prices must be positive multiples of CNY 0.001. Reject a price that
  is not tick-aligned with `INVALID_TICK_SIZE`.
- The first phase applies T+1 uniformly: ETF units bought on a trade date are
  not sellable on that same date. Imported lots use their existing
  `buy_trade_date` and participate in the same sellable-quantity calculation.
- Buy orders reserve notional value plus ETF commission. Sell orders reserve
  sellable ETF quantity.
- Matching uses the ETF daily bar and fills a tradable limit order at its limit
  price when that price falls within the day's low/high range.
- ETF validity checks assess the daily price range and ordinary account rules,
  but do not apply A-share limit-up or limit-down detection.
- ETF sells return proceeds to available cash immediately on fill. ETF share
  sellability remains T+1 and is independent of this cash rule.
- ETF metadata failures are explicit order-stage rejections. Missing market
  data is a recoverable matching-stage warning, not an A-share fallback.
- ETF supports the existing explicit past-date order and account rebuild flow.
  Historical replay applies the same ETF metadata, fee, tick-size, T+1, and
  daily-bar rules as current-date matching.

## Persistence And Migration

Extend the existing market enum/database constraint to include `etf`. Add the
ETF fee configuration using the repository's enum migration and rollback
conventions. Migration defaults must leave existing accounts and records
unchanged and must preserve the ability to read and replay existing
`a_share` and `hk_connect` data.

No new security-type column is required in this phase; the explicit persisted
market value is the routing contract. However, all security identity and
derived-state boundaries must use `(account_id, market, symbol)`, not just a
symbol:

- Change position uniqueness and all position lookups, upserts, imports, lot
  lookups, sellability calculations, frozen-quantity operations, historical
  rebuilds, and round-trip queries to include `market`.
- Change the daily-bar diagnostic key to `(business_date, market, symbol,
  adjust)` and migrate existing A-share diagnostics with `market=a_share`.
- Include `market` in valuation-gap details and other persisted references to a
  missing symbol so diagnostics and retry eligibility cannot cross markets.

## Tests And Acceptance

Add focused tests covering:

- ETF market enum, schema migration, defaults, and rollback behavior.
- Eligibility-table migration, daily reconciliation, CLI review operations,
  review audit data, and rollback behavior.
- Valid listed Shanghai/Shenzhen `supported` ETF acceptance, including a
  domestic-listed cross-border ETF.
- Unknown eligibility, disabled/delisted, money-market, invalid exchange or
  listing status, and absent ETF metadata rejection with the specified error
  codes.
- ETF name resolution and market preservation through derived records.
- ETF data provider routing to the populated ETF-specific daily table for daily
  bars and latest closes, with no stock-data or fund-daily fallback.
- ETF commission-only fee calculations on buy and sell.
- 100-unit lot validation, CNY 0.001 tick validation, T+1 sellability, and
  imported-lot behavior.
- Daily-range matching, validity checks without stock limit analysis, and
  missing-bar retry behavior, including historical order replay.
- ETF valuation, snapshots, account summaries, round trips, and historical
  rebuilds, including symbols that collide across markets.
- Market-qualified daily-bar diagnostics and valuation gaps, including migration
  of existing A-share diagnostic records.
- Regression coverage for existing A-share and Hong Kong Stock Connect flows.

Acceptance requires a test-backed ETF buy on one trading date, a sell on the
next trading date, successful matching and snapshot valuation, and passing the
repository's relevant formatting, lint, type-check, and paper trading tests.

## Non-Goals

- Money-market ETF support.
- ETF-specific T+0 classification.
- ETFs listed outside Shanghai or Shenzhen, even if they track domestic or
  overseas assets.
- Automatic symbol-based market inference.
- Changes to DAG schedules, task boundaries, or unrelated storage workflows.
