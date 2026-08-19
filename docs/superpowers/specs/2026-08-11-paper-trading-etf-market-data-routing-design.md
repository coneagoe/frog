# Paper Trading ETF Market Data Routing Design

## Scope

Issue #45 routes the existing paper-trading `etf` market to the populated
`etf_daily` data pipeline for daily bars and latest daily closes. It covers the
market-data boundary plus the existing matching retry, diagnostics, valuation,
and snapshot flows that consume it.

This issue does not change ETF eligibility, order acceptance, fees, quantity or
tick rules, T+1 sellability, or any other paper-trading market behavior.

## Market Data Contract

Extend `StorageMarketDataProvider` with an explicit `etf` branch in both
market-data operations:

- `get_daily_bar(symbol, trade_date, market="etf")` reads the exact date from
  the existing ETF daily storage helper and maps its OHLC values to `DailyBar`.
- `get_latest_daily_close(symbol, trade_date, market="etf")` reads the latest
  ETF close on or before the requested date from the existing ETF daily storage
  helper.
- Both ETF operations use the adjustment convention already stored by the ETF
  daily pipeline. Matching, fill prices, position valuation, and snapshots
  therefore use one price basis.
- ETF requests never read A-share stock history or `fund_daily`. Missing ETF
  data remains missing instead of falling back to a different security type.

Existing A-share and Hong Kong Stock Connect routing remains unchanged.

## Missing Data And Retry

When matching an accepted ETF order cannot obtain an exact-date ETF bar, the
provider raises the existing missing-bar error. `MatchingService` preserves its
current recoverable behavior: the order remains accepted, an unresolved daily
bar diagnostic and warning are recorded with `market="etf"`, and a later
matching attempt can fill the order after ETF data arrives.

The delayed daily-bar rebuild query must treat ETF diagnostics as eligible for
retry. It continues to require the existing exact-date, unresolved, BFQ
diagnostic conditions and joins by market-qualified security identity; it must
not retain an A-share-only market filter that would permanently exclude ETF
orders.

## Valuation And Snapshots

`SnapshotService` and `PositionValuationService` already pass a position's
market to the market-data provider. Once ETF routing exists, ETF positions use
ETF daily closes for snapshots, account value, and request-time valuation.
When a required ETF bar is absent, the existing valuation-gap flow retains the
ETF market in its detailed missing-security entry and does not attempt a stock
or fund fallback.

## Tests And Acceptance

Add focused tests for:

- Exact-date ETF OHLC retrieval and latest ETF close retrieval from ETF storage.
- Shared adjustment-basis behavior across the two ETF provider operations.
- No A-share or `fund_daily` loader invocation for ETF requests, including
  missing ETF data.
- ETF matching with an available bar and ETF-market-qualified missing-bar
  diagnostic/warning behavior.
- Delayed matching rebuild retrying a previously missing ETF order once the
  exact ETF bar becomes available.
- ETF snapshot and position valuation using ETF closes, plus an ETF-qualified
  valuation gap when data is absent.
- Existing A-share and Hong Kong Stock Connect provider-routing regressions.

Acceptance requires ETF daily bars and latest closes to come only from
`etf_daily`, matching and valuation to share the ETF pipeline's stored price
basis, and missing exact-date ETF bars to remain recoverable and retryable.

## Non-Goals

- ETF eligibility or metadata validation.
- ETF order acceptance, fees, lot size, tick size, or T+1 behavior.
- New ETF data downloads, storage tables, providers, or DAG changes.
- A-share or Hong Kong Stock Connect routing changes.
