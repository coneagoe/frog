# Final Fix Report: Issue #60 Forecast Snapshot Ingestion

## Scope

This final review-fix wave changes only immutable forecast snapshot schema
governance, snapshot acquisition, and their focused tests. Existing mutable
forecast download, backfill, and rolling DAG workflows remain unchanged.

## Root Causes

1. The enum adapter converted a complete legacy snapshot table pair's status
   column and recreated only the partial running-range index. It did not add
   lifecycle/count columns, generated IDs, the range-plus-attempt constraint,
   or the record source-order constraint, so a reported successful migration
   could not support normal snapshot writes.
2. Storage acquisition performed completed-run lookup before opening its insert
   transaction. A run that completed after this lookup could be missed and a
   later attempt created.
3. Migration audit evaluated only enum columns and existing JSON checks. It did
   not represent the snapshot tables' complete schema contract.
4. The PostgreSQL db-script fixture did not require the newly governed
   `forecast_snapshot_status` enum.

## Changes

- `storage/enum_migration.py`
  - Upgrades an existing complete legacy snapshot pair transactionally by
    adding lifecycle/count columns with defaults, timestamps, generated IDs,
    the full attempt constraint, and record source-order constraint.
  - Recreates malformed named uniqueness constraints and retains exact partial
    running-range-index verification.
  - Audits and verifies the full run/record contract: required columns,
    nullability/defaults, FK, both named unique constraints, and exact partial
    index. Incomplete pairs now report
    `forecast_snapshot_schema_contract` as not ready.
  - Preserves strict pair preflight: no pair creates both tables; exactly one
    table still rejects before DDL.
- `storage/storage_db.py`
  - Moves completed-run lookup into the acquisition transaction and rechecks it
    after active-run observation, immediately before creating a new attempt.
  - Reloads a reused completed row after transaction exit to avoid returning a
    detached ORM instance.
- `test/storage/test_forecast_snapshot_enum_migration.py`
  - Proves migration of the previous complete legacy pair supports normal
    acquire, save, and complete operations and has both uniqueness constraints.
  - Proves dry-run audit reports an incomplete legacy pair.
- `test/storage/test_forecast_snapshot_storage.py`
  - Deterministically completes the existing run in the stale-read window and
    proves acquisition reuses it without inserting another attempt.
- `test/tools/test_db_scripts_postgresql.py`
  - Requires `forecast_snapshot_status` in the migrated fixture enum set.

## RED Evidence

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py::test_migration_upgrades_complete_legacy_snapshot_pair_for_storage_lifecycle test/storage/test_forecast_snapshot_enum_migration.py::test_snapshot_schema_audit_reports_incomplete_legacy_pair -v
```

Result before implementation: 2 failures.

- The legacy pair lacked `requested_date_count`, showing that enum conversion
  alone left the lifecycle schema incomplete.
- Audit returned ready for the incomplete pair because it had no snapshot
  schema-contract check.

```bash
uv run pytest test/storage/test_forecast_snapshot_storage.py::test_snapshot_acquisition_reuses_run_completed_after_initial_lookup -v
```

Result before implementation: failed because acquisition created attempt 2
after the first attempt completed in the initial-lookup race window.

## GREEN Evidence

```bash
uv run pytest test/storage/test_forecast_snapshot_storage.py -v
```

Result: 11 passed.

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v
```

Result: 10 passed.

```bash
uv run pytest test/forecast_snapshot/test_service.py test/tools/test_create_forecast_snapshot.py test/dags/test_create_forecast_snapshot_dag.py test/download/test_download_manager.py test/download/dl/test_forecast.py test/tools/test_backfill_forecast.py test/dags/test_download_forecast_daily.py test/forecast/test_forecast_ingestion_operations.py -v
```

Result: 105 passed.

```bash
tools/run_tests.sh test/tools/test_db_scripts_postgresql.py -v
```

Result: 4 passed.

```bash
uv run ruff format --check storage/enum_migration.py storage/storage_db.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py test/tools/test_db_scripts_postgresql.py
uv run ruff check storage/enum_migration.py storage/storage_db.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py test/tools/test_db_scripts_postgresql.py
uv run mypy storage/enum_migration.py storage/storage_db.py
```

Result: formatting and Ruff checks passed; mypy reported no issues in the two
changed production modules.

## Documentation Review

Checked `docs/database_design.md`, the Issue #60 design, and implementation
plan. They already describe explicit enum migration, rollback/verification,
transactional lifecycle acquisition, and the required schema constraints. No
project documentation change is needed for this corrective implementation.

## Remaining Risks

- The full repository suite was not run. Verification covers all affected
  SQLite and PostgreSQL contracts, database-script contract tests, snapshot
  service/CLI/DAG tests, and the protected mutable forecast workflow tests.
- The migration intentionally assumes legacy constraint data has no duplicate
  range-attempt or record source-order values. PostgreSQL rejects migration
  transactionally if such data exists, rather than silently altering records.
