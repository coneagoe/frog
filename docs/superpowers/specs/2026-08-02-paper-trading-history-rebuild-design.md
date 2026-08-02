# Paper Trading Historical Ledger Rebuild

## Problem Statement

When a paper order's exact trade-date BFQ daily bar is unavailable, matching
leaves the order accepted and records an unresolved daily-bar diagnostic. A
later stock-history download can supply that bar, but the current daily matching
only processes its own business date. The order therefore remains unfilled.

Directly matching the historical order later is insufficient: it can change the
account's historical cash, positions, position lots, round trips, and snapshots
after later orders have already been matched.

## Solution

After a successful A-share history download, identify accepted A-share orders
with unresolved missing-exact-date BFQ diagnostics whose trade-date BFQ bars
are now available. For each affected account, rebuild the current derived
ledger from its earliest eligible order date.

The rebuild preserves original orders, manual cancellations, deposits,
withdrawals, and manual cash adjustments as source facts. It removes and
recreates derived trades, trade-generated cash events, positions, position
lots, round trips, snapshots, valuation gaps, and matching outcomes in the
rebuild range. It replays orders by trade date and order ID, using exact-date
market data and existing matching rules.

## User Stories

1. As a paper trading account holder, I want an order delayed solely by missing
   trade-date market data to be reconsidered after that data is downloaded, so
   that a valid historical order is not permanently stranded.
2. As a paper trading account holder, I want later holdings and cash balances to
   reflect an automatically backfilled historical fill, so that my current
   ledger is internally consistent.
3. As a paper trading account holder, I want orders that did not touch their
   limit price to remain accepted after a rebuild, so that an unavailable bar is
   not confused with a price that was not reached.
4. As a paper trading account holder, I want a previously missing-data
   diagnostic resolved as soon as its exact-date BFQ bar is readable, so that
   it is not selected for endless future backfills.
5. As a paper trading account holder, I want a suspended symbol rejected during
   replay under the normal suspended-symbol rule, so that delayed data does not
   bypass market restrictions.
6. As a paper trading account holder, I want manual order cancellations retained
   through a historical rebuild, so that cancelled orders are never revived.
7. As a paper trading account holder, I want deposits, withdrawals, and manual
   cash adjustments retained through replay, so that account funding history is
   not changed by a market-data repair.
8. As an operator, I want each account rebuild to be atomic, so that an
   unexpected error cannot leave a partially reconstructed account ledger.
9. As an operator, I want a lightweight rebuild audit record, so that I can see
   which account and date range were reconstructed without retaining duplicate
   versions of all derived data.
10. As an operator, I want normal missing-data and limit-not-touched outcomes to
    remain business outcomes, so that one unavailable symbol does not prevent
    independent orders from replaying.
11. As an operator, I want historical matching-run and trade-validity records
    preserved, so that I can audit what occurred before a ledger rebuild.
12. As an operator, I want the download DAG to surface an unexpected rebuild
    failure, so that Airflow retry and alert behavior remains available.
13. As a developer, I want rebuild work serialized per paper trading account and
    coordinated with date/account matching runs, so that concurrent workers
    cannot double-apply an order or corrupt reservations.
14. As a developer, I want derived data stored only for the current ledger
    version, so that repeated historical repairs do not multiply storage use.

## Implementation Decisions

- The daily stock-history DAG is the integration seam. It triggers historical
  ledger rebuild only after the associated history download has completed
  successfully.
- The existing order-replay service is the service seam. Extend its account
  replay capability rather than introduce a second ledger reconstruction path.
- Eligible trigger orders must be accepted A-share orders with an unresolved
  BFQ missing-exact-date daily-bar diagnostic and a now-readable exact-date BFQ
  bar. Accounts are grouped and replay starts at the earliest eligible order
  date per account.
- The replay baseline is derived state strictly before the rebuild start date.
  From that date onward, the system deletes and rebuilds derived trades,
  trade-generated cash events, positions, position lots, round trips, snapshots,
  valuation gaps, and matching outcomes.
- Original order inputs, manual cancellations, deposits, withdrawals, and
  manual cash adjustments are source facts. Non-cancelled orders in the replay
  range return to pending matching state before replay.
- Replay order is ascending trade date, then ascending order ID. Existing
  matching semantics remain authoritative: suspended symbols are rejected,
  price-not-touched orders remain accepted, and still-missing exact-date market
  data remains accepted with an unresolved daily-bar diagnostic.
- A readable exact-date BFQ bar resolves its missing-data diagnostic regardless
  of whether the order fills.
- Each account rebuild locks its account and runs in one transaction. Unexpected
  application or database errors roll back the complete rebuild. Missing data,
  suspension, and untouched prices are expected business outcomes.
- Existing paper matching runs and trade-validity checks remain historical
  execution facts. Replay creates new matching runs using the existing
  date/account active-run lock; historical run records are not rewritten.
- Add a lightweight ledger-rebuild audit record containing account, rebuild
  start date, triggering orders or diagnostics, deleted and regenerated record
  counts, status, completion timestamp, and error details. The audit record
  must not duplicate trade, cash-event, or snapshot rows.
- The system retains one current derived ledger only; it does not retain a full
  pre-rebuild derived-ledger version.

## Testing Decisions

- The principal integration test exercises the daily stock-history completion
  seam and asserts observable account-ledger results, not implementation calls.
- Service tests extend the existing order-replay and matching-service patterns
  to prove replayed trades, cash, positions, lots, round trips, and snapshots
  reflect date-then-ID order processing.
- Tests must cover a missing daily bar later supplied by download, a downstream
  trade and snapshot affected by the new fill, a readable but untouched limit
  order whose diagnostic resolves, suspended-symbol rejection, retained manual
  cancellation and manual cash events, and a still-missing independent order.
- Tests must prove that an unexpected replay or persistence error rolls back all
  changes, leaving the prior ledger intact.
- Concurrency tests must demonstrate that overlapping rebuild and matching work
  for the same account cannot double-process orders, while different accounts
  remain independently processable.

## Out of Scope

- Retaining complete historical versions of trades, cash events, positions,
  lots, or snapshots for every rebuild.
- Rewriting or deleting historical matching-run or trade-validity records.
- New user-facing APIs or frontend pages for initiating ledger rebuilds.
- Backfilling orders that have no unresolved missing-exact-date BFQ diagnostic.
- Altering A-share suspension, T+1, limit-price, fee, or normal order-cancel
  rules.

## Further Notes

The feature replaces the previous conservative proposal that skipped historical
orders when later matching, trades, or snapshots existed. A full account replay
was explicitly selected so the current ledger is correct after delayed market
data becomes available. The lightweight audit record keeps storage growth
proportional to rebuild count rather than to all reconstructed ledger rows.
