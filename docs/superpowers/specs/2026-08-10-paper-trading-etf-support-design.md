# Paper Trading China ETF Support Design

## Scope

Add support for non-money-market ETFs listed on the Shanghai and Shenzhen stock
exchanges. ETF orders use an explicit `market=etf` value. This phase does not
support money-market ETFs, Hong Kong ETFs, overseas ETFs, or automatic market
inference from a symbol.

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
metadata. The symbol must identify a Shanghai or Shenzhen non-money-market ETF.
Reject unknown symbols with `ETF_NOT_FOUND` and reject money-market ETFs with
`UNSUPPORTED_ETF_TYPE`. Symbols with exchange suffixes such as `.SH` or `.SZ`
are rejected at the ETF entry point. Existing A-share and Hong Kong symbol
validation remains unchanged.

ETF display names are resolved from ETF basic metadata. The paper trading
records retain the existing market field and persist `etf` on every derived
record.

## Market Data

Extend the market data provider's explicit market routing for `etf`:

- Daily bars use the existing `load_history_data_fund` storage helper and the
  `fund_daily` table.
- Latest daily closes use the same ETF/fund data source.
- ETF valuation and matching never fall through to A-share stock history.
- ETF bars provide open, high, low, and close values. A-share limit-price data
  is not loaded for ETFs.

If an exact-date ETF bar is unavailable during matching, preserve the accepted
order, record the existing daily-bar diagnostic and warning, and allow a later
same-date retry once data arrives.

## Fees

Add account-level ETF commission configuration with defaults matching the
existing commission and minimum-commission convention. ETF transactions charge
commission only: no stamp duty and no transfer fee on either buy or sell.

Existing A-share and Hong Kong fee fields and calculations remain unchanged.
Existing accounts receive the ETF defaults through the migration/default path;
their current behavior does not change.

## Trading Rules

- ETF order quantity must be positive and divisible by 100.
- The first phase applies T+1 uniformly: ETF units bought on a trade date are
  not sellable on that same date. Imported lots use their existing
  `buy_trade_date` and participate in the same sellable-quantity calculation.
- Buy orders reserve notional value plus ETF commission. Sell orders reserve
  sellable ETF quantity.
- Matching uses the ETF daily bar and fills a tradable limit order at its limit
  price when that price falls within the day's low/high range.
- ETF validity checks assess the daily price range and ordinary account rules,
  but do not apply A-share limit-up or limit-down detection.
- ETF metadata failures are explicit order-stage rejections. Missing market
  data is a recoverable matching-stage warning, not an A-share fallback.

## Persistence And Migration

Extend the existing market enum/database constraint to include `etf`. Add the
ETF fee configuration using the repository's enum migration and rollback
conventions. Migration defaults must leave existing accounts and records
unchanged and must preserve the ability to read and replay existing
`a_share` and `hk_connect` data.

No new security-type column is required in this phase; the explicit persisted
market value is the routing contract.

## Tests And Acceptance

Add focused tests covering:

- ETF market enum, schema migration, defaults, and rollback behavior.
- Valid non-money-market ETF metadata acceptance.
- Unknown ETF and money-market ETF rejection with distinct error codes.
- ETF name resolution and market preservation through derived records.
- ETF data provider routing for daily bars and latest closes, with no stock
  data fallback.
- ETF commission-only fee calculations on buy and sell.
- 100-unit lot validation, T+1 sellability, and imported-lot behavior.
- Daily-range matching, validity checks without stock limit analysis, and
  missing-bar retry behavior.
- ETF valuation, snapshots, account summaries, round trips, and historical
  rebuilds.
- Regression coverage for existing A-share and Hong Kong Stock Connect flows.

Acceptance requires a test-backed ETF buy on one trading date, a sell on the
next trading date, successful matching and snapshot valuation, and passing the
repository's relevant formatting, lint, type-check, and paper trading tests.

## Non-Goals

- Money-market ETF support.
- ETF-specific T+0 classification.
- Hong Kong, overseas, or exchange-traded products outside the domestic ETF
  metadata scope.
- Automatic symbol-based market inference.
- Changes to DAG schedules, task boundaries, or unrelated storage workflows.
