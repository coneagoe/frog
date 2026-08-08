# Task 3 Report: Paper Trading Enum Governance Adapter

## Scope

Adapted the existing Paper Trading enum migration into independently callable
governance phases. The work is limited to the Paper Trading migration module
and its PostgreSQL integration tests. It does not register the adapter in the
unified coordinator and does not modify Monitor behavior.

## Implementation

- Added `PAPER_TRADING_ENUM_ADAPTER` with `preflight`, `apply`, `verify`,
  `rollback`, and result callbacks compatible with `EnumGovernanceAdapter`.
- Kept `migrate_paper_trading_enums()` as the existing compatibility wrapper;
  it now delegates to the adapter phases while retaining non-PostgreSQL,
  dry-run, missing-table, and rollback result behavior.
- Reused the existing Paper Trading preflight, enum creation, missing-table
  bootstrap, conversion, verification, and rollback helpers without importing
  or sharing Monitor migration rules.
- Retained validation for legacy values, exact defaults, ordinary indexes,
  the active matching-run partial unique index, existing enum labels,
  preconverted columns, and unmanaged enum dependencies.
- Added adapter-level PostgreSQL coverage for non-DDL preflight and the
  apply/rollback round trip. The apply assertion reads
  `completed_with_warnings` from PostgreSQL rather than deriving it from the
  migration catalog.

## Test Evidence

1. Red: `uv run pytest test/paper_trading/storage/test_enum_migration.py -k adapter -v`
   failed during collection because `PAPER_TRADING_ENUM_ADAPTER` was not
   defined.
2. Green: the same focused command collected both adapter tests and explicitly
   skipped them because `TEST_POSTGRESQL_URL` is unavailable.
3. `uv run pytest test/paper_trading/storage/test_enum_migration.py -v`
   collected 14 PostgreSQL integration tests and explicitly skipped all 14 for
   the same missing environment variable.
4. `uv run ruff format --check paper_trading/storage/enum_migration.py
   test/paper_trading/storage/test_enum_migration.py` passed.
5. `uv run ruff check paper_trading/storage/enum_migration.py
   test/paper_trading/storage/test_enum_migration.py` passed.
6. `uv run mypy paper_trading/storage/enum_migration.py` passed.

## Limitation

No PostgreSQL URL was configured in this worktree, so live enum DDL,
partial-index predicate validation, and rollback execution could not run here.

## Regression Fix

### Root Cause

Task 3 replaced the legacy `_migrate(connection, groups, ...)` orchestration
helper with full-domain adapter callbacks. The existing
`paper_trading.storage.matching_status_migration` module imports `_migrate` to
run a deliberately scoped migration containing only
`paper_matching_run_status`. Removing it caused matching-status test collection
to fail with an import error.

The matching-status caller cannot use the full Paper Trading adapter: it must
work when only `paper_matching_runs` exists, and its dry run reports whether
the single status column would be converted through
`dry_run_reports_conversion=True`.

### Fix

- Restored `_migrate` as a private compatibility helper for scoped Paper
  Trading migration callers.
- Preserved the former non-PostgreSQL, preflight, missing-table bootstrap,
  apply, verify, rollback, and `dry_run_reports_conversion` result semantics.
- Left `PAPER_TRADING_ENUM_ADAPTER` and its full-domain phase behavior
  unchanged.

### Regression Evidence

1. Before the fix, `uv run pytest
   test/paper_trading/storage/test_matching_status_migration.py -v` failed at
   collection: `matching_status_migration.py` could not import `_migrate`.
2. After the fix, the same suite collected 15 tests: 1 portable SQLite test
   passed and 14 PostgreSQL tests explicitly skipped because
   `TEST_POSTGRESQL_URL` is unavailable.
3. `uv run pytest test/paper_trading/storage/test_enum_migration.py -v`
   collected 14 PostgreSQL tests and explicitly skipped all 14 for the same
   missing environment variable.
