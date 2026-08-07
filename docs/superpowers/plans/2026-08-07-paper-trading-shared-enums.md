# Paper Trading Shared Enums Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert selected Paper Trading finite values to shared PostgreSQL enums through an explicit, reversible operator migration while retaining canonical string API and CLI labels.

**Architecture:** Python `StrEnum` classes and SQLAlchemy native enum mappings define the canonical contracts. A Paper Trading-specific declarative migration catalog owns preflight, fresh-schema bootstrap, conversion, verification, and rollback inside one transaction; PostgreSQL startup excludes governed tables so only the operator command changes enum storage. Database export/import scripts enumerate the same named types around dependent tables.

**Tech Stack:** Python 3.11+, SQLAlchemy, PostgreSQL native enums, pytest, Ruff, mypy, Bash, Docker Compose.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Keep named PostgreSQL enum labels readable and identical to Python `StrEnum.value`, SQLAlchemy storage, API payloads, and CLI output.
- Reuse one enum type only where the business meaning and complete label set are identical.
- Do not create, alter, or append PostgreSQL enum labels during ordinary application startup.
- Run live apply and rollback only in a maintenance window after all business writers stop; retain a verified backup and migration output before restart.
- Preflight every group before any live DDL; reject nulls or unknown legacy values without coercing, renaming, truncating, deleting, or rewriting data.
- Rollback restores prior string column definitions and drops a type only after no dependent columns remain; never use `DROP TYPE ... CASCADE` as rollback.
- Do not change Paper Trading matching, ledger, snapshot, validity, API, CLI, DAG schedule, retries, task boundaries, or SLA behavior.
- PostgreSQL integration tests enabled by `TEST_POSTGRESQL_URL` are required for issue closure; skipped integration tests are not sufficient.
- Preserve the untracked `data/` directory and any concurrent user changes.

---

## File Structure

- `paper_trading/domain/enums.py`: canonical closed value sets for all selected Paper Trading concepts.
- `storage/model/paper_trading.py`: SQLAlchemy native enum mappings and unchanged readable defaults for the selected columns.
- `storage/storage_db.py`: PostgreSQL startup boundary that excludes enum-governed tables from automatic metadata DDL while preserving SQLite test setup and existing non-governed compatibility upgrades.
- `paper_trading/storage/enum_migration.py`: explicit catalog plus PostgreSQL preflight, apply, verify, bootstrap, and rollback operations.
- `tools/migrate_paper_trading_enums.py`: transaction-owning CLI for `--dry-run`, `--rollback`, and `--json`.
- `test/paper_trading/storage/test_models.py`: portable mapping and unknown-value coverage.
- `test/paper_trading/storage/test_enum_migration.py`: isolated PostgreSQL integration coverage for migration and rollback behavior.
- `test/tools/test_migrate_paper_trading_enums.py`: CLI argument forwarding, stable output, and transaction-failure behavior.
- `tools/db_common.sh`, `tools/db_export.sh`, `tools/db_import.sh`: shared ordered type list and backup/restore ordering.
- `test/tools/test_db_scripts.py`: complete Paper Trading enum export and clean-import ordering tests.
- `docs/paper_trading.md`: the existing Paper Trading operator runbook, extended with the unified migration procedure.
- `docs/database_design.md`: no planned change because it already states the enum migration, rollback, and verification policy implemented here.

### Task 1: Define Paper Trading Enum Contracts

**Files:**
- Modify: `paper_trading/domain/enums.py`
- Modify: `paper_trading/domain/fees.py`
- Test: `test/paper_trading/domain/test_fees.py`
- Test: `test/paper_trading/storage/test_models.py`

**Interfaces:**
- Consumes: existing `StrEnum`, `FEE_PRESETS`, and `DEFAULT_FEE_PRESET`.
- Produces: `FeePreset`, `PositionSource`, `PendingSettlementSource`, `RoundTripStatus`, `TradeValidityGranularity`, and `LedgerRebuildStatus` `StrEnum` classes; `DEFAULT_FEE_PRESET: FeePreset`; `FEE_PRESETS: dict[FeePreset, FeeConfig]`.

