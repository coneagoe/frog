# Task 4 Report: Unified Storage Enum Governance Coverage

## Scope

- Modified `test/storage/test_enum_governance.py`.
- Added the three Storage legacy tables to the unified PostgreSQL fixture.
- Added coverage showing invalid Storage `provider_outcomes` preflight blocks all adapter DDL in the shared transaction.
- Confirmed `docs/superpowers/specs/2026-08-08-blackroom-diagnostic-ssf-enum-design.md` already states "five named scalar types" at lines 25-26 and 76; no wording edit was necessary.

## Commands And Outcomes

| Command | Outcome |
| --- | --- |
| `uv run pytest test/storage/test_enum_governance.py -q` | Passed: 7 passed, 3 skipped. PostgreSQL integration cases skipped because `TEST_POSTGRESQL_URL` is unavailable. |
| `uv run pytest test/storage/test_enum_governance.py test/storage/test_enum_migration.py test/storage/test_blackroom_storage_db.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q` | Failed: 240 passed, 12 skipped, 1 failed. `test_postgresql_migrates_legacy_global_idempotency_index_to_account_scope` attempts to create `daily_bar_diagnostics` with PostgreSQL native enum `daily_bar_diagnostic_adjust` before the Storage enum type exists. This path is in `StorageDb.ensure_paper_trading_schema`, outside Task 4 scope. |
| `uv run ruff format --check storage paper_trading test && uv run ruff check storage paper_trading test && uv run mypy` | Format and lint passed. Mypy failed with pre-existing missing annotation: `storage/model/ssf_change_signal.py:41: Need type annotation for "status"`. |
| `uv run pytest test` | Failed during collection: `test/paper_trading/storage/test_enum_migration.py` and `test/storage/test_enum_migration.py` share module name `test_enum_migration` under the current pytest import mode. No tests ran after collection stopped. |

## Self-Review

- The fixture models each Storage governed table using the Task 3 legacy column forms and defaults.
- The new test inserts only an invalid Storage JSON status and asserts the Paper Trading, Monitor, and Storage scalar columns all remain legacy `VARCHAR` types after unified migration raises `EnumGovernanceError` for `storage`.
- The existing managed-type helper already includes `STORAGE_ENUM_GROUPS`; the existing default adapter order assertion already includes `storage`.
- No production code changed. No unrelated worktree changes were modified.

## Commit

- Commit SHA: `cca850f` (`Verify storage enum governance`)

## Concerns

- PostgreSQL integration evidence for the new atomicity test is unavailable without `TEST_POSTGRESQL_URL`.
- The required focused set has one existing PostgreSQL schema-bootstrap failure described above.
- The full suite is blocked by duplicate test module basenames during collection.
- Mypy is blocked by the existing unannotated SQLAlchemy model attribute described above.

## P1 Follow-up: PostgreSQL Bootstrap Ownership Repair

### Scope

- Kept the Task 4 coverage commit `cca850f`; did not rewrite or discard it.
- Made the unified Storage enum adapter exclusively responsible for creating Storage-governed tables on PostgreSQL.
- Preserved SQLite creation paths and PostgreSQL legacy Blackroom `remaining_days` upgrades.
- Added an explicit legacy PostgreSQL schema regression test for `ensure_paper_trading_schema` and extended startup metadata exclusion coverage.
- Strengthened atomic preflight coverage to assert no managed enum types or Storage JSON-check constraints remain after Storage preflight rejects invalid JSON.
- Extended fake unified migration sequencing to include all three adapters before apply.
- Added the compatible explicit `Any` annotation for `SSFChangeSignal.status`, resolving the full mypy failure.

### Red And Green Evidence

