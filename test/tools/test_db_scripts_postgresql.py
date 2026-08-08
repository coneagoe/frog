from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from storage.enum_governance import migrate_enums
from storage.enum_migration import STORAGE_ENUM_ADAPTER, STORAGE_ENUM_GROUPS

ROOT = Path(__file__).resolve().parents[2]
STORAGE_ENUM_TYPES = {
    "blackroom_market",
    "blackroom_source",
    "daily_bar_diagnostic_adjust",
    "daily_bar_diagnostic_classification",
    "ssf_change_signal_status",
}
STORAGE_ENUM_LABELS = {group.type_name: group.labels for group in STORAGE_ENUM_GROUPS}


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


@pytest.fixture()
def postgres_schema() -> Iterator[tuple[Engine, str]]:
    engine = _engine()
    schema = f"db_scripts_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(text("CREATE TABLE paper_orders (id integer PRIMARY KEY)"))
        connection.execute(
            text("CREATE TABLE paper_trades (id integer PRIMARY KEY, order_id integer REFERENCES paper_orders(id))")
        )
        connection.execute(
            text(
                "CREATE TABLE paper_trade_validity_checks (id integer PRIMARY KEY, "
                "order_id integer REFERENCES paper_orders(id))"
            )
        )
        _create_legacy_storage_tables(connection)
        migrate_enums(connection, adapters=(STORAGE_ENUM_ADAPTER,))
        for type_name in STORAGE_ENUM_TYPES:
            assert enum_type_exists(connection, schema, type_name)
    try:
        yield engine, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _run_script(script: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.setdefault("COMPOSE_PROJECT_NAME", "frog")
    required_compose_environment = {
        "ALERT_EMAILS": "test@example.com",
        "PAPER_TRADING_API_TOKEN": "test-token",
        "SMTP_HOST": "localhost",
        "SMTP_MAIL_FROM": "test@example.com",
        "SMTP_PASSWORD": "test-password",
        "SMTP_PORT": "25",
        "SMTP_USER": "test-user",
        "TUSHARE_TOKEN": "test-token",
    }
    for name, value in required_compose_environment.items():
        environment.setdefault(name, value)
    return subprocess.run(
        ["bash", str(ROOT / "tools" / script), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


def foreign_key_exists(connection: Connection, schema: str, table: str, constraint: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM pg_constraint AS foreign_key "
                "JOIN pg_class AS source_table ON source_table.oid = foreign_key.conrelid "
                "JOIN pg_namespace AS source_schema ON source_schema.oid = source_table.relnamespace "
                "WHERE foreign_key.contype = 'f' "
                "AND source_schema.nspname = :schema "
                "AND source_table.relname = :table "
                "AND foreign_key.conname = :constraint"
                ")"
            ),
            {"schema": schema, "table": table, "constraint": constraint},
        ).scalar_one()
    )


def table_exists(connection: Connection, schema: str, table: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": f'"{schema}"."{table}"'},
        ).scalar_one()
    )


def enum_type_exists(connection: Connection, schema: str, type_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = :schema AND t.typname = :type_name)"
            ),
            {"schema": schema, "type_name": type_name},
        ).scalar_one()
    )


def constraint_exists(connection: Connection, schema: str, table: str, name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :schema AND t.relname = :table AND c.conname = :name)"
            ),
            {"schema": schema, "table": table, "name": name},
        ).scalar_one()
    )


def enum_labels(connection: Connection, schema: str, type_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = :schema AND t.typname = :type_name "
                "ORDER BY e.enumsortorder"
            ),
            {"schema": schema, "type_name": type_name},
        ).scalars()
    )


