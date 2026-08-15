# Final Fix Round 4 Report: Issue #60 Forecast Snapshot Ingestion

## Scope

This is a test-only correction. PostgreSQL production advisory-lock ordering
from round 3 is unchanged.

## Root Cause

The round-3 test signaled the coordinator immediately before calling
`pg_advisory_xact_lock` and then released the completion transaction. It proved
only that acquisition entered the wrapper, not that its PostgreSQL backend had
actually blocked on the completion transaction's exact advisory lock.

## TDD Evidence

### RED

The strengthened assertion was introduced before any production edits. A
temporary test-only mutation made acquisition's lock wrapper a no-op:

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py::test_postgresql_acquisition_waits_for_locked_completion_before_active_check -v
```

Result: failed with `acquisition never waited on completion advisory lock`.
This demonstrates that the strengthened test rejects the no-op-lock false
positive that round 3 permitted.

### GREEN

The restored wrapper records the acquiring backend PID and calls the real
production lock. The coordinator queries `pg_locks` until it finds an ungranted
advisory lock for that acquiring PID joined to a granted advisory lock with the
same PostgreSQL lock identity held by the independent completion transaction.
Only then does it release completion. No arbitrary sleeps are used.

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py::test_postgresql_acquisition_waits_for_locked_completion_before_active_check -v
```

Result: 1 passed.

## Files

- `test/storage/test_forecast_snapshot_enum_migration.py`
  - Strengthens the independent completion/acquisition race test with backend
    PID capture and `pg_locks` holder/waiter identity verification.

## Verification

```bash
uv run ruff format --check test/storage/test_forecast_snapshot_enum_migration.py
uv run ruff check test/storage/test_forecast_snapshot_enum_migration.py
uv run pytest test/storage/test_forecast_snapshot_storage.py -v
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v
```

Results:

- Ruff format and lint passed.
- SQLite forecast snapshot storage: 11 passed.
- PostgreSQL forecast snapshot migration/storage: 20 passed.

## Caveats

- The full repository suite was not run because no production behavior changed.
- PostgreSQL integration commands must run serially because `tools/run_tests.sh`
  owns a fixed Compose test service name.
