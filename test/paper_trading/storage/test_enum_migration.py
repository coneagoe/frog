# ruff: noqa: E501

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

from paper_trading.storage.enum_migration import (
    PAPER_TRADING_ENUM_ADAPTER,
    PAPER_TRADING_ENUM_GROUPS,
    PaperTradingEnumMigrationError,
    migrate_paper_trading_enums,
)

EXPECTED_TYPE_NAMES = {group.type_name for group in PAPER_TRADING_ENUM_GROUPS}


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


@pytest.fixture()
def postgres_schema():
    engine = _engine()
    schema = f"enum_migration_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        _create_legacy_schema(connection)
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture()
def empty_postgres_schema():
    engine = _engine()
    schema = f"enum_migration_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _connection(engine: Engine, schema: str) -> Connection:
    connection = engine.connect()
    connection.execute(text(f'SET search_path TO "{schema}"'))
    return connection


def _create_legacy_schema(connection: Connection) -> None:  # noqa: E501
    statements = (
        "CREATE TABLE paper_accounts (id integer primary key, status varchar(20) NOT NULL DEFAULT 'active', fee_preset varchar(30) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_cash_ledger (id integer primary key, event_type varchar(20) NOT NULL)",
        "CREATE TABLE paper_positions (id integer primary key, source varchar(20) NOT NULL DEFAULT 'trade', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_position_lots (id integer primary key, source varchar(20) NOT NULL DEFAULT 'trade', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_orders (id integer primary key, side varchar(10) NOT NULL, status varchar(30) NOT NULL, validity_status varchar(20), market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_trades (id integer primary key, side varchar(10) NOT NULL, market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_position_round_trips (id integer primary key, status varchar(20) NOT NULL DEFAULT 'open')",
        "CREATE TABLE paper_trade_validity_checks (id integer primary key, side varchar(10) NOT NULL, status varchar(20) NOT NULL, data_granularity varchar(20) NOT NULL DEFAULT 'daily', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_pending_settlement (id integer primary key, source varchar(20) NOT NULL)",
        "CREATE TABLE paper_ledger_rebuilds (id integer primary key, status varchar(20) NOT NULL)",
        "CREATE TABLE paper_matching_runs (id integer primary key, trade_date date NOT NULL, scope_key varchar(40) NOT NULL, status varchar(32) NOT NULL)",
        "CREATE INDEX ix_paper_positions_market ON paper_positions (market)",
        "CREATE INDEX ix_paper_position_lots_market ON paper_position_lots (market)",
        "CREATE INDEX ix_paper_orders_status ON paper_orders (status)",
        "CREATE INDEX ix_paper_orders_validity_status ON paper_orders (validity_status)",
        "CREATE INDEX ix_paper_orders_market ON paper_orders (market)",
        "CREATE INDEX ix_paper_trades_market ON paper_trades (market)",
        "CREATE INDEX ix_paper_trade_validity_checks_status ON paper_trade_validity_checks (status)",
        "CREATE INDEX ix_paper_trade_validity_checks_market ON paper_trade_validity_checks (market)",
        "CREATE INDEX ix_paper_position_round_trips_status ON paper_position_round_trips (status)",
        "CREATE INDEX ix_paper_ledger_rebuilds_status ON paper_ledger_rebuilds (status)",
        "CREATE UNIQUE INDEX uq_matching_active_scope ON paper_matching_runs (trade_date, scope_key) WHERE status = 'running'",
    )
    for statement in statements:
        connection.execute(text(statement))


def _enum_types(connection: Connection) -> set[str]:
    return (
        set(
            connection.execute(
                text("SELECT typname FROM pg_type WHERE typnamespace = current_schema()::regnamespace")
            ).scalars()
        )
        & EXPECTED_TYPE_NAMES
    )


def _enum_labels(connection: Connection, type_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typnamespace = current_schema()::regnamespace AND t.typname = :type_name "
                "ORDER BY e.enumsortorder"
            ),
            {"type_name": type_name},
        ).scalars()
    )


def _column_type(connection: Connection, table_name: str, column_name: str) -> str:  # noqa: E501
    return str(
        connection.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid WHERE c.relnamespace = current_schema()::regnamespace AND c.relname = :table_name AND a.attname = :column_name"
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar_one()
    )


def _index_exists(connection: Connection, index_name: str) -> bool:
    return bool(
        connection.execute(text("SELECT to_regclass(:index_name) IS NOT NULL"), {"index_name": index_name}).scalar_one()
    )


def _table_exists(connection: Connection, table_name: str) -> bool:
    return bool(
        connection.execute(text("SELECT to_regclass(:table_name) IS NOT NULL"), {"table_name": table_name}).scalar_one()
    )


