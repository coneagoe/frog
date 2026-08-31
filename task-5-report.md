# Task 5 Order Lifecycle Fact Report

## Regression Repair

- Rebuilds preserve append-only order events and begin each replay with a new
  accepted/reserved lifecycle boundary. Effective reservation projection uses
  the latest boundary by immutable event lineage, so old fills/releases cannot
  cancel or offset the rebuilt reservation.
- Replay lifecycle creation now copies the reservation from the current
  effective epoch. The copied reservation is its remaining balance after
  lifecycle fills/releases, so a partial fill only restores the unfilled cash
  and quantity rather than the original order amount.
- Reservation restore, cancel/reject release, and fill settlement use the
  effective event balance rather than mutable order frozen fields. Lifecycle
  idempotency keys include the replay lifecycle, allowing regenerated facts to
  coexist with original execution facts.
- Terminal historical orders do not receive synthetic accepted/reserved facts.
  Orders with unproven reservation chronology remain rejected for corporate
  action projection repair instead of receiving fabricated midnight timestamps.
- PostgreSQL enum migration treats `paper_order_events` as an additive
  governed table, permits it to be absent during preflight, creates it with
  the native `paper_order_event_type` and its event-type index, reruns
  idempotently, and drops it before rollback enum dependency checks.

## Scope

- Added append-only `PaperOrderEvent` facts for accepted, reserved, fill,
  cancel, reject, and release transitions, including ordered UTC timestamps,
  deltas, market/symbol, order and optional trade links, and per-account
  idempotency keys.
- Added additive SQLite/PostgreSQL schema migration coverage and repeatable
  startup creation for `paper_order_events`.
- Corporate-action frozen projection now derives the outstanding sell
  reservation and its action-time factor from lifecycle facts, never from
  mutable `PaperOrder.frozen_quantity`.
- Historical order paths record UNKNOWN provenance without inventing midnight
  chronology. Corporate-action application rejects a pending reservation whose
  accepted/reserved ordering cannot be proven; existing historical matching
  replay remains operational.
- Fill consumes only its actual reservation portion, including quantity for
  buys and sells; cancel/reject release only the outstanding event balance.
  `filled_quantity` is derived from the same balance, preserving completed
  quantity through partial-fill rebuild and terminal transitions. Operational
  orders, trades, and acquisition fields remain unchanged by action projection.

## Coverage

- TDD RED: repeated replay lifecycle creation copied the first reservation
  rather than the current epoch reservation; the regression now passes.
- TDD RED: PostgreSQL enum preflight treated the additive order-event table as
  a partially missing governed table, and rollback retained its enum
  dependencies; both migration regressions now pass.
- Lifecycle facts: idempotency/immutability, partial fill -> rebuild ->
  remaining fill, partial fill -> rebuild -> cancel/reject, fill trade link,
  delete retention, and reject/release transitions.
- Corporate actions: consecutive splits, late action with frozen sell,
  rights/cash flows, HK pending behavior, and order/trade immutability.
- Migration: SQLite table creation/rerun and a real PostgreSQL pre-Task5
  schema installation/rerun assertion for `paper_order_events`, native enum,
  and index.

## Verification

- New behavior TDD: the partial-fill rebuild test first failed with a
  100-unit replay trade; it now passes with one 60-unit trade and cumulative
  `filled_quantity=100`. The cancel/reject cases pass with a 60-unit release
  and `filled_quantity=40`.
- `uv run pytest test/paper_trading/services/test_order_delete_service.py
  test/paper_trading/services/test_matching_service.py
  test/paper_trading/services/test_order_service.py -q`: `144 passed`.
  This includes `test_replay_rejected_order_reconsidered_on_later_delete`;
  the failure was lifecycle replay funding residue: a near-zero effective
  cash balance (`1E-12`) prevented the intended insufficient-cash rejection.
  Replay cash is now normalized at the lifecycle projection boundary.
- `uv run pytest test/paper_trading/storage/test_repository.py
  test/paper_trading/services/test_corporate_action_service.py
  test/paper_trading/storage/test_corporate_action_migration.py -q`:
  `162 passed, 7 skipped, 2 broad storage failures` after the lifecycle tests.
- `tools/run_tests.sh test/paper_trading/storage/test_enum_migration.py test/paper_trading/storage/test_corporate_action_migration.py -q`:
  `44 passed`.

## Known Test Gap

The broad storage command `uv run pytest test/paper_trading/storage/test_repository.py -q`
has two established failures, reproduced after this change:
`test_mixed_repository_stream_replays_without_cash_flow_double_count` and
`test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary`.
They do not exercise `PaperOrderEvent`.

The two broad storage failures are reproducible relative to the `f7575fb`
baseline and are outside the lifecycle path:
`test_mixed_repository_stream_replays_without_cash_flow_double_count` is a
NavSeries replay expectation, and
`test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary` is an
as-of cash precision expectation. They were not changed because Task 5 does
not own analytics replay or general cash precision. The lifecycle failure
`test_replay_rejected_order_reconsidered_on_later_delete` is fixed and is not
classified as preexisting.

Lifecycle boundaries: `PaperOrder.quantity`, filled trade quantities, trade
prices/amounts/fees, and base lot acquisition facts remain immutable. Replay
updates mutable order status, cumulative `filled_quantity`, and projected
remaining reservation fields. Corporate-action projection may update mutable
position/order projections, but never rewrites order/trade/acquisition facts.
