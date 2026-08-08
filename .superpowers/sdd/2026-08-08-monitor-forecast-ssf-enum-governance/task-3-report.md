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
