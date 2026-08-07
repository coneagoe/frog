# Database Design Principles

## Finite Business Values

Use a named PostgreSQL enum for a table column whose values are finite, closed,
and defined by this application. Keep the persisted enum labels readable; do
not replace them with integer codes.

Examples include statuses, order sides, markets, event types, sources,
frequencies, reset modes, and built-in fee-preset names. Reuse one enum type
for columns with the same business meaning. For example, paper-trading market
columns share one market enum rather than defining one enum per table.

Define the same value set in Python with `StrEnum`, map it through SQLAlchemy
`Enum`, and persist its `.value` labels. PostgreSQL enum labels, SQLAlchemy
mapping, API payload values, and CLI output must agree.

Keep `VARCHAR` or `TEXT` for free-form user input, external-provider taxonomies,
and values that can expand independently of this application. Examples include
names, notes, detailed error text, third-party classifications, industries, ETF
types, shareholder types, and provider-specific labels.

## Enum Evolution

Enum values may be added only through an explicit, reviewed database migration.
Application startup must not silently alter enum types or add enum labels.

Before converting an existing string column:

1. Inspect all distinct values, nulls, defaults, indexes, constraints, and
   dependent objects.
2. Compare observed values with the complete application-defined value set,
   not only values currently present in production.
3. Abort on an unknown value. Do not coerce, truncate, or silently rename it.
4. Create or verify the named enum, drop/recreate dependent defaults and
   indexes as required, and convert with an explicit text-to-enum cast.
5. Restore defaults, indexes, and constraints, then verify the final column
   type and enum labels.

Perform schema conversions during a maintenance window with every application
and worker that writes the business database stopped. Keep the database service
running. Restart compatible application versions only after migration
verification.

Every enum migration needs a tested rollback command or procedure that converts
the affected columns back to their prior string representation. Do not drop an
enum type while any column, default, index predicate, or other object still
depends on it.

Database export and import procedures must preserve enum type creation before
dependent tables and type removal after dependent tables. Test restore ordering
whenever a new enum type is introduced.

## JSON Values

JSON columns remain appropriate for structured evidence, configuration, lists,
and external payloads. Do not split JSON into relational columns solely to use a
PostgreSQL enum.

Finite values nested in JSON are still business contracts and require
validation:

- Define them with Python `StrEnum` or `Literal` at the write boundary.
- Validate discriminated JSON structures centrally before persistence. For
  example, a monitor condition validates its `type`, allowed `direction` for
  that type, and type-specific required fields.
- Add PostgreSQL `CHECK` constraints when the JSON shape and allowed values can
  be expressed stably in SQL. At minimum, use checks for fixed arrays and
  fixed nested labels that could otherwise be bypassed by direct SQL.
- Use application validation as the authority for conditional or deeply nested
  schemas that would make a database constraint unreadable or fragile.

Current examples of JSON-contained finite values include:

- `daily_bar_diagnostics.provider_outcomes[*].status`: `downloaded`, `empty`,
  or `error`.
- `ssf_change_signals.event_types[*]`: `increase`, `decrease`, `new_entry`,
  or `exit`.
- `stock_monitor_targets.condition.type` and its type-dependent `direction`.

JSON keys and values supplied by external providers, or deliberately designed
to be extensible, remain unbounded unless an explicit application contract is
introduced.

## Verification

Each migration must have PostgreSQL integration coverage for successful
conversion, idempotent rerun, rejection of unknown legacy values, preserved
indexes/defaults, and rollback behavior. SQLite tests must continue to verify
the SQLAlchemy and application-level contracts, but do not substitute for
PostgreSQL enum DDL testing.

After a production migration, run focused write-path smoke tests for every
affected subsystem and verify that API/CLI responses still expose the canonical
string labels.
