# Paper Trading Historical Replay Integrity

## Problem Statement

Historical A-share orders trigger a complete account replay. The replay must preserve source facts and reconstruct one coherent derived ledger. It must also be coordinated with ordinary matching so concurrent work cannot process the same account twice.

## Goals

- Preserve orders, comments, cancellations, deposits, withdrawals, and manual cash adjustments.
- Recreate trades, trade cash events, positions, lots, round trips, snapshots, valuation gaps, and matching outcomes without duplicates.
- Keep expected market-data and matching outcomes local to their orders.
- Roll back the complete rebuild on unexpected errors.
- Serialize replay and account-scoped matching with one account lock.
- Prove the order #33 historical sell semantics.

## Design

### Account Coordination

Add a repository operation that locks one paper account row for the current transaction. `rebuild_account_from` acquires this lock before clearing any derived state and holds it through replay and audit-row creation. The account-scoped matching path acquires the same lock before reading or mutating orders, cash, positions, and lots. Different accounts use different rows and remain independently processable.

The lock is a database row lock on PostgreSQL. SQLite test coverage uses the same repository seam and verifies serialized access at the service boundary; the implementation must not add a process-local lock that would fail across workers.

### Deterministic Full Replay

Retain the current full-rebuild model: clear derived account state while preserving source facts and execution history, reset replayable orders, and process accepted orders sorted by `(trade_date, order_id)`. The recorded `start_date` remains the earliest affected date for audit and triggering; it is not treated as an incremental deletion boundary.

After each historical date, generate at most one snapshot for that account and date. Repository uniqueness/upsert behavior must ensure repeated rebuilds do not create duplicate current snapshots, trades, cash events, lots, round trips, or valuation gaps. Existing execution-history rows remain preserved and new matching runs describe the replay.

### Business Outcome Isolation

Matching outcomes such as missing exact-date market data, a limit price not being touched, and suspension are expected results. They update the relevant order and matching run, then allow later dates and unrelated symbols to continue. Unexpected exceptions propagate through the transaction and trigger rollback.

### Order #33 Regression

Use a 2026-07-30 daily bar for 002558 with a range containing 28.00. Seed a buy before that date so 1,100 shares are historically mature, then place the historical sell after the date. Assert it is not rejected with `HISTORICAL_TRADE_DATE_NOT_ELIGIBLE`, fills, and leaves no residual position.

Add the complementary insufficient-matured-inventory case and assert the existing inventory or T+1 rejection code instead of the historical-date code.

## Testing Strategy

Tests exercise public service behavior through the existing repository and SQLite fixtures:

- source-fact preservation for comments, cancellation, and manual cash events;
- repeated rebuild counts and observable derived-row uniqueness;
- downstream trades, balances, positions, lots, round trips, snapshots, and valuation gaps after an early historical fill;
- isolated missing-data, untouched-limit, and suspended-symbol outcomes;
- rollback after injected matching and persistence failures;
- account-lock coordination for same-account replay/matching and independence across different accounts;
- order #33 fill and historical inventory/T+1 rejection behavior.

Tests assert external state and error codes, not helper call sequences.

## Non-Goals

- True incremental replay from `start_date`.
- A direct filled-trade import API.
- Changes to fees, lot sizes, T+1, suspension, or limit-price semantics.
- Frontend changes or full historical versions of derived ledgers.
