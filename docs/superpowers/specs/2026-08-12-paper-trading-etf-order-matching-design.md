# Paper Trading ETF Order And Matching Design

## Scope

Issue #46 completes the current-date ETF order-to-fill workflow for eligible
Shanghai and Shenzhen ETFs. It uses the already implemented ETF market enum,
eligibility lifecycle, ETF fee configuration, and ETF daily-bar routing.

This issue covers ETF order acceptance, matching, settlement, T+1 sellability,
validity analysis, historical replay, and ETF market/name propagation through
paper-trading read paths. It does not add a web UI, automatic market inference,
money-market ETF support, ETF-specific T+0 handling, or changes to DAG
schedules, dependencies, retries, task boundaries, or SLA.

## Order Acceptance

`OrderService.place_order` dispatches `market=etf` to a narrow ETF-specific
order path. The path requires a bare six-digit symbol and rejects exchange
suffixes. It delegates eligibility and lifecycle validation to the existing ETF
eligibility validation seam, preserving its distinct outcomes for absent
metadata, unreviewed eligibility, disabled or money-market classifications,
invalid exchange, and invalid listing status.

ETF orders require an open trade date, a positive quantity divisible by 100,
and a positive limit price aligned to a CNY 0.001 tick. Invalid lot and tick
requests use the established error codes. Accepted ETF buys reserve notional
plus ETF commission. Accepted ETF sells reserve only market-qualified sellable
quantity.

ETF sellability uses the existing position-lot model. Units bought on the order
trade date are not sellable until a later trade date; imported lots participate
through their existing `buy_trade_date`. ETF sell proceeds are not deferred:
once a sell fills, net proceeds become available cash immediately.

Past-date ETF orders use the existing account rebuild flow so historical replay
applies the same metadata, fee, tick, daily-bar, and T+1 rules as current-date
orders.

## Matching And Validity

`MatchingService` continues to request an exact-date bar using the persisted
order market. For ETFs, the existing provider reads the ETF-specific daily
table and does not load A-share price-limit data. A limit fills only when it is
inside the ETF bar low/high range, at its limit price.

ETF matching remains in the shared fill and settlement lifecycle. Existing
market-aware fee dispatch calculates ETF commission-only fees, position/lot
operations use the order market, and ETF sells follow the existing non-HK
immediate-cash-credit path. A-share and Hong Kong Stock Connect logic remains
unchanged.

`TradeValidityService` receives a dedicated ETF daily-range branch. It records
the ETF bar low/high and produces valid or invalid range outcomes without
A-share limit-up or limit-down analysis. ETF validity records leave limit-price
and touched-limit fields unset.

When an exact-date ETF bar is unavailable, matching leaves the accepted order
unchanged and records the existing recoverable diagnostic and warning with
`market=etf`. The existing delayed retry/rebuild flow must query that
market-qualified diagnostic and may fill the order after data is available.

## Persistence And Read Paths

The persisted `market=etf` value remains the security routing contract; no
additional security-type column is added. All position, lot, frozen-quantity,
sellability, valuation, round-trip, rebuild, and deletion operations use
`(account_id, market, symbol)`, preventing collisions with an A-share that has
the same symbol.

Orders, trades, positions, validity checks, snapshots, account summaries,
valuation gaps, and daily-bar diagnostics expose `market=etf`. The existing
security-name enrichment resolves ETF names through ETF basic metadata, while
A-share and HK name resolution remain unchanged. Read-path changes are limited
to locations that still omit market-qualified identity or assume A-share
metadata.

## Error Contract

ETF metadata and order-rule failures are recorded as rejected orders with the
established rejection and validity-check behavior. The order path must preserve
distinct outcomes for invalid ETF symbol form, absent metadata, unreviewed
eligibility, unsupported ETF type, invalid exchange/listing status, invalid
lot size, invalid tick size, insufficient cash, and insufficient sellable
quantity.

Missing ETF market data is a matching-stage warning rather than an order-stage
rejection. It never falls back to A-share or fund history.

## Testing And Verification

Focused tests cover:

- Supported listed ETF acceptance and each ETF metadata rejection, including
  suffixed symbols.
- Positive 100-unit lots and CNY 0.001 tick validation.
- Buy cash reservation including ETF commission, same-date sell rejection,
  next-trading-date sell acceptance, imported-lot sellability, and immediate
  ETF sale proceeds.
- ETF daily-range matching and skip behavior without A-share limit-price
  analysis, plus missing-bar diagnostics and later retry.
- ETF market/name propagation across orders, trades, positions, validity
  checks, snapshots, account summaries, valuation gaps, and diagnostics.
- Historical ETF replay and market-collision behavior.
- A-share and Hong Kong Stock Connect regressions in changed services.

Verification runs the focused paper-trading tests first, then relevant Ruff,
mypy, and wider paper-trading tests. PostgreSQL-backed migration coverage is
run when the local test database is available; any unavailable integration
coverage is reported explicitly.
