# Task 9 Gate Repair Report

## Status

Issue #82 Task 9 migration and schema gate repairs are implemented. The
remaining repository failures are pre-existing and were reproduced at the
issue #82 baseline commit `f7575fb`.

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

## Verification

- Focused migration, startup, rollback, repository parity, and table-list
  coverage: `103 passed`.
- Focused enum governance and matching-status coverage: `58 passed`.
- Frontend `npm run test -- --run`: `227 passed` across 18 files.
- Frontend `npm run lint`: passed.
- Frontend `npm run build`: passed.
- `uv run pre-commit run --all-files`: formatting and Ruff passed; mypy failed
  on existing typing/import diagnostics.
- Full `tools/run_tests.sh`: `2358 passed, 9 skipped, 3 failed`.

## Baseline Evidence

The following failures were reproduced unchanged at `f7575fb`:

- `test_mixed_repository_stream_replays_without_cash_flow_double_count`
  (`100099` observed versus `100075` expected).
- `test_cash_available_as_of_internal_preserves_adjacent_decimal_boundary`
  (creation cash is filtered by its legacy trade date).
- `test_postgresql_recalculation_preserves_initial_components_and_imported_holdings`
  (imported holding replay remains at quantity `2` rather than `3`).

The final full-suite run after the Task 9 fixes contains only those three
baseline failures. The two enum-governance rollback failures from the earlier
run are resolved by the fixture updates.

## Mypy

The final full `uv run mypy` run reports 18 existing diagnostics, including
legacy `tools` third-party import stubs and pre-existing paper-trading typing
issues. The Task 9 reduced-fixture diagnostic was removed; the pre-commit
scope reports 13 remaining existing diagnostics.

## Scope

No matching or settlement behavior was changed. Untracked `PRODUCT.md` and
`data/` were left untouched and are not part of the intended commit.

## Simplify Review

No safe simplification was identified. The changed code directly expresses
schema dependency ordering and test-fixture invariants; further compression
would make the migration boundary less clear.
