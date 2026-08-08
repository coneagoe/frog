# ruff: noqa: E501

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from storage.enum_migration import (
    STORAGE_ENUM_ADAPTER,
    STORAGE_ENUM_GROUPS,
    StorageEnumMigrationError,
    migrate_storage_enums,
)

EXPECTED_TYPE_NAMES = {group.type_name for group in STORAGE_ENUM_GROUPS}
CHECK_NAMES = {
    "ck_daily_bar_diagnostics_provider_outcome_status",
    "ck_ssf_change_signals_event_types",
}


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


@pytest.fixture()
def postgres_schema():
    engine = _engine()
    schema = f"storage_enum_migration_{uuid.uuid4().hex}"
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
    statements = (
        "CREATE TABLE blackroom_records (id integer primary key, market varchar(5) NOT NULL DEFAULT 'A', source varchar(50) NOT NULL DEFAULT 'manual')",
        "CREATE TABLE daily_bar_diagnostics (id integer primary key, adjust varchar(10) NOT NULL, classification varchar(50) NOT NULL, provider_outcomes jsonb NOT NULL)",
        "CREATE TABLE ssf_change_signals (id integer primary key, status varchar(20) NOT NULL DEFAULT 'signal', event_types jsonb NOT NULL)",
    )
    for statement in statements:
        connection.execute(text(statement))


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


def _check_names(connection: Connection) -> set[str]:
    return set(
        connection.execute(
            text(
                "SELECT c.conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE c.connamespace = current_schema()::regnamespace "
                "AND c.conname IN ('ck_daily_bar_diagnostics_provider_outcome_status', 'ck_ssf_change_signals_event_types')"
            )
        ).scalars()
    )


def _check_definitions(connection: Connection) -> dict[str, str]:
    rows = connection.execute(
        text(
            "SELECT c.conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE c.connamespace = current_schema()::regnamespace "
            "AND c.conname IN ('ck_daily_bar_diagnostics_provider_outcome_status', 'ck_ssf_change_signals_event_types')"
        )
    ).all()
    return {str(row[0]): str(row[1]) for row in rows}


def _assert_rejected(connection: Connection, statement: str) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(Exception):
            connection.execute(text(statement))
    finally:
        savepoint.rollback()


def test_apply_converts_storage_values_and_enforces_json_contracts(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert STORAGE_ENUM_ADAPTER.apply(connection) is True

        for group in STORAGE_ENUM_GROUPS:
            assert _enum_labels(connection, group.type_name) == group.labels
            for column in group.columns:
                assert _column_type(connection, column.table_name, column.column_name) == group.type_name
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        assert _check_names(connection) == CHECK_NAMES
        assert all("storage_" not in definition for definition in _check_definitions(connection).values())
        assert _column_default(connection, "blackroom_records", "market") == "'A'::blackroom_market"
        assert _column_default(connection, "blackroom_records", "source") == "'manual'::blackroom_source"
        assert _column_default(connection, "ssf_change_signals", "status") == "'signal'::ssf_change_signal_status"

        _assert_rejected(connection, "INSERT INTO blackroom_records (id, market, source) VALUES (1, 'US', 'manual')")
        _assert_rejected(connection, "INSERT INTO blackroom_records (id, market, source) VALUES (1, 'A', 'unknown')")
        _assert_rejected(connection, "INSERT INTO daily_bar_diagnostics VALUES (1, 'raw', 'downloaded', '[]'::jsonb)")
        _assert_rejected(connection, "INSERT INTO daily_bar_diagnostics VALUES (1, 'bfq', 'unknown', '[]'::jsonb)")
        _assert_rejected(connection, "INSERT INTO ssf_change_signals VALUES (1, 'unknown', '[]'::jsonb)")
        _assert_rejected(
            connection,
            'INSERT INTO daily_bar_diagnostics VALUES (1, \'bfq\', \'downloaded\', \'[{"provider": "x", "status": "partial"}]\'::jsonb)',
        )
        _assert_rejected(
            connection,
            "INSERT INTO daily_bar_diagnostics VALUES (1, 'bfq', 'downloaded', '{}'::jsonb)",
        )
        _assert_rejected(
            connection,
            "INSERT INTO daily_bar_diagnostics VALUES (1, 'bfq', 'downloaded', '[1]'::jsonb)",
        )
        _assert_rejected(
            connection,
            "INSERT INTO daily_bar_diagnostics VALUES (1, 'bfq', 'downloaded', '[{}]'::jsonb)",
        )
        _assert_rejected(
            connection,
            "INSERT INTO daily_bar_diagnostics VALUES (1, 'bfq', 'downloaded', '[{\"status\": null}]'::jsonb)",
        )
        _assert_rejected(connection, "INSERT INTO ssf_change_signals VALUES (1, 'signal', '{}'::jsonb)")
        _assert_rejected(connection, "INSERT INTO ssf_change_signals VALUES (1, 'signal', '[1]'::jsonb)")
        _assert_rejected(connection, "INSERT INTO ssf_change_signals VALUES (1, 'signal', '[\"split\"]'::jsonb)")


def test_preflight_rejects_invalid_legacy_provider_outcomes_before_creating_types(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO daily_bar_diagnostics VALUES "
                '(1, \'bfq\', \'downloaded\', \'[{"provider": "x", "status": "partial"}]\'::jsonb)'
            )
        )

        with pytest.raises(StorageEnumMigrationError, match="daily_bar_diagnostics.id=1"):
            STORAGE_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert _enum_types(connection) == set()