def column_type(connection: Connection, schema: str, table: str, column: str) -> tuple[str, str]:
    type_schema, type_name = connection.execute(
        text(
            "SELECT type_schema.nspname, column_type.typname FROM pg_attribute a "
            "JOIN pg_class table_class ON table_class.oid = a.attrelid "
            "JOIN pg_namespace table_schema ON table_schema.oid = table_class.relnamespace "
            "JOIN pg_type column_type ON column_type.oid = a.atttypid "
            "JOIN pg_namespace type_schema ON type_schema.oid = column_type.typnamespace "
            "WHERE table_schema.nspname = :schema AND table_class.relname = :table "
            "AND a.attname = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).one()
    return str(type_schema), str(type_name)


def _create_legacy_storage_tables(connection: Connection) -> None:
    statements = (
        "CREATE TABLE blackroom_records ("
        "id integer primary key, market varchar(5) NOT NULL DEFAULT 'A', "
        "source varchar(50) NOT NULL DEFAULT 'manual')",
        "CREATE TABLE daily_bar_diagnostics ("
        "id integer primary key, adjust varchar(10) NOT NULL, "
        "classification varchar(50) NOT NULL, provider_outcomes jsonb NOT NULL)",
        "CREATE TABLE ssf_change_signals ("
        "id integer primary key, status varchar(20) NOT NULL DEFAULT 'signal', "
        "event_types jsonb NOT NULL)",
        "INSERT INTO daily_bar_diagnostics VALUES (1, 'bfq', 'downloaded', '[{\"status\": \"downloaded\"}]'::jsonb)",
        "INSERT INTO ssf_change_signals VALUES (1, 'signal', '[\"increase\"]'::jsonb)",
    )
    for statement in statements:
        connection.execute(text(statement))


def _assert_foreign_keys_and_selected_table_remain(connection: Connection, schema: str) -> None:
    assert foreign_key_exists(connection, schema, "paper_trades", "paper_trades_order_id_fkey")
    assert foreign_key_exists(
        connection,
        schema,
        "paper_trade_validity_checks",
        "paper_trade_validity_checks_order_id_fkey",
    )
    assert table_exists(connection, schema, "paper_orders")


@pytest.mark.parametrize(
    ("table", "enum_types", "enum_columns", "check_name", "expected_row"),
    (
        (
            "daily_bar_diagnostics",
            ("daily_bar_diagnostic_adjust", "daily_bar_diagnostic_classification"),
            (("adjust", "daily_bar_diagnostic_adjust"), ("classification", "daily_bar_diagnostic_classification")),
            "ck_daily_bar_diagnostics_provider_outcome_status",
            ("bfq", "downloaded", [{"status": "downloaded"}]),
        ),
        (
            "ssf_change_signals",
            ("ssf_change_signal_status",),
            (("status", "ssf_change_signal_status"),),
            "ck_ssf_change_signals_event_types",
            ("signal", ["increase"]),
        ),
    ),
)
def test_selected_storage_table_export_restores_enums_data_and_json_check(
    postgres_schema: tuple[Engine, str],
    tmp_path: Path,
    table: str,
    enum_types: tuple[str, ...],
    enum_columns: tuple[tuple[str, str], ...],
    check_name: str,
    expected_row: tuple[object, ...],
) -> None:
    engine, schema = postgres_schema
    dump_file = tmp_path / f"{table}.sql"

    export = _run_script(
        "db_export.sh",
        ["--no-gzip", "--schema", schema, "--table", table, "--out", str(dump_file)],
    )

    assert export.returncode == 0, export.stderr
    dump = dump_file.read_text(encoding="utf-8")
    table_marker = f"-- Name: {table}; Type: TABLE; Schema: {schema};"
    for type_name in enum_types:
        assert dump.index(f'CREATE TYPE "{schema}"."{type_name}"') < dump.index(table_marker)
    assert check_name in dump

    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    imported = _run_script(
        "db_import.sh",
        ["--schema", schema, "--table", table, "--in", str(dump_file)],
    )

    assert imported.returncode == 0, imported.stderr
    with engine.connect() as connection:
        for type_name in enum_types:
            assert enum_type_exists(connection, schema, type_name)
            assert enum_labels(connection, schema, type_name) == STORAGE_ENUM_LABELS[type_name]
        assert table_exists(connection, schema, table)
        for column, type_name in enum_columns:
            assert column_type(connection, schema, table, column) == (schema, type_name)
        restored_row = connection.execute(text(f'SELECT * FROM "{schema}"."{table}"')).one()
        assert tuple(restored_row[1:]) == expected_row
        assert constraint_exists(connection, schema, table, check_name)


def test_clean_selected_table_export_is_rejected_before_mutation(
    postgres_schema: tuple[Engine, str], tmp_path: Path
) -> None:
    engine, schema = postgres_schema

    output_file = tmp_path / "orders.sql"
    output_file.write_text("existing dump\n", encoding="utf-8")
    result = _run_script(
        "db_export.sh",
        [
            "--clean",
            "--no-gzip",
            "--table",
            "paper_orders",
            "--schema",
            schema,
            "--out",
            str(output_file),
        ],
    )

    assert result.returncode != 0
    assert "cannot be combined with --table" in result.stderr
    assert output_file.read_text(encoding="utf-8") == "existing dump\n"
    with engine.connect() as connection:
        _assert_foreign_keys_and_selected_table_remain(connection, schema)


def test_clean_selected_table_import_rejects_inbound_foreign_keys_before_mutation(
    postgres_schema: tuple[Engine, str], tmp_path: Path
) -> None:
    engine, schema = postgres_schema
    input_file = tmp_path / "orders.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    result = _run_script(
        "db_import.sh",
        [
            "--clean",
            "--table",
            "paper_orders",
            "--schema",
            schema,
            "--in",
            str(input_file),
        ],
    )

    assert result.returncode != 0
    assert "unselected inbound foreign key" in result.stderr
    with engine.connect() as connection:
        _assert_foreign_keys_and_selected_table_remain(connection, schema)