- [ ] **Step 1: Write failing contract tests for every selected value set**

```python
from paper_trading.domain.enums import (
    FeePreset,
    LedgerRebuildStatus,
    PendingSettlementSource,
    PositionSource,
    RoundTripStatus,
    TradeValidityGranularity,
)


def test_paper_trading_new_enum_values_are_canonical():
    assert [item.value for item in FeePreset] == ["a_share"]
    assert [item.value for item in PositionSource] == ["trade", "imported"]
    assert [item.value for item in PendingSettlementSource] == ["hk_sell"]
    assert [item.value for item in RoundTripStatus] == ["open", "closed"]
    assert [item.value for item in TradeValidityGranularity] == ["daily"]
    assert [item.value for item in LedgerRebuildStatus] == ["completed"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest test/paper_trading/domain/test_fees.py -q`

Expected: FAIL with an import error for the missing enum classes.

- [ ] **Step 3: Add the missing `StrEnum` classes and type the fee preset registry**

```python
class FeePreset(StrEnum):
    A_SHARE = "a_share"


class PositionSource(StrEnum):
    TRADE = "trade"
    IMPORTED = "imported"


class PendingSettlementSource(StrEnum):
    HK_SELL = "hk_sell"


class RoundTripStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class TradeValidityGranularity(StrEnum):
    DAILY = "daily"


class LedgerRebuildStatus(StrEnum):
    COMPLETED = "completed"
```

Change `DEFAULT_FEE_PRESET` to `FeePreset.A_SHARE` and key `FEE_PRESETS` by `FeePreset`; normalize incoming `str | FeePreset | None` with `FeePreset(name or DEFAULT_FEE_PRESET)` before lookup, preserving the current `ValueError("unknown fee preset: ...")` behavior for an unknown string.

- [ ] **Step 4: Run domain and existing fee tests**

Run: `uv run pytest test/paper_trading/domain/test_fees.py -q`

Expected: PASS with unchanged fee calculations and canonical `a_share` behavior.

- [ ] **Step 5: Commit the enum contracts**

```bash
git add paper_trading/domain/enums.py paper_trading/domain/fees.py test/paper_trading/domain/test_fees.py
git commit -m "Add paper trading value enums"
```

### Task 2: Map Selected ORM Columns To Shared Native Enums

**Files:**
- Modify: `storage/model/paper_trading.py`
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/services/round_trip_service.py`
- Test: `test/paper_trading/storage/test_models.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/paper_trading/services/test_round_trip_service.py`

**Interfaces:**
- Consumes: every existing and new `StrEnum` from `paper_trading.domain.enums`.
- Produces: native SQLAlchemy enum columns using `values_callable=lambda enum_type: [member.value for member in enum_type]` and `validate_strings=True`; repository/service write paths that pass canonical `.value` labels.

- [ ] **Step 1: Write failing portable enum mapping tests**

```python
from sqlalchemy import Enum


def test_selected_paper_columns_use_shared_value_enums():
    assert isinstance(PaperOrder.__table__.c.side.type, Enum)
    assert PaperOrder.__table__.c.side.type.name == "paper_order_side"
    assert PaperTrade.__table__.c.side.type.name == "paper_order_side"
    assert PaperTradeValidityCheck.__table__.c.side.type.name == "paper_order_side"
    assert PaperOrder.__table__.c.market.type.name == "paper_market"
    assert PaperPosition.__table__.c.market.type.name == "paper_market"
    assert PaperPositionLot.__table__.c.market.type.name == "paper_market"
    assert PaperTrade.__table__.c.market.type.name == "paper_market"
    assert PaperTradeValidityCheck.__table__.c.market.type.name == "paper_market"


