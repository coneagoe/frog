# Paper Trading Market-Qualified Security Identity Design

## Scope

Issue #42 makes paper-trading security identity market-qualified for the
existing `a_share` and `hk_connect` markets. A single account may therefore
hold the same bare symbol in both markets without mixing state or analytics.

This issue does not add the `etf` market enum label, ETF metadata, fees,
trading rules, or market-data routing. Those changes remain in issue #41.

## Identity Contract

Use `(account_id, market, symbol)` as the complete security identity for all
stateful, aggregate paper-trading operations.

- Change `paper_positions` uniqueness from `(account_id, symbol)` to
  `(account_id, market, symbol)`.
- Position lookup and upsert methods require and filter on `market`.
- Position-lot lookup, sellability calculations, frozen-quantity operations,
  and closed-position cleanup filter on `market`.
- Persist `market` on position round trips and include it when creating and
  locating an open cycle. Realized PnL cannot cross markets for a shared
  symbol.
- Historical rebuild groups imported lots by `(market, symbol)`, instead of
  rejecting a symbol imported under distinct markets.

Existing records retain their current `a_share` default or existing
`hk_connect` value, so they remain readable after the change.

## Diagnostics And Valuation Gaps

Daily-bar diagnostics use `(business_date, market, symbol, adjust)` as their
identity. Add a persisted diagnostic `market` column, migrate existing rows to
`a_share`, and include it in diagnostic upserts, unresolved-diagnostic checks,
and A-share delayed-bar rebuild joins.

Keep valuation gaps unique by account and trade date. Each missing-security
entry in its structured details includes both `market` and `symbol`, so a
valuation warning and its retry path retain the proper market-data route. The
legacy `missing_symbols` list remains available for compatibility with current
responses, while the detailed reference is authoritative for market identity.

## Service Integration

Services pass the persisted market from orders, trades, lots, or positions into
the changed repository methods. This applies to order reservations, matching,
sellability, trade creation, position cleanup, historical replay, round-trip
analytics, snapshots, request-time position valuation, and market-data
diagnostics.

The existing API and CLI contracts are unchanged: order `market` remains
optional and defaults to `a_share`; explicit `hk_connect` orders continue to
use their existing behavior.

## Migration And Rollback

Extend the governed schema migration to create or verify the new position
unique constraint and diagnostic market column. Upgrade backfills existing
daily-bar diagnostics as `a_share`. Rollback restores the prior diagnostic
shape and position uniqueness only after the existing migration preflight and
dependency checks succeed.

## Tests And Acceptance

Add focused tests for:

- Schema upgrade and rollback, including the position uniqueness change and
  A-share diagnostic backfill.
- Same-symbol A-share and HK Connect holdings in one account, proving isolated
  quantities, costs, frozen inventory, sellability, lots, round trips, and
  realized PnL.
- Historical rebuild and round-trip recreation using same-symbol imported lots
  from both markets.
- Market-qualified diagnostics and valuation-gap details, including retry
  eligibility and snapshot valuation.
- Existing A-share and HK Connect order, matching, snapshot, and replay
  regressions.

Acceptance requires that same-symbol positions in distinct markets remain
independent through normal matching and historical rebuild, while existing
A-share and Hong Kong Stock Connect records and workflows remain readable and
unchanged.
