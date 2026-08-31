# Task 9 Gate Repair Report

## Status

Issue #82 Task 9 migration and schema gate repairs remain intact. The three
final-review failures were fixed without changing matching or settlement
facts.

## Changes

- Added `paper_order_events` to `tools/db_common.sh` and added an explicit
  business-table coverage test.
- Kept `paper_order_events` out of PostgreSQL's pre-enum metadata creation
  phase, including its governed foreign-key dependency boundary.
- Made reduced PostgreSQL NAV migration fixtures derive and initialize every
  native enum required by newly created metadata tables, including replay-time
  provenance and market types.
- Completed the reduced legacy lot fixture with the `cost_price` column needed
  by the existing projected-cost migration.
- Made SQLite/PostgreSQL replay parity fixtures use the same fixed UTC account
  creation timestamp and initial cash-ledger timestamp instead of two calls to
  `datetime.now()`.
- Updated unified enum-governance fixtures for the additive order-event table,
  its legacy index, and its table-level rollback semantics.
- Preserved the five pre-existing Ruff formatting changes in the working tree.
- Prevented repository replay of trade and corporate-action projection facts
  from applying their asset impact a second time after the persisted NAV
  baseline.
- Included account creation cash exactly once in historical internal cash
  queries, independent of a later or filtered creation-ledger date, while
  retaining Decimal summation.
- Replayed the proven initial baseline before historical facts without changing
  its visible timestamp, preserving imported position quantities when an
  imported lot is a partial representation of the position.

## Verification

- Focused migration, startup, rollback, repository parity, and table-list
  coverage: `103 passed`.
- Focused enum governance and matching-status coverage: `58 passed`.
- Frontend `npm run test -- --run`: `227 passed` across 18 files.
- Frontend `npm run lint`: passed.
- Frontend `npm run build`: passed.
- `uv run pre-commit run --all-files`: all hooks passed, including mypy.
- `uv run mypy`: no issues found in 234 source files.
- Full `tools/run_tests.sh`: `2361 passed, 9 skipped`.
- Replay/repository/recalculation suites after the fixes: `183 passed, 8
  skipped`.
- The three final-review focused tests all pass.

## Baseline Evidence

The following failures were reproduced unchanged at both current `HEAD`
(`ec750df`) and the issue-start implementation baseline `f7575fb`. The
earlier `0bd1122` ancestor was also confirmed as an ancestor of `f7575fb`, but
the final-review tests were not all present there; therefore `f7575fb` is the
reproducible comparison baseline for these exact assertions.

- `test_mixed_repository_stream_replays_without_cash_flow_double_count`
  (`100099` observed versus `100075` expected).
- `test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary`
  (creation cash is filtered by its legacy trade date).
- `test_postgresql_recalculation_preserves_initial_components_and_imported_holdings`
  (imported holding replay remains at quantity `2` rather than `3`).

The previous full-suite run after the Task 9 fixes contained only these three
failures. The two enum-governance rollback failures from the earlier run remain
resolved by the fixture updates.

## Root Causes And Results

- Mixed replay: repository trade and corporate-action facts carried the same
  economic state already represented by the persisted NAV stream. Replay now
  marks those adapter-level projections and applies cash/holding state without
  double-changing total assets; external deposits/withdrawals still remain the
  only share-flow events, and internal fee/corporate-action ledger rows do not
  mint or burn shares.
- Historical cash: the as-of accessor filtered out the creation ledger by
  `trade_date` and returned zero before later activity. It now starts from the
  account's Decimal `initial_cash`, excludes the matching creation ledger, and
  sums only eligible later ledger rows once.
- PostgreSQL recalculation: the builder replayed a backdated trade before an
  INITIAL event whose persisted timestamp was later, so INITIAL reset holdings
  from the imported position total to the partial imported-lot quantity. The
  selected proven baseline is now ordered first for replay, and imported lots
  remain the cost/quantity source when present while imported positions remain
  the fallback when no lot exists.

All three final-review assertions pass, including NAV/assets/share consistency,
the adjacent Decimal boundary, and imported holding quantity `3` after
recalculation.

## Mypy

The final full `uv run mypy` run reports no issues in 234 source files. The
paper-trading replay, migration, corporate-action, cash-service, and test
fixture diagnostics were resolved with type-only annotations and casts. The
missing third-party tool imports are covered by narrow `pyproject.toml`
overrides, and the Airflow override now targets the actually imported
`airflow.*` modules without an unused-config warning.

## Scope

No matching or settlement behavior was changed. Untracked `PRODUCT.md` and
`data/` were left untouched and are not part of the intended commit.

## Simplify Review

Removed an unused baseline wrapper introduced while fixing replay ordering. No
further safe simplification was identified: the changed code directly expresses
persistence and replay boundaries, and further compression would make those
facts less clear.
