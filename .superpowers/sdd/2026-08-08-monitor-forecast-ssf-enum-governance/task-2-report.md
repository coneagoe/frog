# Task 2 Report: Monitor And Forecast SSF Migration Phases

## Changes

- Added `MONITOR_ENUM_ADAPTER`, implementing the Task 1 `EnumGovernanceAdapter` contract for the Monitor and Forecast SSF domain.
- Extracted preflight, apply, verify, rollback, and result callbacks while retaining the existing validation and DDL helpers.
- Kept `migrate_monitor_enums` as the non-public legacy CLI compatibility wrapper, delegating each operation through the adapter phases.
- Retained legacy migration behavior for PostgreSQL-only no-ops, dry runs, complete-table bootstrap, partial-table rejection, idempotency, and fully absent-table rollback.
- Added phase-level integration coverage for no-DDL preflight, successful apply, and rollback to legacy `VARCHAR` columns with condition-check removal.

## Test-First Evidence

The new adapter tests were added before adapter production code. The required red command was run:

```text
TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/monitor/storage/test_enum_migration.py -k adapter -v
ImportError: cannot import name 'MONITOR_ENUM_ADAPTER' from 'monitor.storage.enum_migration'
```

This failed during collection because the required adapter symbol did not yet exist.

## Verification Output

```text
uv run ruff check monitor/storage/enum_migration.py test/monitor/storage/test_enum_migration.py
All checks passed!

uv run ruff format --check monitor/storage/enum_migration.py test/monitor/storage/test_enum_migration.py
2 files already formatted
```

```text
TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/monitor/storage/test_enum_migration.py -v
16 skipped in 1.56s
```

Each skipped test explicitly reports `TEST_POSTGRESQL_URL is unavailable`; the PostgreSQL integration environment was not available in this workspace. No test failed.

## Self-Review

- `preflight` calls the existing `_preflight` validation and retains rejection for invalid legacy enum values, invalid condition documents, unexpected labels, incompatible column shapes/defaults/indexes, partial table presence, and condition-check conflicts.
- `apply` invokes adapter preflight before DDL, creates missing governed tables only after validation succeeds, then uses the established type conversion, condition check, and index helpers.
- `rollback` invokes adapter preflight before altering columns, retains unmanaged dependency detection, restores legacy column types/defaults/indexes, removes the condition check, and drops managed enum types.
- The legacy wrapper returns the existing `MonitorEnumMigrationResult` shape and delegates to the adapter rather than duplicating migration logic.

## Concerns

- PostgreSQL-backed behavior could not execute because `TEST_POSTGRESQL_URL` is unset. The adapter tests collect and skip as required, but a database-backed run remains necessary to establish the actual DDL and rollback outcomes.

## Coordinator Rollback Fix

- Updated `_adapter_verify` to treat rollback as verified when both governed tables are absent.
- Retained `_adapter_preflight` partial-table rejection and all non-rollback verification behavior.
- Added PostgreSQL-gated coverage for `migrate_enums(connection, rollback=True, adapters=(MONITOR_ENUM_ADAPTER,))` after dropping both governed tables.

### Command And Output

```text
TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/monitor/storage/test_enum_migration.py -k coordinator_rollback -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/monitor-enum-governance/.venv/bin/python
cachedir: .pytest_cache
rootdir: /data/frog/.worktrees/monitor-enum-governance
configfile: pyproject.toml
plugins: anyio-4.14.0
collecting ... collected 17 items / 16 deselected / 1 selected

test/monitor/storage/test_enum_migration.py::test_coordinator_rollback_is_noop_when_all_governed_tables_are_absent SKIPPED [100%]

====================== 1 skipped, 16 deselected in 0.96s =======================
```

The test skips because `TEST_POSTGRESQL_URL` is unavailable.

### Self-Review

- The coordinator always calls adapter verification after rollback. The new guard prevents `_verify` from querying absent governed tables after the rollback no-op.
- The guard requires `rollback=True` and absence of both tables, so it does not weaken apply verification or allow partially missing tables through preflight.
- The regression test uses the actual Task 1 coordinator and Monitor adapter, asserting the observable no-op result instead of invoking the adapter callbacks directly.
