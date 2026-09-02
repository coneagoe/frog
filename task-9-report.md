# Task 9 Gate Repair Report

## Status

Issue #82 Task 9 migration and schema gate repairs remain intact. The three
final-review failures were fixed without changing matching or settlement
facts.

## Changes

- Added `paper_order_event_type` and `paper_replay_time_provenance` to the
  business backup enum list. The event enum is selected for
  `paper_order_events`; replay-time provenance is selected for
  `paper_cash_ledger`, `paper_trades`, `paper_corporate_actions`,
  `paper_account_snapshots`, and `paper_order_events`.
- Added TDD coverage for the enum list, direct enum-to-table selection,
  selected-table exports, full exports, and clean-import SQL ordering.
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

- Initial TDD run: `25 passed, 7 failed`; failures confirmed the two enum
  types were absent from backup/restore selection.
- Focused backup/restore tests after implementation:
  `uv run pytest test/tools/test_db_common.py test/tools/test_db_scripts.py -q`
  (`33 passed`).
- Full tools tests: `uv run pytest test/tools -q` (`306 passed, 4 skipped`).
- `uv run pre-commit run --all-files`: all hooks passed, including mypy.
- `git diff --check`: passed.
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

For the backup/restore enum mapping change, no further safe simplification was
identified. The shared table-selection function remains the single source for
both export and clean-import enum dependency selection.

## Final Review: Same-Date Cash Flow NAV

### Change

Cash-flow NAV pricing now includes a valid trading snapshot for the same
business date when the cash flow's UTC date matches its `trade_date`. The
repository lookup otherwise remains bounded by `event_at <= occurred_at`.

Trading snapshots remain canonical at `trade_date 23:59:59.999999 UTC`, and
initial snapshot creation is unchanged.

### TDD Evidence

Added `test_same_date_cash_flow_uses_canonical_trading_snapshot_nav`, which
saves a valid July 20 trading snapshot, confirms its canonical timestamp, and
then deposits at 10:00 UTC on July 20.

- Red: the ledger used NAV `1.000000` instead of the snapshot NAV
  `1.250000`.
- Green: the regression passes after the business-date-aware lookup change and
  confirms NAV `1.250000` with share allocation `20000.000000`.

### Validation

- Passed: targeted regression test.
- Passed: `test/paper_trading/storage/test_repository.py` (`133 passed, 5
  skipped`).
- Passed: snapshot service, timestamp repair, and recalculation tests (`68
  passed, 2 skipped`).
- Passed: focused Ruff check.
- Passed: `uv run mypy` (`235` source files).
- Cash-service module: `49 passed, 8 failed`. These failures predate this
  lookup change and occur because test fixtures pass `None` or market-data
  stubs lacking `is_trade_date` to `SnapshotRecalculationService`; failure is
  before the affected assertions. The new regression supplies the required
  minimal method and passes.

### Simplify Review

No safe simplification was identified. The optional repository `trade_date`
filter and CashService UTC-date guard make the same-date exception explicit
while retaining timestamp semantics for all other flows.
