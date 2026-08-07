from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[2]


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
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
    return connection.execute(
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


def table_exists(connection: Connection, schema: str, table: str) -> bool:
    return connection.execute(
        text("SELECT to_regclass(:table_name) IS NOT NULL"),
        {"table_name": f'"{schema}"."{table}"'},
    ).scalar_one()


def _assert_foreign_keys_and_selected_table_remain(connection: Connection, schema: str) -> None:
    assert foreign_key_exists(connection, schema, "paper_trades", "paper_trades_order_id_fkey")
    assert foreign_key_exists(
        connection,
        schema,
        "paper_trade_validity_checks",
        "paper_trade_validity_checks_order_id_fkey",
    )
    assert table_exists(connection, schema, "paper_orders")


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