def test_selected_paper_enum_columns_reject_unknown_values(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'paper.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(PaperOrder(..., side="borrow", status="accepted", market="a_share"))
        with pytest.raises((StatementError, ValueError)):
            session.flush()
```

Also add rows covering the existing defaults for account status/fee preset, position and lot source/market, round-trip status, validity granularity, and ledger rebuild status, asserting they load as the same readable strings.

- [ ] **Step 2: Run mapping tests to verify they fail**

Run: `uv run pytest test/paper_trading/storage/test_models.py -q`

Expected: FAIL because selected columns are still `String` types.

- [ ] **Step 3: Implement exact native enum mappings and canonical writes**

Add a small module-local helper in `storage/model/paper_trading.py` that returns `Enum(enum_type, name=..., values_callable=..., native_enum=True, validate_strings=True)`. Apply it with these type names and columns:

```text
paper_account_status: paper_accounts.status
paper_fee_preset: paper_accounts.fee_preset
paper_cash_event_type: paper_cash_ledger.event_type
paper_order_side: paper_orders.side, paper_trades.side, paper_trade_validity_checks.side
paper_order_status: paper_orders.status
paper_trade_validity_status: paper_orders.validity_status, paper_trade_validity_checks.status
paper_market: paper_orders.market, paper_positions.market, paper_position_lots.market, paper_trades.market, paper_trade_validity_checks.market
paper_position_source: paper_positions.source, paper_position_lots.source
paper_round_trip_status: paper_position_round_trips.status
paper_trade_validity_granularity: paper_trade_validity_checks.data_granularity
paper_pending_settlement_source: paper_pending_settlement.source
paper_ledger_rebuild_status: paper_ledger_rebuilds.status
paper_matching_run_status: paper_matching_runs.status
```

Keep all existing `VARCHAR` sizes and server-default labels represented in the migration catalog for rollback. Update repository and round-trip service literals to use `.value` from the appropriate enum where they write or compare selected values, without changing public method parameter shapes or response serialization.

- [ ] **Step 4: Run portable Paper Trading mapping and workflow tests**

Run: `uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_round_trip_service.py -q`

Expected: PASS; SQLite persists and returns the existing lower-case labels while invalid writes fail before storage.

- [ ] **Step 5: Commit ORM mappings and canonical writes**

```bash
git add storage/model/paper_trading.py paper_trading/storage/repository.py paper_trading/services/round_trip_service.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_round_trip_service.py
git commit -m "Map paper trading values to enums"
```

### Task 3: Enforce The Explicit PostgreSQL Startup Boundary

**Files:**
- Modify: `storage/storage_db.py`
- Modify: `test/storage/test_storage_db.py`
- Modify: `test/paper_trading/storage/test_matching_status_migration.py`

**Interfaces:**
- Consumes: `Base.metadata.sorted_tables` and the full table-name set from the governed enum catalog.
- Produces: `_non_enum_governed_paper_trading_tables() -> list[Any]`, used only for PostgreSQL automatic DDL; ordinary SQLite metadata setup remains unchanged.

- [ ] **Step 1: Write failing PostgreSQL startup isolation tests**

```python
def test_postgresql_storage_startup_excludes_all_enum_governed_paper_tables(monkeypatch):
    create_all = Mock()
    monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", create_all)
    # Instantiate StorageDb against a PostgreSQL-shaped engine as existing tests do.
    StorageDb(config)
    tables = create_all.call_args.kwargs["tables"]
    assert {table.name for table in tables}.isdisjoint(
        {
            "paper_accounts", "paper_cash_ledger", "paper_positions",
            "paper_position_lots", "paper_orders", "paper_trades",
            "paper_position_round_trips", "paper_matching_runs",
            "paper_trade_validity_checks", "paper_pending_settlement",
            "paper_ledger_rebuilds",
        }
    )
```

Extend the existing PostgreSQL integration startup test to assert no newly named Paper Trading enum types exist after `StorageDb` initialization.

- [ ] **Step 2: Run isolation tests to verify they fail**

Run: `uv run pytest test/storage/test_storage_db.py test/paper_trading/storage/test_matching_status_migration.py -q`

Expected: FAIL because startup still includes selected tables other than `paper_matching_runs`.

- [ ] **Step 3: Exclude governed tables only for PostgreSQL startup**

Replace `_non_matching_run_tables()` with a helper that receives the engine dialect and excludes the full governed table-name set only when `dialect.name == "postgresql"`. Pass the helper result to `Base.metadata.create_all`; keep SQLite tests and development databases able to create every mapped table from metadata. Remove individual `__table__.create()` calls in `ensure_paper_trading_schema()` for governed tables on PostgreSQL, retaining existing additive-column compatibility checks only for non-enum fields.

- [ ] **Step 4: Run startup isolation and SQLite regression tests**

Run: `uv run pytest test/storage/test_storage_db.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_matching_status_migration.py -q`

Expected: PASS; PostgreSQL startup does no governed table/enum DDL, while SQLite metadata setup remains functional.

- [ ] **Step 5: Commit the startup boundary**

```bash
git add storage/storage_db.py test/storage/test_storage_db.py test/paper_trading/storage/test_matching_status_migration.py
git commit -m "Keep paper trading enum DDL explicit"
```

### Task 4: Implement Coordinated Preflight, Apply, Verify, And Rollback

**Files:**
- Create: `paper_trading/storage/enum_migration.py`
- Create: `test/paper_trading/storage/test_enum_migration.py`
- Modify: `paper_trading/storage/matching_status_migration.py`

**Interfaces:**
- Consumes: mapped Paper Trading tables, their `StrEnum` types, and a SQLAlchemy `Connection`.
- Produces: `PaperTradingEnumMigrationError`, `PaperTradingEnumColumn`, `PaperTradingEnumGroup`, `PaperTradingEnumMigrationResult`, `PAPER_TRADING_ENUM_GROUPS`, `migrate_paper_trading_enums(connection: Connection, *, dry_run: bool = False, rollback: bool = False) -> PaperTradingEnumMigrationResult`.

- [ ] **Step 1: Write failing PostgreSQL integration fixtures and preflight tests**

Create a fixture that builds all eleven governed tables in an isolated schema with their prior `VARCHAR` columns, canonical defaults, ordinary indexes, and the matching active-run partial unique index. Add these tests:

```python
def test_dry_run_reports_every_group_without_ddl(postgres_schema):
    result = migrate_paper_trading_enums(connection, dry_run=True)
    assert result.dry_run is True
    assert result.converted is False
    assert {group.type_name for group in result.groups} == EXPECTED_TYPE_NAMES
    assert enum_types(connection) == set()


def test_unknown_legacy_value_aborts_all_groups_without_conversion(postgres_schema):
    connection.execute(text("INSERT INTO paper_orders (...) VALUES (..., 'borrow', ...)"))
    with pytest.raises(PaperTradingEnumMigrationError, match="paper_order_side"):
        migrate_paper_trading_enums(connection)
    assert column_type(connection, "paper_accounts", "status") == "character varying"
    assert enum_types(connection) == set()
```

- [ ] **Step 2: Run migration tests to verify they fail**

Run: `uv run pytest test/paper_trading/storage/test_enum_migration.py -q`

Expected: FAIL because the unified migration module and command contract do not exist.

- [ ] **Step 3: Build the explicit catalog and all-group preflight**

Define frozen `PaperTradingEnumColumn` records with `table_name`, `column_name`, `legacy_type_sql`, `default_sql`, `nullable`, and any named index/constraint restoration facts. Define `PaperTradingEnumGroup` records using exactly the Task 2 type names and complete label tuples from their `StrEnum` classes. The catalog must include every selected column and retain matching-run's `uq_matching_active_scope` predicate facts.

For PostgreSQL, inspect schema-local table existence, distinct values including nulls, type OIDs, enum labels, column defaults, indexes, constraints, and dependencies. Preflight every group before creating types, dropping defaults/indexes, or altering columns. Treat a missing table as bootstrap work only when the entire governed table is absent; reject a partially missing or structurally incompatible table with a group- and column-specific error. Return a no-op result for non-PostgreSQL connections.

- [ ] **Step 4: Add conversion, fresh bootstrap, verification, and rollback tests**

```python
def test_apply_converts_all_columns_preserves_defaults_and_indexes(postgres_schema):
    result = migrate_paper_trading_enums(connection)
    assert result.converted is True
    assert column_type(connection, "paper_orders", "side") == "paper_order_side"
    assert column_type(connection, "paper_trades", "side") == "paper_order_side"
    assert enum_labels(connection, "paper_market") == ("a_share", "hk_connect")
    assert column_default(connection, "paper_accounts", "status") == "'active'::paper_account_status"
    assert matching_index_is_valid(connection)


def test_apply_is_idempotent_and_rejects_direct_invalid_write(postgres_schema):
    migrate_paper_trading_enums(connection)
    assert migrate_paper_trading_enums(connection).converted is False
    with pytest.raises(Exception):
        connection.execute(text("INSERT INTO paper_orders (...) VALUES (..., 'borrow', ...)"))


def test_rollback_restores_varchar_columns_and_removes_unreferenced_types(postgres_schema):
    migrate_paper_trading_enums(connection)
    result = migrate_paper_trading_enums(connection, rollback=True)
    assert result.rolled_back is True
    assert column_type(connection, "paper_orders", "side") == "character varying(10)"
    assert enum_types(connection) == set()
    assert matching_index_is_valid(connection, enum_typed=False)
```

Add a fresh-schema test asserting live apply creates every governed table from mapped SQLAlchemy metadata and returns canonical enum-backed columns; add a type-label mismatch test that fails without modifying the existing type.

- [ ] **Step 5: Implement apply, verify, and rollback in one transaction-compatible operation**

On fresh PostgreSQL schemas, create the governed tables in dependency order from their mapped `__table__` definitions only within this explicit migration. On legacy schemas, for each group create or validate its schema-local named type, temporarily remove only cataloged dependent defaults/indexes, alter each column with `USING column::text::<type_name>`, recreate documented defaults/indexes, and verify the final catalog facts. Make each apply rerun report `converted=False` when all columns already match.

For rollback, preflight that every cataloged selected column has the expected enum type; temporarily remove dependencies as declared; use `USING column::text::<legacy_type_sql>` to restore the exact prior `VARCHAR` form; restore defaults and indexes; verify no selected column references the type; then execute a non-cascading `DROP TYPE <type_name>`. Preserve values and canonical index behavior throughout.

Refactor `migrate_paper_matching_status_enum()` to delegate to the matching group in the unified implementation or keep it as a thin compatibility wrapper that returns its established result shape. Do not retain independent matching-run DDL paths that can diverge from the unified catalog.

- [ ] **Step 6: Run PostgreSQL migration coverage**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_enum_migration.py test/paper_trading/storage/test_matching_status_migration.py -q`

Expected: PASS when `TEST_POSTGRESQL_URL` is configured; covers dry-run, fresh bootstrap, conversion, complete labels, unknown-value atomic rejection, defaults/indexes, invalid direct writes, idempotency, type mismatch, and rollback.

- [ ] **Step 7: Commit the migration implementation**

```bash
git add paper_trading/storage/enum_migration.py paper_trading/storage/matching_status_migration.py test/paper_trading/storage/test_enum_migration.py test/paper_trading/storage/test_matching_status_migration.py
git commit -m "Add paper trading enum migration"
```

### Task 5: Add The Operator Migration CLI

**Files:**
- Create: `tools/migrate_paper_trading_enums.py`
- Create: `test/tools/test_migrate_paper_trading_enums.py`

**Interfaces:**
- Consumes: `conf.parse_config()`, `storage.get_storage()`, and `migrate_paper_trading_enums()`.
- Produces: `main(argv: list[str] | None = None) -> int`; CLI options `--dry-run`, `--rollback`, and `--json`.

- [ ] **Step 1: Write failing CLI behavior tests**

```python
def test_main_forwards_dry_run_and_emits_stable_json(monkeypatch, capsys):
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_paper_trading_enums", fake_migration)
    assert command.main(["--dry-run", "--json"]) == 0
    assert calls == [{"dry_run": True, "rollback": False}]
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_main_forwards_rollback_and_rolls_back_transaction_on_error(monkeypatch, caplog, capsys):
    monkeypatch.setattr(command, "migrate_paper_trading_enums", raising_migration)
    assert command.main(["--rollback"]) == 1
    assert transaction.rolled_back is True
    assert "migration failure" in capsys.readouterr().err
```

Include a subprocess `--help` test proving the script adds the project root before imports.

- [ ] **Step 2: Run CLI tests to verify they fail**

Run: `uv run pytest test/tools/test_migrate_paper_trading_enums.py -q`

Expected: FAIL because the operator script does not exist.

- [ ] **Step 3: Implement the operator command**

Follow `tools/bootstrap_paper_matching_run_status.py`: add the repository root to `sys.path`, parse config, open `get_storage().engine.begin()`, invoke the migration with `dry_run=args.dry_run` and `rollback=args.rollback`, and serialize `dataclasses.asdict(result)` for `--json`. Human output must include `dry_run`, `rollback`, `converted`, `rolled_back`, and a comma-separated per-group type/column summary. Catch `Exception`, log the stack trace, print `error: <message>` to stderr, and return `1`.

- [ ] **Step 4: Run CLI tests**

Run: `uv run pytest test/tools/test_migrate_paper_trading_enums.py -q`

Expected: PASS with stable human/JSON output, correct mode forwarding, and transaction rollback on failure.

- [ ] **Step 5: Commit the CLI**

```bash
git add tools/migrate_paper_trading_enums.py test/tools/test_migrate_paper_trading_enums.py
git commit -m "Add paper trading enum migration command"
```

### Task 6: Preserve All Paper Trading Enum Types In Backup And Restore

**Files:**
- Modify: `tools/db_common.sh`
- Modify: `tools/db_export.sh`
- Modify: `tools/db_import.sh`
- Modify: `test/tools/test_db_scripts.py`

**Interfaces:**
- Consumes: `PAPER_TRADING_ENUM_TYPES` Bash array declared in `tools/db_common.sh` and the existing `BUSINESS_TABLES` list.
- Produces: exports that emit existing enum DDL before selected dependent table dumps; clean exports/imports that drop dependent tables before all selected enum types.

- [ ] **Step 1: Write failing complete ordering tests**

```python
def test_full_export_places_every_paper_enum_before_table_dump(tmp_path):
    output_file = tmp_path / "paper.sql"
    _run_script("db_export.sh", ["--no-gzip", "--out", str(output_file)], tmp_path)
    dump = output_file.read_text(encoding="utf-8")
    for type_name in PAPER_ENUM_TYPES:
        assert f'CREATE TYPE "public"."{type_name}"' in dump
        assert dump.index(f'CREATE TYPE "public"."{type_name}"') < dump.index("-- dump output")


def test_clean_full_import_drops_tables_before_every_paper_enum(tmp_path):
    _run_script("db_import.sh", ["--clean", "--in", str(input_file)], tmp_path)
    drop_sql = command_log(tmp_path)
    assert drop_sql.index('DROP TABLE IF EXISTS "public"."paper_orders"') < drop_sql.index(
        'DROP TYPE IF EXISTS "public"."paper_order_side"'
    )
```

Update the fake Docker `psql` output to return labels for the queried type name so tests can assert every generated `CREATE TYPE` statement and preserve the existing matching-only behavior.

- [ ] **Step 2: Run script tests to verify they fail**

Run: `uv run pytest test/tools/test_db_scripts.py -q`

Expected: FAIL because the scripts only handle `paper_matching_run_status`.

- [ ] **Step 3: Generalize export/import around one ordered type array**

Declare `PAPER_TRADING_ENUM_TYPES` in `tools/db_common.sh` in catalog order. Replace single matching-type variables and branches with loops that query and prepend schema-local type DDL for types needed by the selected table set. For `--clean`, generate all relevant table drops first in reverse table order, then non-cascading `DROP TYPE IF EXISTS` statements in reverse enum order, then type definitions before `pg_dump` output. Preserve the optimization that unrelated single-table exports do not query any Paper Trading enum.

- [ ] **Step 4: Run shell-script tests**

Run: `uv run pytest test/tools/test_db_common.py test/tools/test_db_scripts.py -q`

Expected: PASS; full exports/imports cover every type and matching-only exports retain their prior ordering.

- [ ] **Step 5: Commit backup and restore support**

```bash
git add tools/db_common.sh tools/db_export.sh tools/db_import.sh test/tools/test_db_scripts.py
git commit -m "Preserve paper trading enum backup order"
```

### Task 7: Run End-To-End Regression And Update Operator Documentation

**Files:**
- Modify: `docs/paper_trading.md:469-579`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_order_delete_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`
- Test: `test/paper_trading/services/test_trade_validity_service.py`
- Test: `test/paper_trading/api/test_accounts_api.py`
- Test: `test/paper_trading/api/test_orders_api.py`
- Test: `test/paper_trading/api/test_matching_api.py`

**Interfaces:**
- Consumes: the migration CLI from Task 5 and its maintenance-window constraints.
- Produces: an operator runbook that names the dry-run, apply, verification, and rollback commands without changing application behavior.

- [ ] **Step 1: Extend the existing Paper Trading maintenance runbook**

Document these exact commands and sequencing:

```bash
uv run tools/migrate_paper_trading_enums.py --dry-run --json
uv run tools/migrate_paper_trading_enums.py --json
uv run tools/migrate_paper_trading_enums.py --rollback --json
```

State that all business writers must be stopped while PostgreSQL remains running, unknown legacy values cause no mutation, output must be retained with a verified backup, and only compatible writers restart after successful verification. Reference `docs/database_design.md` for enum evolution policy; do not duplicate the full policy.

- [ ] **Step 2: Run focused application regression tests**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/api/test_accounts_api.py test/paper_trading/api/test_orders_api.py test/paper_trading/api/test_matching_api.py -q`

Expected: PASS with canonical string labels, including `completed_with_warnings`, preserved matching/ledger/snapshot/validity behavior, and unchanged API contracts.

- [ ] **Step 3: Run required static and migration verification**

Run: `uv run ruff format --check paper_trading storage tools test/paper_trading test/tools && uv run ruff check paper_trading storage tools test/paper_trading test/tools && uv run mypy paper_trading storage && TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_enum_migration.py test/paper_trading/storage/test_matching_status_migration.py -q && git diff --check`

Expected: every command succeeds; PostgreSQL integration tests run rather than skip when the environment variable is configured.

- [ ] **Step 4: Commit documentation and final verification changes**

```bash
git add docs/paper_trading.md test/paper_trading/services test/paper_trading/api
git commit -m "Document paper trading enum migration"
```

## Self-Review

Spec coverage is complete: Tasks 1-2 establish shared Python/ORM labels; Task 3 removes startup DDL authority; Task 4 owns preflight, fresh bootstrap, apply, verification, unknown-value atomicity, idempotency, direct-write enforcement, index/default retention, and rollback; Task 5 adds the operator interface; Task 6 provides backup/restore ordering; Task 7 documents the maintenance procedure and executes workflow regressions. No JSON contracts are included because issue #36 scopes only selected Paper Trading table fields.

The plan uses the same signatures across tasks: `migrate_paper_trading_enums(connection, *, dry_run=False, rollback=False)` is defined in Task 4 and consumed only by Task 5. The full set of PostgreSQL type names is defined in Task 2 and repeated consistently in Tasks 4 and 6. The plan contains no deferred work markers or implied validation steps.
