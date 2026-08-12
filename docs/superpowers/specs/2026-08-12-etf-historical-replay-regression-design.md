# ETF Historical Replay Regression Design

## Scope

Issue #47 verifies and completes the existing historical ETF order replay
workflow. It covers an explicit past-date ETF buy, a sell on the next open
trade date, and account rebuild-derived state. It preserves the existing
explicit ETF market selection and does not change ETF eligibility, market-data
downloads, schemas, DAG schedules, or frontend behavior.

## Design

Historical ETF orders continue through the current `OrderService` ETF path.
After ETF eligibility, 100-unit lot, CNY 0.001 tick, and open-trade-date
validation, past-date requests create accepted historical source orders and
trigger the existing account rebuild service. Rebuild replays accepted orders
in trade-date and order-ID order, restoring reservations only in the historical
ledger before applying normal matching, settlement, validity, snapshot, and
round-trip services.

The ETF replay must retain its market-qualified identity throughout. Daily bars
come exclusively from the ETF route; fees are commission-only; buy lots retain
their trade date; the later-date sell passes ETF T+1; and filled ETF sales make
net proceeds available cash immediately. Rebuilt output contains ETF-qualified
orders, trades, cash-ledger entries, snapshots, position changes, and closed
round trips without colliding with A-share or HK Connect identities.

## Testing

Add or strengthen one focused end-to-end historical ETF lifecycle test to
assert order acceptance, ETF bar routing, commission-only fees, next-date T+1
sellability, immediate cash credit, and the complete regenerated derived
records. Test data supplies exact ETF bars for the buy and sell dates and uses
a supported ETF eligibility record.

Run the corresponding historical A-share and HK Connect matching/replay tests
as regressions. The change remains test-only unless those acceptance assertions
reveal an implementation defect, in which case the smallest fix belongs in the
existing replay, matching, or market-data path.

## Verification

Run the focused paper-trading service tests first, then Ruff and the wider
paper-trading test suite as practical. Report any unavailable PostgreSQL-backed
coverage explicitly.
