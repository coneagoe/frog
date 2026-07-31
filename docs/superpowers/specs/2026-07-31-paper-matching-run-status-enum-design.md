# Paper Matching Run Status PostgreSQL Enum Design

## Goal

Prevent an EOD paper trading matching run that completes with recoverable warnings from failing because its terminal status cannot be persisted. The matching-run state machine will be stored as a PostgreSQL-native enum and introduced through a single explicit migration command.

## Scope

This design implements the approved work in issues #13 through #16:

- explicit PostgreSQL migration of matching-run status;
- enum-backed matching and order-replay status persistence;
- transaction-safe handling of unexpected matching persistence failures;
- rollout, backup, and restore documentation and verification.

It does not change matching, settlement, valuation, warning, retry, API success-response, or DAG scheduling semantics.

## State Model

The canonical matching-run state values remain the existing lowercase domain values:

```text
running | completed | completed_with_warnings | failed
```

The named PostgreSQL enum uses precisely these labels. SQLAlchemy maps the existing domain enum using its values, rather than its uppercase Python member names. Existing API and CLI responses continue to expose lowercase strings.

`running` is the only active state. The existing partial unique constraint continues to permit one running matching run per trade-date and scope. Each terminal state permits a subsequent matching attempt for that scope.

## Explicit Migration Command

The migration is an explicit, versioned paper-trading command rather than startup bootstrap behavior. It runs only against PostgreSQL.

Before conversion, it validates every existing matching-run status against the canonical state set. Unknown values halt the command with actionable diagnostics; the migration must not truncate, delete, coerce, or otherwise alter those rows.

For a valid legacy schema, the command creates the named enum type if necessary, changes the status column with an explicit text-to-enum cast, preserves dependent active-run index semantics, and verifies the target type and labels. It is safe to rerun after a successful conversion. SQLite remains compatible with the application model, but receives no PostgreSQL enum DDL.

The command is the only production schema writer for this conversion. Operators isolate matching writes, run and verify the migration, deploy enum-aware API and worker images, then resume Airflow matching.

## Application Behavior

Regular matching and order-deletion replay write canonical matching-run values through the same domain enum. A daily-bar or valuation-gap warning still completes the run with `completed_with_warnings`; it is persisted successfully and returned through the existing matching API/CLI contract.

Unexpected database or persistence failures at the matching API boundary cause transaction rollback before session release. Server-side logging includes safe operation context for incident response. Client responses remain safe and do not expose SQL statements, query parameters, or stack traces.

## Verification Seams

The primary behavioral seam is the existing matching API: a warning-producing matching request persists and returns `completed_with_warnings` without a 500 response.

A real PostgreSQL integration seam verifies the production-only behavior that SQLite cannot prove:

- conversion of a valid legacy text column;
- rejection and diagnostics for unknown legacy values;
- idempotent migration rerun;
- named enum labels and lowercase value round trips;
- database rejection of invalid states;
- preservation of the active-run partial uniqueness behavior.

Existing matching service, API, replay, CLI, and SQLite tests continue to cover business behavior. Export/import verification confirms that enum type dependencies are restored before matching-run data is used.

## Operations

The paper-trading documentation will define a maintenance sequence: isolate API/Celery/Airflow matching writes; run and verify the migration; deploy enum-aware services; retry the affected matching task; and validate a warning-completed run. It will state that enum labels are a compatibility contract: future labels require an explicit migration and rollout review, while label removal, renaming, and reordering are not routine application changes.

Backup and restore guidance will verify enum type creation/restoration ordering for paper-trading database export and import.

## Self-Review

- No placeholder or deferred design decisions remain.
- The state model, migration behavior, API contract, and test seams all use the same four canonical values.
- The change is limited to matching-run persistence and operations; it does not broaden into unrelated status-column conversions or a repository-wide migration framework.
