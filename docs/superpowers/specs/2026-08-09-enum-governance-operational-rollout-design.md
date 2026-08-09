# Enum Governance Operational Rollout Design

## Purpose

Complete issue #40 by making the unified enum migration preflight an
operator-auditable report, documenting one executable maintenance-window
procedure, and adding focused smoke coverage for every affected business writer.
The rollout preserves existing canonical string labels at all public boundaries
and does not change normal application startup or migration semantics.

## Scope

The governed domains are Paper Trading, Monitor and Forecast SSF, and Storage.
The supported operator interface remains:

```bash
uv run tools/migrate_enums.py --dry-run --json
uv run tools/migrate_enums.py --json
uv run tools/migrate_enums.py --rollback --json
```

No second audit command is introduced. SQLite continues to enforce portable
application validation; PostgreSQL remains the authority for native enum and
JSON CHECK enforcement.

## Architecture

`storage.enum_governance` remains the single coordinator. Each existing domain
adapter keeps its preflight, apply, verify, rollback, and result responsibilities
but exposes preflight facts through its result data. The coordinator aggregates
those facts without performing any DDL in dry-run mode.

Each reported enum group includes:

- domain name and PostgreSQL type name;
- every governed table and column;
- the canonical expected labels, in enum order;
- distinct observed legacy or enum values for each selected column;
- current column type, default, and managed index state where applicable;
- associated JSON CHECK name and readiness where the domain owns one;
- dependency findings relevant to conversion or rollback; and
- an explicit ready/not-ready result with a diagnostic reason.

The JSON report is additive to the current result shape. Human-readable output
may remain concise, but the JSON output is the maintenance record. Preflight
still rejects invalid legacy values, incompatible types, conflicting checks,
missing required indexes, and rollback dependencies before any conversion or
rollback DDL starts.

## Maintenance Procedure

The existing unified enum governance section in `docs/paper_trading.md` becomes
the authoritative runbook. It requires the operator to record the database and
schema, deployment revision, backup location, command output, and validation
results.

The sequence is fixed:

1. Stop API, CLI automation, Airflow scheduling/workers, Celery workers, and
   every other business database writer while PostgreSQL remains available.
2. Create a full business-database backup and independently verify that it can
   be listed and restored in an isolated target before changing production.
3. Run the dry-run JSON command and resolve every non-ready item. Preserve the
   report with the maintenance record.
4. Run the live migration JSON command. Preserve its successful result.
5. Independently query PostgreSQL catalog metadata to confirm managed type
   labels, converted column types, JSON checks, defaults, and indexes.
6. Run the focused PostgreSQL writer smoke suite against the migrated schema.
7. Restart compatible services in a controlled order only after all checks pass,
   then confirm public API, CLI, Airflow, Celery, frontend, and export consumers
   show canonical readable labels.

Rollback uses the existing unified rollback command while writers remain
stopped. It is a schema rollback, not data recovery: it converts governed
columns back to their documented varchar types, restores defaults and indexes,
removes managed JSON checks, refuses unmanaged dependencies, and drops managed
types only after dependent columns have been converted. The runbook explicitly
prohibits destructive table drops and implicit startup migrations. A failed
rollout needing data recovery uses the verified backup restore procedure rather
than treating enum rollback as a point-in-time restore.

## Smoke Coverage

A focused operational smoke module uses public service/storage entry points,
not direct model construction where a writer already exists. Its PostgreSQL
cases verify that the migrated schema accepts and returns canonical labels for:

- a matching run that completes with `completed_with_warnings`;
- Paper Trading order, trade, cash-ledger, and associated account write paths;
- monitor target creation and persisted condition validation;
- Blackroom record creation;
- daily-bar diagnostic persistence, including valid provider outcomes; and
- SSF signal persistence, including valid event-type arrays.

The same test family or adjacent focused SQLite tests verifies portable
application contracts: input validation rejects invalid finite values and valid
workflows return the same readable labels. PostgreSQL-only assertions cover
native enum catalog labels, converted SQL column types, direct-SQL rejection,
and JSON CHECK constraints.

Tests also retain current export/import and rollback coverage. Export artifacts,
CLI/API payloads, and task-facing data are asserted as canonical strings such
as `completed_with_warnings`, never Python enum reprs or database-internal
objects.

## Error Handling

Dry-run never mutates the schema. A failed group makes the report non-ready and
causes the command to fail before apply or rollback work begins. Apply and
rollback retain their transaction boundary, existing domain-qualified error
wrapping, and independent post-operation verification. A smoke failure blocks
writer restart and directs the operator either to diagnose under the maintenance
window or run the tested schema rollback command after verifying it applies to
the deployed service version.

## Verification

Focused checks cover the migration CLI JSON schema, each domain's audit facts,
the unified preflight ordering and atomicity, PostgreSQL enum/JSON behavior,
writer smoke paths, SQLite portable validation, rollback dependency rejection,
and export/import readability. Before issue completion, run the focused suite
with `TEST_POSTGRESQL_URL` configured, then repository formatting, linting,