def test_preflight_rejects_conflicting_named_json_constraint_before_creating_types(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "ALTER TABLE daily_bar_diagnostics ADD CONSTRAINT "
                "ck_daily_bar_diagnostics_provider_outcome_status "
                "CHECK (jsonb_typeof(provider_outcomes) = 'array')"
            )
        )

        with pytest.raises(StorageEnumMigrationError, match="conflicting constraint"):
            STORAGE_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert _enum_types(connection) == set()


def test_json_checks_remain_enforced_after_legacy_validator_functions_are_replaced(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert STORAGE_ENUM_ADAPTER.apply(connection) is True
        connection.execute(
            text(
                "CREATE FUNCTION storage_provider_outcomes_are_valid(value jsonb) RETURNS boolean "
                "LANGUAGE sql IMMUTABLE AS $$ SELECT true $$"
            )
        )
        connection.execute(
            text(
                "CREATE FUNCTION storage_ssf_event_types_are_valid(value jsonb) RETURNS boolean "
                "LANGUAGE sql IMMUTABLE AS $$ SELECT true $$"
            )
        )

        _assert_rejected(
            connection,
            'INSERT INTO daily_bar_diagnostics VALUES (1, \'bfq\', \'downloaded\', \'[{"provider": "x", "status": "partial"}]\'::jsonb)',
        )
        _assert_rejected(connection, "INSERT INTO ssf_change_signals VALUES (1, 'signal', '[\"split\"]'::jsonb)")


@pytest.mark.parametrize(
    ("statement", "error"),
    (
        ("ALTER TABLE blackroom_records ALTER COLUMN market TYPE varchar(6)", "incompatible blackroom_records.market"),
        ("DROP TABLE ssf_change_signals", "partially missing governed tables"),
        (
            "INSERT INTO blackroom_records (id, market, source) VALUES (1, 'US', 'manual')",
            "blackroom_market: unknown legacy values",
        ),
    ),
)
def test_preflight_rejects_incompatible_legacy_schema_before_creating_types(postgres_schema, statement, error) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text(statement))

        with pytest.raises(StorageEnumMigrationError, match=error):
            STORAGE_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert _enum_types(connection) == set()


def test_second_apply_is_idempotent_and_rollback_restores_legacy_schema(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_storage_enums(connection).converted is True
        assert STORAGE_ENUM_ADAPTER.apply(connection) is False

        result = migrate_storage_enums(connection, rollback=True)

        assert result.rolled_back is True
        assert _column_type(connection, "blackroom_records", "market") == "character varying(5)"
        assert _column_type(connection, "blackroom_records", "source") == "character varying(50)"
        assert _column_type(connection, "daily_bar_diagnostics", "adjust") == "character varying(10)"
        assert _column_type(connection, "daily_bar_diagnostics", "classification") == "character varying(50)"
        assert _column_type(connection, "ssf_change_signals", "status") == "character varying(20)"
        assert _column_default(connection, "blackroom_records", "market") == "'A'::character varying"
        assert _column_default(connection, "blackroom_records", "source") == "'manual'::character varying"
        assert _column_default(connection, "ssf_change_signals", "status") == "'signal'::character varying"
        assert _enum_types(connection) == set()
        assert _check_names(connection) == set()
        assert _check_definitions(connection) == {}


def test_rollback_rejects_unmanaged_storage_enum_dependency(postgres_schema) -> None:
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_storage_enums(connection)
        connection.execute(text("CREATE VIEW blackroom_market_dependency AS SELECT 'A'::blackroom_market AS market"))

        with pytest.raises(StorageEnumMigrationError, match="blackroom_market: dependencies remain"):
            migrate_storage_enums(connection, rollback=True)

        assert _column_type(connection, "blackroom_records", "market") == "blackroom_market"
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        for group in STORAGE_ENUM_GROUPS:
            for column in group.columns:
                assert _column_type(connection, column.table_name, column.column_name) == group.type_name
