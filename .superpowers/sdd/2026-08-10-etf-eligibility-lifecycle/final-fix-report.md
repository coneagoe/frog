# ETF Eligibility Lifecycle Final Fix Report

## Scope

Addressed the two High final-review findings for issue #43 without changing
DAG schedules, task boundaries, or the public
`DownloadManager.download_etf_basic() -> bool` contract.

## Finding 1: PostgreSQL Fresh Bootstrap

Root cause: `paper_etf_eligibility` uses the governed
`paper_etf_eligibility_status` PostgreSQL enum but was omitted from
`_ENUM_GOVERNED_PAPER_TRADING_TABLES`. `Base.metadata.create_all()` could
therefore attempt to create the table before the enum migration created its
type.

Fix: Added `tb_name_paper_etf_eligibility` to the PostgreSQL bootstrap
exclusion set. `ensure_paper_trading_schema()` and its enum-governance adapter
now remain the owner of eligibility-table creation.

Regression evidence: extended
`test_postgresql_storage_startup_excludes_all_enum_governed_paper_tables` to
assert that `paper_etf_eligibility` is absent from the metadata bootstrap
selection.

## Finding 2: Atomic ETF Refresh And Reconciliation

Root cause: `save_etf_basic()` committed its replacement through the engine
before `reconcile_etf_eligibility()` started a separate ORM session. A later
reconciliation failure therefore preserved the new provider snapshot and left
eligibility state stale.

Fix: Added `StorageDb.refresh_etf_basic_and_reconcile()`. It prepares the
provider frame, deletes the old `etf_basic` rows, inserts the replacement, and
reconciles eligibility through one SQLAlchemy session transaction. The
replacement deliberately uses row deletion plus append rather than Pandas
`if_exists="replace"`: SQLite `DROP TABLE`/recreate behavior cannot provide the
rollback guarantee required by the direct transaction test. The download
manager now delegates to this method and returns its existing boolean outcome.
`save_etf_basic()` and `reconcile_etf_eligibility()` remain available for their
existing callers.

Regression evidence:

- `test_refresh_etf_basic_rolls_back_provider_and_eligibility_when_reconciliation_fails`
  uses SQLite, real provider and eligibility tables, and a forced reconciliation
  exception. It proves the original provider name and eligibility row remain
  after the atomic refresh returns `False`.
- `test_refresh_etf_basic_updates_provider_and_eligibility_together` uses SQLite
  to prove a successful replacement updates the provider row, refreshes the
  matching eligibility row, and disables the missing ETF in the same operation.
- Download-manager tests retain false-return behavior for empty input, failed
  atomic persistence/reconciliation, and provider errors.

## TDD Evidence

Red command, before production fix:

```text
uv run pytest test/storage/test_storage_db.py::test_postgresql_storage_startup_excludes_all_enum_governed_paper_tables test/storage/test_storage_db.py::test_refresh_etf_basic_rolls_back_provider_and_eligibility_when_reconciliation_fails test/storage/test_storage_db.py::test_refresh_etf_basic_updates_provider_and_eligibility_together
```

Result: `3 failed`. The bootstrap test observed `paper_etf_eligibility` in the
metadata table selection. Both atomic-refresh tests raised `AttributeError`
because `StorageDb.refresh_etf_basic_and_reconcile` did not yet exist.

First green attempt exposed a real SQLite transaction limitation: the forced
reconciliation failure returned `False`, but the prior provider table had been
removed by `if_exists="replace"`. The atomic implementation was narrowed to
`DELETE` plus `append` within the same session transaction. This is the final
minimal implementation.

Focused green command:

```text
uv run pytest test/storage/test_storage_db.py::test_postgresql_storage_startup_excludes_all_enum_governed_paper_tables test/storage/test_storage_db.py::test_refresh_etf_basic_rolls_back_provider_and_eligibility_when_reconciliation_fails test/storage/test_storage_db.py::test_refresh_etf_basic_updates_provider_and_eligibility_together test/download/test_download_manager.py -q
```

Result: `47 passed in 2.57s`.

## Verification

```text
uv run pytest test/storage/test_storage_db.py test/download/test_download_manager.py -q
177 passed, 3 skipped in 16.81s

uv run pytest test/paper_trading -q
402 passed, 38 skipped, 5 warnings in 125.55s

uv run pytest test/paper_trading/storage/test_enum_migration.py -q
24 skipped in 2.22s

uv run ruff format --check storage/storage_db.py download/download_manager.py test/storage/test_storage_db.py test/download/test_download_manager.py
4 files already formatted

uv run ruff check storage/storage_db.py download/download_manager.py test/storage/test_storage_db.py test/download/test_download_manager.py
All checks passed!

uv run mypy storage/storage_db.py download/download_manager.py
Success: no issues found in 2 source files
```

The PostgreSQL enum migration suite is skipped because its local PostgreSQL
fixtures are unavailable. The focused bootstrap-selection regression exercises
the StorageDb ordering decision directly; the existing PostgreSQL migration
tests remain the integration evidence when a PostgreSQL test database is
available.

## Documentation Review

Reviewed `docs/paper_trading.md` and the ETF eligibility lifecycle design
specification. No documentation update was required: CLI/API usage and lifecycle
policy are unchanged, while this repair is internal storage behavior.
