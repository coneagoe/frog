# Final Fix Round 2 Report: Issue #60 Forecast Snapshot Ingestion

## Scope

This round addresses the final review findings for PostgreSQL forecast snapshot
identity migration, lifecycle acquisition serialization, and complete snapshot
schema governance. SQLite acquisition behavior remains unchanged.

## Root Causes

1. Adding a PostgreSQL identity to a populated legacy `id` column did not set
   the backing sequence to the current maximum ID, so the next implicit insert
   could collide with a legacy row.
2. Acquisition made a final completed-run lookup but had no database-wide
   serialization shared with completion. A run could complete after that lookup
   and before attempt insertion.
3. The snapshot schema audit verified required fields and selected constraints,
   but did not require primary keys, generated ID behavior, exact absence of
   defaults on record fields, the referenced FK column, or runtime verification
   of the complete schema contract.

## Changes

- `storage/enum_migration.py`
  - Advances each generated snapshot ID sequence to the maximum existing ID.
  - Audits primary keys, generated IDs, exact defaults including required
    absence, exact FK source/target columns, named unique constraints, and the
    partial active-range index.
  - Applies the record-table upgrade after fresh table creation and verifies the
    full snapshot contract after migration.
- `storage/storage_db.py`
  - Uses a transaction-scoped PostgreSQL advisory lock derived from the range
    identity before a new-attempt creation, then rechecks completed and active
    rows while holding that lock.
  - Completion and failure transitions use the same lock, preventing a
    completion from interleaving between the locked recheck and flush.
- `test/storage/test_forecast_snapshot_enum_migration.py`
  - Adds regression coverage for populated legacy identities, completion after
    the final pre-lock lookup, and malformed catalog contracts.

## RED Evidence

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py::test_migration_advances_legacy_snapshot_run_identity_sequence test/storage/test_forecast_snapshot_enum_migration.py::test_postgresql_acquisition_reuses_completion_after_final_lookup test/storage/test_forecast_snapshot_enum_migration.py::test_snapshot_schema_audit_and_verify_reject_malformed_contract -v
```

Result before production edits: 12 failures.

- The populated legacy ID test failed because the generated sequence attempted
  to reuse an existing ID.
- The completion race test failed because acquisition attempted a second run
  after completion was forced immediately after the final lookup.
- Audit/verify tests exposed missing primary-key, default, FK-target, named
  constraint, and index-contract validation.

## GREEN Evidence

```bash
uv run ruff format --check storage/enum_migration.py storage/storage_db.py test/storage/test_forecast_snapshot_enum_migration.py test/storage/test_forecast_snapshot_storage.py
uv run ruff check storage/enum_migration.py storage/storage_db.py test/storage/test_forecast_snapshot_enum_migration.py test/storage/test_forecast_snapshot_storage.py
uv run mypy storage/enum_migration.py storage/storage_db.py
uv run pytest test/storage/test_forecast_snapshot_storage.py -v
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v
tools/run_tests.sh test/tools/test_db_scripts_postgresql.py -v
uv run pytest test/forecast_snapshot/test_service.py test/tools/test_create_forecast_snapshot.py test/dags/test_create_forecast_snapshot_dag.py test/download/test_download_manager.py test/download/dl/test_forecast.py test/tools/test_backfill_forecast.py test/dags/test_download_forecast_daily.py test/forecast/test_forecast_ingestion_operations.py -v
```

Results:

- Ruff formatting and lint passed.
- Mypy passed for both production modules.
- SQLite forecast snapshot storage: 11 passed.
- PostgreSQL forecast snapshot migration/storage: 20 passed.
- PostgreSQL database scripts: 4 passed.
- Snapshot service, CLI, DAG, and forecast regressions: 105 passed.

## Documentation Review

Checked `docs/database_design.md` and the Issue #60 design/plan documents. The
existing documentation already specifies migration verification and snapshot
schema governance; no documentation update was required.

## Caveats

- The full repository suite was not run. The focused SQLite/PostgreSQL storage,
  migration, db-script, service, CLI, DAG, and forecast regression coverage was
  run.
- PostgreSQL integration commands must run serially because `tools/run_tests.sh`
  owns a fixed Compose test service name. An initial parallel invocation caused
  Docker container contention; every PostgreSQL suite listed above was rerun
  serially and passed.
- PostgreSQL advisory lock key collisions are theoretically possible because the
  database function hashes the range identity. A collision only serializes two
  unrelated ranges and does not affect correctness.
