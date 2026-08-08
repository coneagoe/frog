# Index Fix Report: Monitor Forecast SSF Enum Governance

## Scope

Corrected issue #37 migration index handling after final re-review identified
that preflight incorrectly required all five managed indexes on legacy tables.

## Changes

- PostgreSQL preflight now permits absent managed indexes while still rejecting
  an existing same-named index whose table, uniqueness, key column, or
  predicate differs from the managed contract.
- Apply creates missing managed indexes after enum conversion and verifies all
  five managed indexes.
- Idempotent apply verifies existing indexes without issuing index DDL.
- Rollback keeps managed indexes as schema improvements and verifies them after
  restoring legacy column types.
- The PostgreSQL legacy fixture now starts with no managed indexes. Coverage
  asserts apply creates them, rerun retains them, rollback retains them, and a
  conflicting same-named unique index aborts before enum DDL.

## Verification

- `uv run pytest test/monitor/storage/test_enum_migration.py -v`
  - Collected 12 tests; all 12 skipped because `TEST_POSTGRESQL_URL` is
    unavailable.
- `uv run pytest test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/tools/test_migrate_monitor_enums.py -v`
  - Passed: 126 tests.
- `uv run ruff format --check monitor/domain_enums.py monitor/condition_validation.py monitor/storage/enum_migration.py monitor/monitor_target_service.py storage/model/stock_monitor_target.py storage/model/forecast_ssf_candidate.py storage/storage_db.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/storage/test_enum_migration.py test/storage/test_forecast_ssf_candidate_storage.py test/tools/test_migrate_monitor_enums.py`
  - Passed: 12 files already formatted.
- `uv run ruff check monitor storage test/monitor test/storage/test_forecast_ssf_candidate_storage.py test/tools/test_migrate_monitor_enums.py`
  - Passed.
- `uv run mypy monitor storage`
  - Passed: no issues in 46 source files.
- `git diff --check`
  - Passed.

## PostgreSQL Availability

`TEST_POSTGRESQL_URL` is unset in this environment. The database-backed
regression tests were collected and explicitly skipped; they must run in CI or
an environment that provides the PostgreSQL test URL.

## Documentation Review

Checked the approved Monitor/Forecast SSF enum governance design and plan.
Neither needs revision because they already require an explicit migration with
preflight, apply verification, idempotent reruns, and rollback. This correction
refines implementation of that existing behavior.
