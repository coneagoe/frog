# Task 1 Report: Snapshot Domain Models and Status Governance

## Outcome

Implemented immutable forecast snapshot SQLAlchemy models and PostgreSQL enum
governance for Issue #60. Snapshot records preserve all normalized provider
rows without any A-share filtering. `source_order` is zero-based per requested
provider response and is uniquely constrained by exactly `(run_id,
announcement_date, source_order)`.

## RED/GREEN Evidence

### SQLite Model Contract

RED command:

```bash
uv run pytest test/storage/test_forecast_snapshot_storage.py::test_snapshot_record_source_order_is_unique_within_a_provider_response -v
```

RED result: failed during collection with `ImportError: cannot import name
'ForecastSnapshotStatus'`, as the status enum and snapshot models did not yet
exist.

GREEN command:

```bash
uv run pytest test/storage/test_forecast_snapshot_storage.py::test_snapshot_record_source_order_is_unique_within_a_provider_response -v
```

GREEN result: `1 passed`. The duplicate insert raises `IntegrityError` for the
named record uniqueness constraint.

### PostgreSQL Enum Governance

RED command:

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v
```

RED result: `1 failed, 1 passed`. A legacy snapshot table converted status to
the new enum but did not have `uq_forecast_snapshot_running_range`; the missing
index caused the expected predicate assertion to fail.

GREEN command:

```bash
tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v
```

GREEN result: `2 passed`. The suite verifies conversion to
`forecast_snapshot_status`, labels `running`, `completed`, `failed`, the exact
partial-index predicate, rejection of `unknown`, and rollback to
`character varying(16)`.

## Final Verification

```bash
uv run pytest test/storage/test_forecast_snapshot_storage.py -v && tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v
```

Result: `1 passed` plus `2 passed`.

```bash
tools/run_tests.sh test/storage/test_storage_enum_migration.py -v
```

Result: `15 passed`.

```bash
uv run ruff format --check storage/domain_enums.py storage/model/forecast_snapshot.py storage/model/__init__.py storage/enum_migration.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py test/storage/test_storage_enum_migration.py
uv run ruff check storage/domain_enums.py storage/model/forecast_snapshot.py storage/model/__init__.py storage/enum_migration.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py test/storage/test_storage_enum_migration.py
bash -n tools/db_common.sh
```

Result: formatting and lint passed; shell syntax check exited successfully.

## Files Changed

- `storage/domain_enums.py`: added `ForecastSnapshotStatus`.
- `storage/model/forecast_snapshot.py`: added immutable run and record models,
  range/attempt constraints, and the per-announcement-date source-order
  constraint.
- `storage/model/__init__.py`: exported both models and table constants.
- `storage/enum_migration.py`: governed `forecast_snapshot_status`, created
  the managed partial index for legacy tables, and removed that index before
  enum rollback while retaining unmanaged dependency protection.
- `tools/db_common.sh`: registered snapshot tables and enum export/import
  governance.
- `test/storage/test_forecast_snapshot_storage.py`: added SQLite model
  contract coverage.
- `test/storage/test_forecast_snapshot_enum_migration.py`: added isolated
  PostgreSQL migration coverage.
- `test/storage/test_storage_enum_migration.py`: extended the existing legacy
  fixture for the new governed snapshot table.

## Self-Review

- Status labels are exactly `running`, `completed`, and `failed`; PostgreSQL
  uses named enum `forecast_snapshot_status`.
- The partial unique index covers only active `running` runs over the three
  range fields. The full attempt constraint includes those fields plus
  `attempt`.
- No mutable snapshot `updated_at` field or update helper was added.
- No mutable forecast refresh, `DownloadManager`, rolling DAG, or backfill
  command was changed.
- `tools/db_common.sh` includes both tables, the enum type, and its required
  table dependency.
- Existing Issue #60 design and implementation-plan documents already cover
  this schema. No repository documentation needed updating.

## Concerns

- The full repository suite was not run. Verification is scoped to the new
  SQLite/PostgreSQL contracts, the adjacent storage enum-migration regression
  suite, lint/formatting, and shell syntax.
