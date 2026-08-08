# Rollback Dependency Classification Fix Report

## Root Cause

`_rollback()` preflights enum dependencies before altering any column. The
previous `_type_dependencies()` catalog query retained ordinary `pg_depend`
rows for the migration's own governed enum columns and their enum-typed
defaults. Consequently, a normal successful apply could never roll back:
`monitor_market` reported its two managed columns and two managed defaults as
external dependencies.

The classifier now receives the active `MonitorEnumGroup` and excludes only
dependencies that identify an exact configured `(table_name, column_name)` as
either its `pg_class` attribute dependency or its `pg_attrdef` default
dependency. All other dependencies remain reported. In particular, a view
casting to `monitor_market` remains an external dependency and causes rollback
to abort before any governed column is altered.

## Test-First Evidence

Before the production change, the focused PostgreSQL run produced one expected
failure and one pass:

```text
FAILED test_rollback_restores_exact_legacy_types_defaults_and_removes_governance
PASSED test_rollback_rejects_non_column_enum_dependency_before_drop
1 failed, 1 passed
```

The failure named managed columns and defaults as remaining dependencies. After
the change, the full module passed:

```text
TEST_POSTGRESQL_URL='postgresql://quant:quant@localhost:5432/quant' \
  uv run pytest test/monitor/storage/test_enum_migration.py -v
13 passed in 6.82s
```

This includes `test_rollback_after_normal_apply_restores_legacy_types_defaults_and_removes_governance` and
`test_rollback_rejects_non_column_enum_dependency_before_drop`.

Additional verification:

```text
uv run pytest test/tools/test_migrate_monitor_enums.py -v
8 passed in 7.48s

uv run ruff format --check monitor/storage/enum_migration.py test/monitor/storage/test_enum_migration.py
2 files already formatted

uv run ruff check .
All checks passed!

uv run mypy monitor/storage/enum_migration.py
Success: no issues found in 1 source file

git diff --check
exit 0
```

## Commit

`Fix managed enum rollback dependency classification`

## Concerns

The classifier deliberately recognizes only the migration's configured
columns/defaults in the active schema. Any enum use by a different table,
column, default, view, function, constraint, index, or other PostgreSQL object
continues to block rollback. PostgreSQL integration verification uses the local
`quant` service because `TEST_POSTGRESQL_URL` was unset in the session.