def test_adapter_preflight_does_not_convert_matching_status(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _enum_types(connection) == set()


def test_adapter_apply_and_rollback_preserve_matching_run_enum_and_index(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=False)
        assert PAPER_TRADING_ENUM_ADAPTER.apply(connection) is True
        PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=False)

        assert _column_type(connection, "paper_matching_runs", "status") == "paper_matching_run_status"
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _index_exists(connection, "uq_matching_active_scope")
        assert "completed_with_warnings" in _enum_labels(connection, "paper_matching_run_status")

        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=True)
        assert PAPER_TRADING_ENUM_ADAPTER.rollback(connection) is True
        PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=True)

        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _enum_types(connection) == set()
        assert _index_exists(connection, "uq_matching_active_scope")


def test_dry_run_reports_every_group_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        result = migrate_paper_trading_enums(connection, dry_run=True)
        assert result.dry_run is True
        assert result.converted is False
        assert {group.type_name for group in result.groups} == EXPECTED_TYPE_NAMES
        assert _enum_types(connection) == set()


def test_unknown_legacy_value_aborts_all_groups_without_conversion(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text("INSERT INTO paper_orders (id, side, status, market) VALUES (1, 'borrow', 'new', 'a_share')")
        )
        with pytest.raises(PaperTradingEnumMigrationError, match="paper_order_side"):
            migrate_paper_trading_enums(connection)
        assert _column_type(connection, "paper_accounts", "status") == "character varying(20)"
        assert _enum_types(connection) == set()


