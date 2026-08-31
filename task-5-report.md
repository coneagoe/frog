# Task 5 Order Lifecycle Fact Report

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

- `uv run pytest test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_corporate_action_service.py -q`: `140 passed`.
- `uv run pytest test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_recalculation_service.py test/paper_trading/domain/test_nav_replay.py -q`: `54 passed, 3 skipped`.
- `tools/run_tests.sh test/paper_trading/storage/test_corporate_action_migration.py -v`: `6 passed`.
- Ruff on touched lifecycle modules: passed.
- `git diff --check`: passed.

## Known Test Gap

The broad storage suite has two unrelated pre-existing failures in
`test_mixed_repository_stream_replays_without_cash_flow_double_count` and
`test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary`.
They do not exercise `PaperOrderEvent` and were left unchanged.
