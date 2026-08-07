# Matching Run Enum Startup Governance Design

## Goal

Make PostgreSQL matching-run enum creation and conversion an explicit operator action. Normal application startup must neither create nor alter the `paper_matching_run_status` enum, while preserving the existing matching-run API, CLI, and Airflow behavior, including `completed_with_warnings`.

## Scope

- Provide one operator-only bootstrap command for the matching-run status storage contract.
- Prevent normal `StorageDb` initialization from issuing PostgreSQL DDL for `paper_matching_runs` or `paper_matching_run_status`.
- Support a fresh PostgreSQL database and a legacy varchar-based matching-run table.
- Preserve the existing active-run partial unique index and verify its shape after bootstrap.
- Add PostgreSQL integration coverage for explicit bootstrap and startup non-mutation.

No change is made to matching logic, HTTP response schemas, CLI response rendering, DAG schedules, retries, or task boundaries.

## Bootstrap Command

`tools/bootstrap_paper_matching_run_status.py` is the sole operator entry point for this vertical slice. It accepts `--dry-run` and `--json`, initializes repository configuration, and operates in one database transaction.

For a missing `paper_matching_runs` table, live bootstrap creates the matching-run table with its canonical columns and the active-run partial unique index, then creates and verifies `paper_matching_run_status` with the canonical labels:

- `running`
- `completed`
- `completed_with_warnings`
- `failed`

For an existing table, the command delegates status-column validation, enum conversion, label validation, and index validation to `migrate_paper_matching_status_enum`. Legacy values outside the canonical set, an enum with different labels, or a missing or malformed active-run partial index cause a clear failure and roll back the transaction.

Dry-run reports whether the table exists, whether conversion would be required, the expected labels, observed legacy values, and index readiness. It executes no DDL or DML.

Repeated successful live bootstrap calls are idempotent: they leave a conforming enum-backed table and partial index intact and report that conversion was not needed.

## Startup Boundary

`StorageDb.__init__` continues to initialize non-paper-trading metadata and existing schema compatibility checks. It must exclude matching-run table and enum DDL from `Base.metadata.create_all` and must not call an alternative helper that creates or changes them.

The application assumes an operator has bootstrapped matching-run storage before a workflow writes matching runs. A missing or incompatible matching-run schema is an operational configuration error surfaced by the normal database operation; startup does not repair it.

The ORM retains the native `MatchingRunStatus` mapping so established matching operations persist and return canonical status values after bootstrap. `completed_with_warnings` remains a valid persisted terminal value, and APIs, CLI output, and Airflow-operated matching retain their existing behavior.

## Error Handling

- Bootstrap rejects unknown legacy statuses before any schema conversion.
- Bootstrap rejects an unexpected existing enum label set rather than extending the type automatically.
- Bootstrap rejects an invalid active-run partial unique index rather than dropping and recreating an unverified index.
- A failed bootstrap transaction leaves the pre-existing table, enum, rows, and index unchanged.
- Normal startup does not attempt recovery through enum or matching-run DDL.

## Verification

PostgreSQL integration tests, enabled by `TEST_POSTGRESQL_URL`, will prove:

- Dry-run reports table and readiness facts without writes.
- A fresh bootstrap creates the canonical table, enum, labels, and partial unique index.
- A legacy varchar status column converts safely, rejects unknown values, and preserves the partial unique-index behavior.
- A second live bootstrap is idempotent.
- Application startup leaves PostgreSQL enum catalog entries unchanged for the matching-run type.

Focused service, API, CLI, and Airflow-adjacent matching tests will continue to verify persistence and returned canonical `completed_with_warnings` statuses. Focused checks include Ruff formatting and linting, mypy for changed typed modules, and `git diff --check`. PostgreSQL integration tests remain a required gate for issue closure and may not be replaced by skipped tests.
