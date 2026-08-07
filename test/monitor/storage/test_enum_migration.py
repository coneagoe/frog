# ruff: noqa: E501

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from monitor.storage.enum_migration import (
    MONITOR_ENUM_GROUPS,
    MonitorEnumMigrationError,
    migrate_monitor_enums,
)

EXPECTED_TYPE_NAMES = {group.type_name for group in MONITOR_ENUM_GROUPS}
CONDITION_CHECK_NAME = "ck_stock_monitor_targets_condition_type"


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    return create_engine(url)


@pytest.fixture()
def postgres_schema():
    engine = _engine()
    schema = f"monitor_enum_migration_{uuid.uuid4().hex}"
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


def _connection(engine: Engine, schema: str) -> Connection:
    connection = engine.connect()
    connection.execute(text(f'SET search_path TO "{schema}"'))
    return connection


def _create_legacy_schema(connection: Connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE stock_monitor_targets ("
            "id integer primary key, stock_code varchar(10) NOT NULL, market varchar(5) NOT NULL DEFAULT 'A', "
            "condition jsonb NOT NULL, frequency varchar(10) NOT NULL DEFAULT 'daily', "
            "reset_mode varchar(10) NOT NULL DEFAULT 'auto')"
        )
    )
    connection.execute(
        text(
            "CREATE TABLE forecast_ssf_candidates ("
            "stock_code varchar(6) primary key, market varchar(5) NOT NULL DEFAULT 'A', "
            "report_end_date date NOT NULL, state varchar(32) NOT NULL, state_reason varchar(128) NOT NULL)"
        )
    )


def _enum_types(connection: Connection) -> set[str]:
    return (
        set(
            connection.execute(
                text("SELECT typname FROM pg_type WHERE typnamespace = current_schema()::regnamespace")
            ).scalars()
        )
        & EXPECTED_TYPE_NAMES
    )


def _column_type(connection: Connection, table_name: str, column_name: str) -> str:
    return str(
        connection.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relnamespace = current_schema()::regnamespace "
                "AND c.relname = :table_name AND a.attname = :column_name"
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar_one()
    )


def _column_default(connection: Connection, table_name: str, column_name: str) -> str | None:
    return connection.execute(
        text(
            "SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d "
            "JOIN pg_class c ON c.oid = d.adrelid "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.adnum "
            "WHERE c.relnamespace = current_schema()::regnamespace "
            "AND c.relname = :table_name AND a.attname = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one_or_none()


def _check_exists(connection: Connection) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE c.connamespace = current_schema()::regnamespace "
                "AND t.relname = 'stock_monitor_targets' AND c.conname = :constraint_name"
            ),
            {"constraint_name": CONDITION_CHECK_NAME},
        ).scalar_one_or_none()
    )


def _assert_insert_rejected(connection: Connection, statement: str) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(Exception):
            connection.execute(text(statement))
    finally:
        savepoint.rollback()


def test_dry_run_preflights_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        result = migrate_monitor_enums(connection, dry_run=True)

        assert result.dry_run is True
        assert result.converted is False
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_unknown_legacy_label_aborts_before_any_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                "VALUES (1, '600001', 'US', '{\"type\": \"price_threshold\", \"direction\": \"above\", \"value\": 10}'::jsonb, 'daily', 'auto')"
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="monitor_market"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_invalid_legacy_condition_aborts_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                "VALUES (1, '600001', 'A', '{\"workflow\": \"forecast_ssf_ma20\"}'::jsonb, 'daily', 'auto')"
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="condition"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_type_dependent_invalid_legacy_condition_aborts_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
                'VALUES (1, \'600001\', \'A\', \'{"type": "ma_cross", "direction": "golden", "fast": 20, "slow": 10}\'::jsonb, \'daily\', \'auto\')'
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="condition"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)


def test_conflicting_named_condition_check_aborts_before_any_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "ALTER TABLE stock_monitor_targets ADD CONSTRAINT ck_stock_monitor_targets_condition_type "
                "CHECK (jsonb_typeof(condition) = 'object' AND condition->>'type' IN ('price_threshold', 'unknown'))"
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="conflicting condition constraint"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()


def test_apply_converts_columns_and_rejects_direct_invalid_values(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        result = migrate_monitor_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "stock_monitor_targets", "market") == "monitor_market"
        assert _column_type(connection, "forecast_ssf_candidates", "state") == "forecast_ssf_candidate_state"
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (1, '600001', 'US', '{\"type\": \"price_threshold\", \"direction\": \"above\", \"value\": 10}'::jsonb, 'daily', 'auto')",
        )
        _assert_insert_rejected(
            connection,
            "INSERT INTO stock_monitor_targets (id, stock_code, market, condition, frequency, reset_mode) "
            "VALUES (1, '600001', 'A', '{\"type\": \"unknown\"}'::jsonb, 'daily', 'auto')",
        )


def test_second_apply_is_idempotent(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_monitor_enums(connection).converted is True

        result = migrate_monitor_enums(connection)

        assert result.converted is False
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)


def test_rollback_rejects_non_column_enum_dependency_before_drop(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)
        connection.execute(text("CREATE VIEW monitor_market_dependency AS SELECT 'A'::monitor_market AS market"))

        with pytest.raises(MonitorEnumMigrationError, match="monitor_market: dependencies remain"):
            migrate_monitor_enums(connection, rollback=True)

        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_exists(connection)


def test_rollback_restores_exact_legacy_types_defaults_and_removes_governance(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_monitor_enums(connection)

        result = migrate_monitor_enums(connection, rollback=True)

        assert result.rolled_back is True
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _column_type(connection, "stock_monitor_targets", "frequency") == "character varying(10)"
        assert _column_type(connection, "stock_monitor_targets", "reset_mode") == "character varying(10)"
        assert _column_type(connection, "forecast_ssf_candidates", "market") == "character varying(5)"
        assert _column_type(connection, "forecast_ssf_candidates", "state") == "character varying(32)"
        assert _column_default(connection, "stock_monitor_targets", "market") == "'A'::character varying"
        assert _column_default(connection, "stock_monitor_targets", "frequency") == "'daily'::character varying"
        assert _column_default(connection, "stock_monitor_targets", "reset_mode") == "'auto'::character varying"
        assert _column_default(connection, "forecast_ssf_candidates", "market") == "'A'::character varying"
        assert _enum_types(connection) == set()
        assert not _check_exists(connection)
