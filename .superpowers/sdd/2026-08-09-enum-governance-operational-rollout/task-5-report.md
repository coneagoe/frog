# Task 5 Report

## Status

- Complete.
- Updated only `docs/paper_trading.md` with the unified enum governance
  maintenance-window runbook.
- Preserved the existing 22-type governed inventory and existing export/import
  behavior statements.
- No test changes were needed: existing PostgreSQL export/import coverage
  already asserts restored readable labels including `bfq`, `downloaded`,
  `signal`, and `increase`.

## Runbook Coverage

- Records database, schema, revision, owner, and maintenance start time.
- Requires a full backup export plus isolated inspection and restore proof.
- Stops API/CLI automation, Airflow scheduling/workers, Celery workers, and all
  other business writers while leaving PostgreSQL running.
- Requires fail-fast dry-run JSON review before the live JSON command.
- Requires independent PostgreSQL catalog verification and the enum governance
  smoke gate before restart.
- Defines controlled restart ordering and explicit API, CLI, Airflow, Celery,
  frontend, and export label boundaries.
- Defines schema-only, non-destructive rollback and prohibits table drops or
  application-startup schema migration as rollback mechanisms.

## Test Results

- `uv run pytest test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py -v`
  - 19 passed, 4 skipped.
- `uv run pytest test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py test/tools/test_migrate_enums.py -v`
  - 28 passed, 4 skipped.
- PostgreSQL integration cases were skipped exclusively because
  `TEST_POSTGRESQL_URL` is unavailable.
- Required Ruff format and check commands passed for the enum governance scope.

## Concerns

- Runtime API, CLI, Airflow, Celery, and frontend observations remain operator
  obligations; repository contract tests do not claim live runtime verification
  for those consumers.
- The smoke gate and PostgreSQL export/import integration tests require an
  isolated database configured through `TEST_POSTGRESQL_URL`.
