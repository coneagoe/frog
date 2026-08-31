# Task 5 Order Lifecycle Fact Report

## Regression Repair

- Rebuilds preserve append-only order events and begin each replay with a new
  accepted/reserved lifecycle boundary. Effective reservation projection uses
  the latest boundary by immutable event lineage, so old fills/releases cannot
  cancel or offset the rebuilt reservation.
- Reservation restore, cancel/reject release, and fill settlement use the
  effective event balance rather than mutable order frozen fields. Lifecycle
  idempotency keys include the replay lifecycle, allowing regenerated facts to
  coexist with original execution facts.
- Terminal historical orders do not receive synthetic accepted/reserved facts.
  Orders with unproven reservation chronology remain rejected for corporate
  action projection repair instead of receiving fabricated midnight timestamps.

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
- Fill consumes only its actual reservation portion; cancel/reject release only
  the outstanding event balance. Operational orders, trades, and acquisition
  fields remain unchanged by action projection.

## Coverage

- TDD RED: a corporate action with an UNKNOWN historical reservation did not
  reject; the regression now passes.
- Lifecycle facts: idempotency/immutability, partial fill/cancelled remainder,
  fill trade link, delete retention, and reject/release transitions.
- Corporate actions: consecutive splits, late action with frozen sell,
  rights/cash flows, HK pending behavior, and order/trade immutability.
- Migration: SQLite table creation/rerun and PostgreSQL additive migration.

## Verification

- `uv run pytest test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_ledger_rebuild_api.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_corporate_action_service.py -q`: `110 passed`.
- `uv run pytest test/paper_trading/storage/test_repository.py -q`: `124 passed, 5 skipped`; two unrelated pre-existing failures remain in mixed replay stream and adjacent decimal boundary coverage.
- `uv run pytest test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_recalculation_service.py test/paper_trading/domain/test_nav_replay.py -q`: `54 passed, 3 skipped`.
- `uv run pytest test/paper_trading/storage/test_corporate_action_migration.py -q`: `4 passed, 2 skipped`.
- Ruff on touched lifecycle modules: passed.
- `git diff --check`: passed.

## Known Test Gap

The broad storage suite has two unrelated pre-existing failures in
`test_mixed_repository_stream_replays_without_cash_flow_double_count` and
`test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary`.
They do not exercise `PaperOrderEvent` and were left unchanged.