def test_apply_preserves_cataloged_defaults_and_ordinary_indexes(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        result = migrate_paper_trading_enums(connection)
        assert result.converted is True
        assert _column_type(connection, "paper_orders", "side") == "paper_order_side"
        assert _column_type(connection, "paper_trades", "side") == "paper_order_side"
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _index_exists(connection, "ix_paper_orders_status")
        assert _index_exists(connection, "ix_paper_position_round_trips_status")
        assert _index_exists(connection, "uq_matching_active_scope")
        savepoint = connection.begin_nested()
        try:
            with pytest.raises(Exception):
                connection.execute(
                    text("INSERT INTO paper_orders (id, side, status, market) VALUES (2, 'borrow', 'new', 'a_share')")
                )
        finally:
            savepoint.rollback()
        assert migrate_paper_trading_enums(connection).converted is False


def test_apply_leaves_preconverted_group_columns_defaults_and_indexes_untouched(postgres_schema):
    engine, schema = postgres_schema
    statements: list[str] = []
    with _connection(engine, schema) as connection:
        connection.execute(text("CREATE TYPE paper_market AS ENUM ('a_share', 'hk_connect')"))
        for table_name, index_name in (
            ("paper_orders", "ix_paper_orders_market"),
            ("paper_positions", "ix_paper_positions_market"),
            ("paper_position_lots", "ix_paper_position_lots_market"),
            ("paper_trades", "ix_paper_trades_market"),
            ("paper_trade_validity_checks", "ix_paper_trade_validity_checks_market"),
        ):
            connection.execute(text(f"DROP INDEX {index_name}"))
            connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN market DROP DEFAULT"))
            connection.execute(
                text(f"ALTER TABLE {table_name} ALTER COLUMN market TYPE paper_market USING market::text::paper_market")
            )
            connection.execute(
                text(f"ALTER TABLE {table_name} ALTER COLUMN market SET DEFAULT 'a_share'::paper_market")
            )
            connection.execute(text(f"CREATE INDEX {index_name} ON {table_name} (market)"))

        @event.listens_for(connection, "before_cursor_execute")
        def capture_ddl(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "paper_orders", "market") == "paper_market"
        assert _index_exists(connection, "ix_paper_orders_market")
        assert (
            connection.execute(
                text(
                    "SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d "
                    "JOIN pg_class c ON c.oid = d.adrelid "
                    "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.adnum "
                    "WHERE c.relnamespace = current_schema()::regnamespace "
                    "AND c.relname = 'paper_orders' AND a.attname = 'market'"
                )
            ).scalar_one()
            == "'a_share'::paper_market"
        )

    emitted_ddl = "\n".join(statements).lower()
    assert "alter table paper_orders alter column market" not in emitted_ddl
    assert "drop index ix_paper_orders_market" not in emitted_ddl


def test_apply_creates_missing_dependent_operational_tables_after_enum_conversion(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        connection.execute(text("DROP TABLE paper_account_snapshots"))
        connection.execute(text("DROP TABLE paper_valuation_gaps"))
        assert not _table_exists(connection, "paper_account_snapshots")
        assert not _table_exists(connection, "paper_valuation_gaps")

        result = migrate_paper_trading_enums(connection)

        assert result.converted is False
        assert _table_exists(connection, "paper_account_snapshots")
        assert _table_exists(connection, "paper_valuation_gaps")


def test_dry_run_leaves_missing_operational_tables_absent_after_enum_conversion(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        connection.execute(text("DROP TABLE paper_account_snapshots"))
        connection.execute(text("DROP TABLE paper_valuation_gaps"))

        result = migrate_paper_trading_enums(connection, dry_run=True)

        assert result.dry_run is True
        assert not _table_exists(connection, "paper_account_snapshots")
        assert not _table_exists(connection, "paper_valuation_gaps")


def test_rollback_leaves_missing_operational_tables_absent_after_enum_conversion(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        connection.execute(text("DROP TABLE paper_account_snapshots"))
        connection.execute(text("DROP TABLE paper_valuation_gaps"))

        result = migrate_paper_trading_enums(connection, rollback=True)

        assert result.rolled_back is True
        assert _column_type(connection, "paper_orders", "side") == "character varying(10)"
        assert _enum_types(connection) == set()
        assert not _table_exists(connection, "paper_account_snapshots")
        assert not _table_exists(connection, "paper_valuation_gaps")


def test_type_label_mismatch_does_not_modify_existing_type(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("CREATE TYPE paper_order_side AS ENUM ('buy')"))
        with pytest.raises(PaperTradingEnumMigrationError, match="paper_order_side"):
            migrate_paper_trading_enums(connection)
        assert _enum_types(connection) == {"paper_order_side"}


def test_fresh_bootstrap_creates_all_enum_types(empty_postgres_schema):
    empty_engine, empty_schema = empty_postgres_schema
    with _connection(empty_engine, empty_schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        for group in PAPER_TRADING_ENUM_GROUPS:
            for column in group.columns:
                assert _table_exists(connection, column.table_name)
                assert _column_type(connection, column.table_name, column.column_name) == group.type_name
        assert _table_exists(connection, "paper_account_snapshots")
        assert _table_exists(connection, "paper_valuation_gaps")


def test_exact_default_mismatch_rejects_without_mutation(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN status SET DEFAULT 'disabled'"))
        with pytest.raises(PaperTradingEnumMigrationError, match="default mismatch"):
            migrate_paper_trading_enums(connection)
        assert _column_type(connection, "paper_accounts", "status") == "character varying(20)"
        assert _enum_types(connection) == set()


def test_rollback_rejects_non_column_enum_dependency_before_drop(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_paper_trading_enums(connection)
        connection.execute(text("CREATE VIEW paper_order_side_dependency AS SELECT 'buy'::paper_order_side AS side"))
        with pytest.raises(PaperTradingEnumMigrationError, match="paper_order_side: dependencies remain"):
            migrate_paper_trading_enums(connection, rollback=True)
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert (
            connection.execute(text("SELECT to_regclass('paper_order_side_dependency')")).scalar_one()
            == "paper_order_side_dependency"
        )
        assert _column_type(connection, "paper_orders", "side") == "paper_order_side"
        assert _column_type(connection, "paper_trades", "side") == "paper_order_side"
        assert _column_type(connection, "paper_matching_runs", "status") == "paper_matching_run_status"


def test_rollback_audit_normalizes_view_dependency_to_one_view_name(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_paper_trading_enums(connection)
        connection.execute(text("CREATE VIEW paper_order_side_dependency AS SELECT 'buy'::paper_order_side AS side"))

        audit = PAPER_TRADING_ENUM_ADAPTER.audit(connection, rollback=True)

    order_side = next(group for group in audit.groups if group.type_name == "paper_order_side")
    assert order_side.dependencies == ("view paper_order_side_dependency",)


def test_rollback_rejects_undeclared_partial_index_enum_dependency(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_paper_trading_enums(connection)
        connection.execute(
            text(
                "CREATE INDEX paper_matching_running_dependency ON paper_matching_runs (id) "
                "WHERE status = 'running'::paper_matching_run_status"
            )
        )

        with pytest.raises(PaperTradingEnumMigrationError, match="paper_matching_run_status: dependencies remain"):
            migrate_paper_trading_enums(connection, rollback=True)

        assert _column_type(connection, "paper_matching_runs", "status") == "paper_matching_run_status"


def test_rollback_restores_exact_varchar_types_and_indexes(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_paper_trading_enums(connection)
        result = migrate_paper_trading_enums(connection, rollback=True)
        assert result.rolled_back is True
        assert _column_type(connection, "paper_orders", "side") == "character varying(10)"
        assert _enum_types(connection) == set()
        assert _index_exists(connection, "ix_paper_orders_status")
        assert _index_exists(connection, "uq_matching_active_scope")