| Command | Outcome |
| --- | --- |
| `uv run pytest test/storage/test_storage_db.py::test_postgresql_paper_schema_upgrade_leaves_diagnostics_to_storage_enum_adapter -q` | Red: failed with `psycopg2.errors.UndefinedObject: type "daily_bar_diagnostic_adjust" does not exist`; `ensure_paper_trading_schema()` called `DailyBarDiagnostic.__table__.create()` before the Storage adapter created types. |
| `uv run pytest test/storage/test_storage_db.py::test_postgresql_paper_schema_upgrade_leaves_diagnostics_to_storage_enum_adapter -q` | Green: 1 passed after PostgreSQL stopped creating `DailyBarDiagnostic` through native metadata. |
| `uv run pytest test/storage/test_storage_db.py::test_postgresql_storage_startup_excludes_all_enum_governed_paper_tables -q` | Red: failed because PostgreSQL metadata startup included `blackroom_records`, `daily_bar_diagnostics`, and `ssf_change_signals`. |
| `uv run pytest test/storage/test_storage_db.py::test_postgresql_storage_startup_excludes_all_enum_governed_paper_tables test/storage/test_storage_db.py::test_postgresql_paper_schema_upgrade_leaves_diagnostics_to_storage_enum_adapter -q` | Green: 2 passed after excluding all Storage adapter tables from PostgreSQL metadata creation. |
| `uv run pytest test/storage/test_storage_db.py::test_postgresql_paper_schema_upgrade_leaves_diagnostics_to_storage_enum_adapter test/storage/test_enum_governance.py -q` | 9 passed, 3 skipped. PostgreSQL unified atomicity integration cases skip only when `TEST_POSTGRESQL_URL` is unavailable. |
| `uv run pytest test/storage/test_enum_governance.py::test_atomic_migration_prevents_all_conversion_when_storage_json_is_invalid -q` | Skipped because `TEST_POSTGRESQL_URL` is unavailable in this workspace. |
| `uv run pytest test/storage/test_enum_governance.py test/storage/test_enum_migration.py test/storage/test_blackroom_storage_db.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py test/tools/test_migrate_enums.py -q` | Passed: 249 passed, 12 skipped. This includes live PostgreSQL legacy bootstrap behavior and the migration command unit coverage. |
| `uv run ruff format --check storage paper_trading test && uv run ruff check storage paper_trading test && uv run mypy` | Passed: 196 files already formatted; all Ruff checks passed; mypy found no issues in 152 source files. |
| `uv run pytest test` | Blocked during collection by the pre-existing duplicate basename `test_enum_migration.py` in `test/paper_trading/storage/` and `test/storage/`. Global pytest import mode was not changed. |

### Self-Review

- PostgreSQL startup no longer creates any Storage adapter table through `Base.metadata.create_all`, `ensure_blackroom_records_table`, or `ensure_paper_trading_schema` before `tools/migrate_enums.py` can obtain storage and invoke `migrate_enums`.
- Fresh PostgreSQL Storage tables are created by `STORAGE_ENUM_ADAPTER.apply`; legacy existing tables remain available for adapter preflight/conversion, while Blackroom legacy `remaining_days` upgrades remain supported.
- The regression test uses a live isolated PostgreSQL schema and proves both the existing paper index migration and absence of `daily_bar_diagnostics`; it tests behavior rather than merely asserting a mocked method call.
- The default three-adapter sequencing test proves preflight completes for Paper Trading, Monitor, and Storage before any apply phase starts.
- No global pytest configuration was changed; the known duplicate-basename collection problem remains reported.

### Commit

- Commit SHA: `bd132ff` (`Fix storage enum bootstrap ordering`)

### Remaining Concerns

- `uv run pytest test` remains un-runnable until the repository resolves duplicate `test_enum_migration.py` module names or adopts a deliberate import-mode change; that unrelated global configuration was intentionally not changed.
- New atomicity integration assertions require `TEST_POSTGRESQL_URL`; where unavailable, they skip as designed.

## Final Whole-Branch Review Fix Wave

### Scope

- Kept PostgreSQL SSF startup from creating `SSFChangeSignal` before the unified Storage adapter creates its enum type and governed table.
- Replaced function-backed Storage JSON checks with self-contained PostgreSQL `jsonb_typeof` and JSONPath `NOT EXISTS`-equivalent predicates; migration no longer creates, validates, or drops helper functions.
- Restored the persisted diagnostic classification `resolved` and matching-service output, while retaining scalar and JSON validation.

### Red And Green Evidence

