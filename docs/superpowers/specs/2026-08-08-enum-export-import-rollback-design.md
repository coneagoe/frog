# Enum Export, Import, and Rollback Design

## Goal

Harden business-database backup, clean restore, and enum-governance rollback so
all finite-value types and stable JSON checks introduced by the governance
migrations survive operational recovery. The implementation must preserve the
existing business-table selection, command interfaces, shared-enum behavior,
and full-clean ordering.

## Scope and Approach

Extend the existing explicit business catalog in `tools/db_common.sh` rather
than generating shell metadata dynamically from Python or switching to a
schema-wide `pg_dump`. The catalog remains the operational source for which
business tables and enum types are included. SQLAlchemy migration adapters
remain the only owners of forward conversion and rollback semantics.

This keeps the change local to the existing backup scripts and governance
adapters, avoids coupling shell operations to Python imports, and preserves the
current exact business-table export contract.

## Managed Database Catalog

Add the Storage-domain enum types to `BUSINESS_ENUM_TYPES` and map them to their
governed tables:

- `blackroom_market` and `blackroom_source` for `blackroom_records`.
- `daily_bar_diagnostic_adjust` and `daily_bar_diagnostic_classification` for
  `daily_bar_diagnostics`.
- `ssf_change_signal_status` for `ssf_change_signals`.

The existing Paper Trading, Monitor, and Forecast SSF entries remain in the
same catalog. A selected-table export emits only enum definitions required by
that table. A full business export emits every existing managed enum before
the dependent table dump. Type creation is duplicate-safe so a selected-table
dump can be restored into a database where shared types already exist.

Clean operations preserve dependency ordering:

1. Full clean export/import removes managed dependent tables before enum types.
2. Selected-table clean removes only the selected table and only enum types
   that are private to that table.
3. Shared enum types remain when another managed table can depend on them.
4. Selected-table clean is rejected before mutation when an unselected table
   has an inbound foreign key to the selected table.

`pg_dump` remains responsible for emitting table-owned indexes, foreign keys,
defaults, and JSON `CHECK` constraints. The scripts must not duplicate those
definitions in manually generated DDL.

## Forward Migration and Rollback

The unified `migrate_enums` command continues to run all adapter preflights
before DDL, then applies or rolls back every domain in one transaction.

On forward migration:

- Validate all legacy scalar and JSON values before conversion.
- Create or verify the complete expected enum label sets.
- Convert string columns using explicit text-to-enum casts.
- Restore defaults and preserve existing indexes and constraints.
- Install and verify the Storage JSON checks and Monitor condition check.

On rollback:

- Preflight every adapter and reject incompatible or partially governed state.
- Reject any unmanaged dependency on a managed enum, including columns,
  defaults, indexes, constraints, views, or other catalog objects.
- Remove managed JSON `CHECK` constraints before removing their governed enum
  domain.
- Convert every managed enum column back to its documented prior `VARCHAR`
  representation and restore its legacy default.
- Verify that no dependency remains, then drop each managed enum type.
- Verify the final legacy column types, defaults, indexes, constraints, and
  absence of managed enum types.

Rollback failure must abort the transaction and leave all governed domains in
their pre-rollback state. Shared enum types must not be dropped while any
managed column still uses them.

## Verification

Portable shell tests will prove:

- All managed enum types are selected for full export.
- Storage enum definitions precede dependent table output.
- Full clean deletion removes tables before enum types.
- Selected-table exports contain only required types.
- Shared types are not removed by selected-table clean operations.
- JSON checks remain part of the `pg_dump` table output.
- Selected-table foreign-key safety rejects destructive clean operations before
  output or database mutation.

PostgreSQL integration tests, gated by `TEST_POSTGRESQL_URL`, will use isolated
schemas to prove forward restore and rollback ordering. They will verify enum
labels, data, defaults, indexes, foreign keys, JSON checks, and table presence
after clean restore. They will run unified migration followed by rollback and
assert that every affected column returns to its original string type, JSON
checks are removed, defaults are restored, and enum types are dropped only
after dependencies are gone. A separate case will create an unmanaged enum
dependency and assert rollback fails without partial conversion.

When PostgreSQL is unavailable, integration tests must report an explicit skip
rather than claim coverage. Existing shell compatibility tests and unrelated
business-table export behavior remain unchanged.

## Documentation and Compatibility

Update the authoritative Paper Trading database operations section to describe
the complete managed enum catalog, duplicate-safe selected-table type creation,
JSON-check preservation, full-clean ordering, selected-table foreign-key
limits, and rollback ordering. Remove stale matching-run-only statements.

Do not change command arguments, business-table names, DAG schedules, task
boundaries, retries, SLAs, or application-visible enum labels. Unknown legacy
values are rejected; no enum labels are silently added, renamed, or coerced.
