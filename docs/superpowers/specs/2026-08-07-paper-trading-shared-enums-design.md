# Paper Trading Shared Enums Design

## Goal

Implement issue #36 by moving selected Paper Trading finite business values
from string columns to named, shared PostgreSQL enums. The application,
database, API, and CLI will retain the existing readable labels. The migration
is explicit and operator-controlled; normal application startup will not create,
alter, or add enum labels.

## Scope

The conversion covers the selected Paper Trading fields identified by issue
#36:

- Account `status` and `fee_preset`.
- Cash-ledger `event_type`.
- Order `side`, `status`, `validity_status`, and `market`.
- Pending-settlement `source`.
- Position and position-lot `source` and `market`.
- Position round-trip `status`.
- Trade-validity-check `side`, `status`, `data_granularity`, and `market`.
- Trade `side` and `market`.
- Ledger-rebuild `status`.
- Matching-run `status`, using the existing `paper_matching_run_status` type.

Free-form text, provider-defined values, detailed reasons, comments, and JSON
payloads remain outside this issue. No matching, ledger, snapshot, validity,
API, CLI, DAG schedule, retry, task-boundary, or SLA behavior changes.

## Canonical Value Contracts

`paper_trading.domain.enums` is the Python source of truth for every selected
value set. Missing closed sets are added as `StrEnum` classes: the built-in fee
preset, position source, pending-settlement source, round-trip status,
validity-check granularity, and ledger-rebuild status. Existing enums remain
authoritative for account status, order side/status, market, cash event type,
matching-run status, and validity status.

SQLAlchemy maps each selected field through a native `Enum` configured to
persist enum member `.value` labels. Reused meanings share one PostgreSQL type:
all selected market columns share the market type; order, trade, and
validity-check sides share the side type; position and lot sources share the
position-source type; and validity states share their type where their value set
is the same. Python values, database labels, and response labels are all the
current lower-case readable strings.

## Migration Architecture

`paper_trading/storage/enum_migration.py` contains the one coordinated
Paper Trading migration. A declarative, explicit group catalog describes each
type name, its `StrEnum` labels, affected table/column pairs, former `VARCHAR`
type and defaults, and dependent schema facts that require restoration.

The catalog remains intentionally specific to this schema rather than becoming a
generic reflection framework. It is the auditable contract for each conversion:
reviewers can see exactly which columns share an enum and how a rollback restores
each one.

`tools/migrate_enums.py` is the operator entrypoint. It reads the standard
configuration and uses a single database transaction. Its modes are:

- `--dry-run`: inspect and report all groups without DDL or DML.
- Default execution: preflight every selected group, convert all compliant
  groups, then verify every final contract.
- `--rollback`: convert every selected enum column back to its declared prior
  string representation, restore defaults and indexes, verify the string
  contract, then drop a type only after no dependent columns remain.
- `--json`: produce machine-readable output in every mode.

Use `uv run tools/migrate_enums.py --dry-run --json` to inspect, `uv run
tools/migrate_enums.py --json` to apply, and `uv run tools/migrate_enums.py
--rollback --json` to roll back. The former
`tools/migrate_paper_trading_enums.py` command is historical and has been
superseded by the unified entrypoint.

The prior matching-run bootstrap command remains valid for fresh matching-run
storage. The unified command detects the existing matching enum type and either
converts the legacy column or verifies its already-converted state.

## Preflight, Conversion, And Rollback

For every group, preflight obtains the observed distinct values including nulls,
column type, default, indexes, constraints, and dependent objects. It compares
every observed value with the entire application-defined label set. Any null
where the target is non-nullable, unknown legacy value, unexpected enum label
set, incompatible type, or unrecognized dependent schema object fails the whole
operation before live DDL begins. It never normalizes, renames, truncates, or
deletes existing data.

On live conversion, the command creates or validates the schema-local named
PostgreSQL enum, removes only dependencies that PostgreSQL requires to be
recreated, casts through `column::text::<enum_type>`, and restores documented
defaults, indexes, and constraints. Verification checks all type names and
labels, converted columns, defaults, indexes, and constraints. A successful
rerun is a no-op verification pass.

Rollback uses the same catalog and transaction. It removes or adjusts dependent
defaults and indexes as required, casts each enum column to its original
`VARCHAR` form, restores its documented default and schema facts, and proves no
column still depends on a type before dropping that type. It does not use table
drops or `DROP TYPE ... CASCADE` as rollback.

Both apply and rollback require a maintenance window: stop Airflow, Celery,
Paper Trading, and all other business writers while keeping PostgreSQL available.
Retain a verified backup and command output before restarting compatible writers.

## Export And Import

`tools/db_common.sh`, `tools/db_export.sh`, and `tools/db_import.sh` will own a
complete ordered list of Paper Trading enum types. Export emits their type DDL
before the dependent table dump. Clean import removes dependent tables before
the corresponding types and restores type DDL before tables. Tests cover this
ordering for every newly introduced Paper Trading enum.

## Verification

PostgreSQL integration tests run in isolated schemas when
`TEST_POSTGRESQL_URL` is available. They prove:

- Dry-run reports all groups without mutations.
- Successful conversion produces the full application label sets and shared
  types on every selected column.
- Defaults, ordinary indexes, and the matching-run partial index are preserved.
- Unknown legacy values reject the entire migration without rewriting data.
- Existing expected types, already-converted columns, and reruns are idempotent.
- Direct invalid enum writes fail in PostgreSQL.
- Rollback restores every selected column's declared string representation and
  removes only unreferenced enum types.
- Export/import SQL orders every enum type correctly around dependent tables.

Focused Paper Trading SQLite service and API tests continue to establish portable
ORM and response behavior. Existing matching, order, ledger, snapshot, and
validity workflows must retain canonical string labels. Required completion
checks are focused Ruff formatting/linting, mypy for changed typed modules,
`git diff --check`, relevant unit tests, and the PostgreSQL integration suite;
skipped PostgreSQL integration tests are not sufficient for issue closure.
