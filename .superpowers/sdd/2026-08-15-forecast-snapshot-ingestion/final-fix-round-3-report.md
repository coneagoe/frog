# Final Fix Round 3 Report: Issue #60 Forecast Snapshot Ingestion

## Scope

This round corrects PostgreSQL advisory-lock ordering during forecast snapshot
acquisition. It keeps SQLite behavior unchanged.

## Root Cause

Acquisition read completed and active rows before taking the range advisory
lock. An independent completion transaction could update the running row, hold
the advisory lock before commit, and leave acquisition observing the prior
committed running state. Acquisition then raised `StorageError` before waiting
for the completion transaction to release the lock.

## TDD Evidence

### RED

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py::test_postgresql_acquisition_waits_for_locked_completion_before_active_check -v
```

Result before production edit: failed after 10 seconds waiting for the
acquisition lock attempt. This demonstrated that acquisition raised from its
pre-lock active lookup rather than contending on the range lock.

### GREEN

The regression starts an independent transaction that acquires the same
advisory lock, flushes a completed status without committing, and waits on an
event. Acquisition signals its lock attempt, blocks, then after the completion
transaction commits it returns the completed run ID and leaves one attempt.

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py::test_postgresql_acquisition_waits_for_locked_completion_before_active_check -v
```

Result: 1 passed.

## Change

- `storage/storage_db.py`
  - Acquires the transaction-scoped PostgreSQL range advisory lock at the start
    of acquisition, before every completed or active range lookup that decides
    reuse or new-attempt creation.
  - Retains the post-active completed recheck required by SQLite's no-op lock
    behavior.
  - Completion and failure retain their existing row-read then same-range-lock
    ordering, so this change introduces no cross-range lock order.
- `test/storage/test_forecast_snapshot_enum_migration.py`
  - Adds the deterministic independent-transaction advisory-lock contention
    regression.

## Final Verification

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v
uv run pytest test/storage/test_forecast_snapshot_storage.py -v
uv run pytest test/forecast_snapshot/test_service.py test/tools/test_create_forecast_snapshot.py test/dags/test_create_forecast_snapshot_dag.py test/download/test_download_manager.py test/download/dl/test_forecast.py test/tools/test_backfill_forecast.py test/dags/test_download_forecast_daily.py test/forecast/test_forecast_ingestion_operations.py -v
uv run ruff format --check storage/storage_db.py test/storage/test_forecast_snapshot_enum_migration.py
uv run ruff check storage/storage_db.py test/storage/test_forecast_snapshot_enum_migration.py
uv run mypy storage/storage_db.py
```

Results:

- PostgreSQL forecast snapshot migration/storage: 20 passed.
- SQLite forecast snapshot storage: 11 passed.
- Snapshot service, CLI, DAG, and forecast regressions: 105 passed.
- Ruff format and lint passed.
- Mypy passed for `storage/storage_db.py`.

## Caveats

- PostgreSQL integration commands must run serially because `tools/run_tests.sh`
  owns a fixed Compose test service name.
- The full repository suite is outside this focused verification scope.
