# Task 5 Corporate Action Projection Report

## Root Cause

Corporate-action projection used mutable `PaperPositionLot.remaining_quantity`,
`original_quantity`, and `cost_price` as if they were historical acquisition
facts. Replaying a later action therefore started from an already transformed
lot and could apply earlier actions again. Lot materialization also maintained
a separate running cash balance instead of using the canonical account replay.

## Fix

- `PaperPositionLot.original_quantity` and `cost_price` remain immutable
  acquisition facts.
- Corporate-action application updates only projection fields:
  `PaperPosition.total_quantity`, `PaperPosition.cost_amount`,
  `PaperPosition.frozen_quantity`, and lot `remaining_quantity`.
- Lot projection is rebuilt from imported acquisition facts and immutable buy
  trade facts, then applies each action's quantity factor only to lots that
  existed at that action timestamp.
- Later buys are created after earlier actions and are not retroactively
  scaled by those actions.
- Sell trades consume the rebuilt FIFO inventory without changing order or
  trade records.
- Corporate-action cash eligibility remains on the existing baseline plus
  cash-ledger/trade/action `NavSeriesReplay` path. The lot materializer no
  longer maintains a second `running_cash` state, preventing cash double
  counting and preserving HK pending/settlement handling.
- Frozen sell projection is rebuilt from immutable order reservation values;
  corporate actions do not mutate any order or trade fields.
- `PaperPositionLot.projected_cost_price` is an additive projection seam.
  Startup migration backfills it from immutable `cost_price` for SQLite and
  PostgreSQL legacy schemas; no order-reservation lifecycle schema is needed
  because existing order, trade, cash-ledger, and corporate-action facts
  express the replay inputs.

## Coverage

The service tests cover consecutive split factors (`x2`, then `x1.5`), late
action chains, post-action buys, multiple cost lots and partial sells, rights
cash eligibility, idempotency, chronology ambiguity, baseline rejection,
valuation gaps, recalculation ranges, rollback behavior, and full order/trade
immutability snapshots.

## Verification

- RED: new consecutive-action regression failed because the second action read
  the first action's mutable projection.
- SQLite focused tests: `43 passed, 3 skipped`.
- PostgreSQL migration suite: `5 passed`.
- Ruff check on changed Python files: passed.
- `git diff --check`: passed.
- Task 7 analytics files and matching/settlement business code were not
  modified.