| Command | Outcome |
| --- | --- |
| `uv run pytest test/paper_trading/storage/test_repository.py::test_daily_bar_diagnostic_scalar_columns_use_value_enums test/paper_trading/services/test_matching_service.py::test_matching_fill_resolves_historical_retry_diagnostic -q` | Red: 2 failed. `resolved` was absent from `DailyBarDiagnosticClassification`; matching persisted `downloaded`. |
| `uv run pytest test/storage/test_enum_migration.py::test_json_checks_remain_enforced_after_legacy_validator_functions_are_replaced test/storage/test_storage_db.py::test_postgresql_ssf_startup_leaves_table_creation_to_storage_enum_adapter -q` | Red: SSF startup failed with `psycopg2.errors.UndefinedObject` because `ssf_change_signal_status` did not exist. The JSON integration case skipped because `TEST_POSTGRESQL_URL` is unset. |
| `uv run pytest test/paper_trading/storage/test_repository.py::test_daily_bar_diagnostic_scalar_columns_use_value_enums test/paper_trading/services/test_matching_service.py::test_matching_fill_resolves_historical_retry_diagnostic -q` | Green: 2 passed. |
| `uv run pytest test/storage/test_enum_migration.py::test_json_checks_remain_enforced_after_legacy_validator_functions_are_replaced test/storage/test_storage_db.py::test_postgresql_ssf_startup_leaves_table_creation_to_storage_enum_adapter -q` | Green: 1 passed, 1 skipped. The live isolated-schema SSF test proved startup leaves no table or type and `migrate_storage_enums` creates both. |
| `uv run pytest test/storage/test_enum_governance.py test/storage/test_enum_migration.py test/storage/test_blackroom_storage_db.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_matching_service.py test/storage/test_storage_db.py test/tools/test_migrate_enums.py -q` | Passed: 280 passed, 12 skipped. |

### Verification Notes

- The direct JSON checks reject non-arrays, invalid element types, missing/null provider statuses, and unrecognized provider status or SSF event labels without calling schema helper functions. The PostgreSQL-native `jsonb_path_exists` predicate is necessary because PostgreSQL disallows subqueries directly inside `CHECK` expressions.
- Legacy same-name helper functions returning `true` cannot weaken the direct checks; the regression creates both functions after migration and verifies invalid direct inserts still fail.
- The enum migration now includes four classification labels: `missing_market_data`, `missing_exact_date`, `downloaded`, and `resolved`.

## P1 Follow-Up: Legacy PostgreSQL SSF Status Upgrade

### Scope

- Preserved PostgreSQL adapter ownership when `ssf_change_signals` is absent.
- Restored the existing `status VARCHAR(20) NOT NULL DEFAULT 'signal'` upgrade when a PostgreSQL legacy SSF table exists without that column.
- Added isolated PostgreSQL coverage proving no ORM SSF table creation occurs before the Storage adapter preflights and converts the legacy table.

### Red And Green Evidence

| Command | Outcome |
| --- | --- |
| `TEST_POSTGRESQL_URL='postgresql://quant:quant@localhost:5432/quant' uv run pytest test/storage/test_storage_db.py::test_postgresql_ssf_startup_upgrades_existing_legacy_table_before_storage_migration -q` | Red: failed with `sqlalchemy.exc.NoResultFound` because unconditional PostgreSQL return left `status` absent. |
| `TEST_POSTGRESQL_URL='postgresql://quant:quant@localhost:5432/quant' uv run pytest test/storage/test_storage_db.py::test_postgresql_ssf_startup_leaves_table_creation_to_storage_enum_adapter test/storage/test_storage_db.py::test_postgresql_ssf_startup_upgrades_existing_legacy_table_before_storage_migration -q` | Green: 2 passed. |
| `uv run pytest test/storage/test_storage_db.py::TestSSFChangeSignalStorage test/storage/test_enum_migration.py -q` | Passed: 10 passed, 9 skipped. |

## Final Test Collection Regression Repair

### Root Cause And Scope

- `uv run pytest test` failed during collection because the newly introduced `test/storage/test_enum_migration.py` shared the unqualified module name `test_enum_migration` with the pre-existing Paper Trading module under the repository's current pytest import mode.
- Renamed only the newly introduced Storage module to `test/storage/test_storage_enum_migration.py`.
- Did not change pytest import configuration or the existing Paper Trading test filename.

### Red And Green Evidence

| Command | Outcome |
| --- | --- |
| `uv run pytest test` | Red: collection failed with an import-file mismatch. Pytest imported `test_enum_migration` from `test/paper_trading/storage/test_enum_migration.py` and then rejected `test/storage/test_enum_migration.py`. |
| `uv run pytest test/storage/test_storage_enum_migration.py -q` | Green: 9 skipped because `TEST_POSTGRESQL_URL` is unavailable; the renamed module collected successfully. |
| `uv run pytest test` | Green: 1354 passed, 69 skipped, 6 existing FastAPI/Starlette/AnyIO deprecation warnings. |
| `uv run ruff format --check . && uv run ruff check .` | Green: 410 files already formatted; all Ruff checks passed. |

### Concerns

- Storage enum migration integration cases remain skipped without `TEST_POSTGRESQL_URL`.
- The full suite retains six third-party FastAPI/Starlette/AnyIO deprecation warnings.
