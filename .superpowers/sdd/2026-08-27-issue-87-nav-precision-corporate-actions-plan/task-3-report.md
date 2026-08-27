# Task 3 Report

## Implementation

- Added `PaperCorporateAction` persistence with account/security identity, governed event type, UTC-aware event timestamp, idempotency key, JSON parameters and processing metadata, impact deltas, before/after quantity, cost, and cash summaries, and affected date range.
- Added repository lookup, creation, deterministic filtered listing, PostgreSQL row-locking for positions, and account-deletion cleanup.
- Registered the corporate-action ORM/table and enum in the storage model exports, governed PostgreSQL migration, SQLite startup creation path, and database export/import business registries.
- Added additive precision upgrades for cash-ledger NAV/share fields and the zero-default `rounding_residual` column. Existing values are not backfilled or rewritten by the additive column path.
- Wired PostgreSQL startup to execute the governed paper-trading migration before the remaining paper schema upgrades.

## Commands And Output

`uv run pytest test/paper_trading/storage/test_repository.py -q`

```text
........................................................................ [ 83%]
..............                                                           [100%]
86 passed in 62.46s (0:01:02)
```

`uv run ruff check storage/model/paper_trading.py storage/model/__init__.py paper_trading/storage/models.py paper_trading/storage/repository.py paper_trading/storage/enum_migration.py storage/storage_db.py`

```text
All checks passed!
```

`git diff --check`

```text
(no output)
```

`tools/run_tests.sh test/paper_trading/storage/test_corporate_action_migration.py -v`

```text
bash: warning: setlocale: LC_ALL: cannot change locale (en_US.UTF-8)
time="2026-08-27T20:18:49+08:00" level=warning msg="No services to build"
Network issue-87-nav-precision_default Creating
Network issue-87-nav-precision_default Error Error response from daemon: all predefined address pools have been fully subnetted
failed to create network issue-87-nav-precision_default: Error response from daemon: all predefined address pools have been fully subnetted
```

The named migration test file was not present in the worktree, and the PostgreSQL test runner could not start its Docker network because Docker reported that all predefined address pools were exhausted.

## Migration Evidence

- `PAPER_TRADING_ENUM_GROUPS` now declares `paper_corporate_action_type` with labels from `CorporateActionType`: `dividend`, `split`, `reverse_split`, `bonus_share`, and `rights_issue`.
- `PaperCorporateAction.__table__` is included in `_GOVERNED_TABLES`; its account foreign key causes metadata creation after `paper_accounts`.
- PostgreSQL `StorageDb.ensure_paper_trading_schema()` invokes `migrate_paper_trading_enums()` in a transaction. The existing migration machinery uses catalog existence checks, `CREATE TYPE` guards, `CREATE TABLE ... checkfirst`, and `CREATE INDEX IF NOT EXISTS` patterns for repeatable upgrades.
- SQLite startup creates `PaperCorporateAction.__table__` with `checkfirst=True` when the legacy account dependency exists.
- Cash-ledger startup adds only missing `trade_date`, widened NAV/share, and `rounding_residual` columns. The residual uses `NUMERIC(30, 24) NOT NULL DEFAULT 0`; existing rows retain their values.
- Export/import synchronization includes `paper_corporate_actions` and `paper_corporate_action_type`, with the required table/enum association in `business_enum_is_needed()`.

## Self-Review

- Repository behavior is flushed but never committed, preserving service/router transaction ownership.
- Corporate-action listing is scoped by account and ordered by `(event_at, id)`.
- Event timestamps reject timezone-less values and normalize offset-aware values to UTC.
- Account deletion removes corporate-action rows before deleting the account.
- Position locking uses `FOR UPDATE` on PostgreSQL and remains a normal deterministic lookup on SQLite.
- No service, API, frontend, documentation, plan, or specification files were modified.
- No further safe simplification was identified without changing the scoped persistence or migration behavior.

## Concerns

- PostgreSQL migration integration could not be executed in this environment because Docker could not allocate a network. The named migration test file was also absent from the worktree, so PostgreSQL legacy-preservation and second-run semantic-idempotence evidence remains unverified here.

## Independent Review Fixes

- Changed governed PostgreSQL preflight so the additive `paper_corporate_actions` table is allowed to be absent on an existing database; the migration creates its table, enum types, columns, and indexes after account dependencies are available, while still rejecting partially missing required legacy tables.
- Added the governed `CorporateActionProcessingStatus` enum (`pending`, `completed`, `failed`) and registered its PostgreSQL/export association, including the processing-status index.
- Added additive PostgreSQL widening for all persisted accounting columns on accounts, cash ledger, and account snapshots. Existing values are altered in place without backfills; `rounding_residual` retains `NUMERIC(30, 24)` and its new-column SQLite default remains zero. SQLite keeps the existing additive `ALTER TABLE ... ADD COLUMN` startup behavior and now runs cash-ledger upgrades before the no-orders early return.
- Added repository coverage for corporate-action persistence, JSON parameters and summaries, deterministic ordering, symbol/event filters, idempotency lookup, and account-deletion cleanup.
- Added `test/paper_trading/storage/test_corporate_action_migration.py` covering reduced SQLite startup, repeatability, legacy value preservation, and PostgreSQL additive migration/repeatability/enum-label assertions when `TEST_POSTGRESQL_URL` is available.

## Fix Verification

`uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_corporate_action_migration.py -q`

```text
89 passed, 1 skipped in 61.98s (0:01:01)
```

The skipped test is the PostgreSQL integration test because `TEST_POSTGRESQL_URL` is unavailable outside the Docker runner.

`uv run ruff check storage/model/paper_trading.py paper_trading/domain/enums.py paper_trading/storage/models.py paper_trading/storage/repository.py paper_trading/storage/enum_migration.py storage/storage_db.py test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_corporate_action_migration.py`

```text
All checks passed!
```

`git diff --check` and `bash -n tools/db_common.sh` passed with no output/errors.

`tools/run_tests.sh test/paper_trading/storage/test_corporate_action_migration.py -v` remains blocked before pytest starts:

```text
Network issue-87-nav-precision_default Creating
Network issue-87-nav-precision_default Error Error response from daemon: all predefined address pools have been fully subnetted
failed to create network issue-87-nav-precision_default: Error response from daemon: all predefined address pools have been fully subnetted
```

## Final Concerns

- PostgreSQL catalog-level widening, legacy preservation, rollback, and second-run semantic idempotence remain unexecuted in this environment because Docker cannot create its network. The corresponding PostgreSQL assertions are present in the new migration test for the parent controller’s scoped re-review environment.
- No service, API, frontend, documentation, plan, or specification files were modified.
