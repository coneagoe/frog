from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Enum as SqlAlchemyEnum
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from monitor.storage.enum_migration import MONITOR_ENUM_ADAPTER, MONITOR_ENUM_GROUPS
from paper_trading.domain.enums import DataGapRecoveryStatus
from paper_trading.storage.enum_migration import _ensure_recovery_append_only, migrate_paper_trading_enums
from storage.enum_governance import migrate_enums
from storage.enum_migration import STORAGE_ENUM_ADAPTER, STORAGE_ENUM_GROUPS
from storage.model import Base, User

ROOT = Path(__file__).resolve().parents[2]
STORAGE_ENUM_TYPES = {
    "blackroom_market",
    "blackroom_source",
    "daily_bar_diagnostic_adjust",
    "daily_bar_diagnostic_classification",
    "forecast_snapshot_status",
    "ssf_change_signal_status",
}
ENUM_LABELS = {group.type_name: group.labels for group in (*MONITOR_ENUM_GROUPS, *STORAGE_ENUM_GROUPS)}


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
    environment["COMPOSE_PROJECT_NAME"] = ROOT.name
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
        "CREATE TABLE forecast_snapshot_runs ("
        "id integer primary key, report_end_date date NOT NULL, announcement_start_date date NOT NULL, "
        "announcement_end_date date NOT NULL, attempt integer NOT NULL, status varchar(16) NOT NULL)",
        "CREATE TABLE forecast_snapshot_records ("
        "id integer primary key, run_id integer NOT NULL REFERENCES forecast_snapshot_runs(id), "
        "ts_code varchar(32) NOT NULL, "
        "announcement_date date NOT NULL, report_end_date date NOT NULL, forecast_type varchar(20) NOT NULL, "
        "growth_min double precision, growth_max double precision, source_order integer NOT NULL)",
        "CREATE TABLE ssf_change_signals ("
        "id integer primary key, status varchar(20) NOT NULL DEFAULT 'signal', "
        "event_types jsonb NOT NULL)",
        "INSERT INTO daily_bar_diagnostics VALUES (1, 'bfq', 'downloaded', '[{\"status\": \"downloaded\"}]'::jsonb)",
        "INSERT INTO ssf_change_signals VALUES (1, 'signal', '[\"increase\"]'::jsonb)",
    )
    for statement in statements:
        connection.execute(text(statement))


def _create_legacy_monitor_notification_tables(connection: Connection) -> None:
    statements = (
        "CREATE TABLE stock_monitor_targets ("
        "id integer primary key, stock_code varchar(10) NOT NULL, market varchar(5) NOT NULL DEFAULT 'A', "
        "condition jsonb NOT NULL, frequency varchar(10) NOT NULL DEFAULT 'daily', "
        "reset_mode varchar(10) NOT NULL DEFAULT 'auto', latest_error_kind varchar(32))",
        "CREATE TABLE forecast_ssf_candidates ("
        "stock_code varchar(6) primary key, market varchar(5) NOT NULL DEFAULT 'A', "
        "report_end_date date NOT NULL, state varchar(32) NOT NULL, state_reason varchar(128) NOT NULL)",
        "CREATE TABLE monitor_notifications ("
        "id uuid primary key, target_id integer NOT NULL, subject text NOT NULL, body text NOT NULL, "
        "state varchar(16) NOT NULL DEFAULT 'pending', attempt_count integer NOT NULL DEFAULT 0, "
        "next_attempt_at timestamptz NOT NULL, claimed_at timestamptz, delivered_at timestamptz, "
        "last_error text, created_at timestamptz NOT NULL DEFAULT now(), "
        "CONSTRAINT monitor_notifications_target_id_fkey FOREIGN KEY (target_id) "
        "REFERENCES stock_monitor_targets(id))",
    )
    for statement in statements:
        connection.execute(text(statement))
    migrate_enums(connection, adapters=(MONITOR_ENUM_ADAPTER,))


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
        ["--service", "test_db", "--no-gzip", "--schema", schema, "--table", table, "--out", str(dump_file)],
    )

    assert export.returncode == 0, export.stderr
    dump = dump_file.read_text(encoding="utf-8")
    table_marker = f"-- Name: {table}; Type: TABLE; Schema: {schema};"
    for type_name in enum_types:
        assert dump.index(f'CREATE TYPE "{schema}"."{type_name}"') < dump.index(table_marker)
    assert check_name in dump

    with engine.begin() as connection:
        if table == "daily_bar_diagnostics":
            connection.execute(
                text(
                    f'INSERT INTO "{schema}"."{table}" VALUES '
                    "(2, 'qfq', 'missing_market_data', '[{\"status\": \"empty\"}]'::jsonb)"
                )
            )
        else:
            connection.execute(text(f'INSERT INTO "{schema}"."{table}" VALUES (2, \'no_signal\', \'["exit"]\'::jsonb)'))

    imported = _run_script(
        "db_import.sh",
        ["--service", "test_db", "--clean", "--schema", schema, "--table", table, "--in", str(dump_file)],
    )

    assert imported.returncode == 0, imported.stderr
    with engine.connect() as connection:
        for type_name in enum_types:
            assert enum_type_exists(connection, schema, type_name)
            assert enum_labels(connection, schema, type_name) == ENUM_LABELS[type_name]
        assert table_exists(connection, schema, table)
        for column, type_name in enum_columns:
            assert column_type(connection, schema, table, column) == (schema, type_name)
        restored_rows = connection.execute(text(f'SELECT * FROM "{schema}"."{table}" ORDER BY id')).all()
        assert len(restored_rows) == 1
        restored_row = restored_rows[0]
        assert tuple(restored_row[1:]) == expected_row
        assert constraint_exists(connection, schema, table, check_name)


def test_full_export_import_preserves_data_gap_recovery_enum_registrations(
    postgres_schema: tuple[Engine, str], tmp_path: Path
) -> None:
    engine, schema = postgres_schema
    dump_file = tmp_path / "full.sql"

    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(
            text(
                "ALTER TABLE paper_orders ADD COLUMN side varchar(10) NOT NULL DEFAULT 'buy', "
                "ADD COLUMN status varchar(30) NOT NULL, "
                "ADD COLUMN validity_status varchar(20), "
                "ADD COLUMN validity_reason varchar(50), "
                "ADD COLUMN market varchar(20) NOT NULL DEFAULT 'a_share'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE paper_trades ADD COLUMN side varchar(10) NOT NULL DEFAULT 'buy', "
                "ADD COLUMN market varchar(20) NOT NULL DEFAULT 'a_share'"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE paper_trade_validity_checks ADD COLUMN side varchar(10) NOT NULL DEFAULT 'buy', "
                "ADD COLUMN status varchar(20) NOT NULL DEFAULT 'valid', "
                "ADD COLUMN reason_code varchar(50) NOT NULL, "
                "ADD COLUMN data_granularity varchar(20) NOT NULL DEFAULT 'daily', "
                "ADD COLUMN market varchar(20) NOT NULL DEFAULT 'a_share'"
            )
        )
        connection.execute(text("ALTER TABLE paper_orders ALTER COLUMN side DROP DEFAULT"))
        connection.execute(text("ALTER TABLE paper_orders ALTER COLUMN status DROP DEFAULT"))
        connection.execute(text("ALTER TABLE paper_trades ALTER COLUMN side DROP DEFAULT"))
        connection.execute(text("ALTER TABLE paper_trade_validity_checks ALTER COLUMN side DROP DEFAULT"))
        connection.execute(text("ALTER TABLE paper_trade_validity_checks ALTER COLUMN status DROP DEFAULT"))
        for statement in (
            "CREATE INDEX ix_paper_orders_status ON paper_orders (status)",
            "CREATE INDEX ix_paper_orders_validity_status ON paper_orders (validity_status)",
            "CREATE INDEX ix_paper_orders_market ON paper_orders (market)",
            "CREATE INDEX ix_paper_trades_market ON paper_trades (market)",
            "CREATE INDEX ix_paper_trade_validity_checks_status ON paper_trade_validity_checks (status)",
            "CREATE INDEX ix_paper_trade_validity_checks_market ON paper_trade_validity_checks (market)",
        ):
            connection.execute(text(statement))
        enum_types = {
            column.type
            for table in Base.metadata.sorted_tables
            for column in table.columns
            if isinstance(column.type, SqlAlchemyEnum)
        }
        for enum_type in enum_types:
            enum_type.create(connection, checkfirst=True)
        Base.metadata.create_all(connection, checkfirst=True)
        _ensure_recovery_append_only(connection)
        migrate_paper_trading_enums(connection)

    exported = _run_script(
        "db_export.sh",
        ["--service", "test_db", "--no-gzip", "--schema", schema, "--out", str(dump_file)],
    )
    assert exported.returncode == 0, exported.stderr
    dump = dump_file.read_text(encoding="utf-8")
    assert 'CREATE TYPE "' + schema + '"."paper_data_gap_recovery_status"' in dump
    assert f"-- Name: paper_data_gap_recovery_gaps; Type: TABLE; Schema: {schema};" in dump

    imported = _run_script(
        "db_import.sh",
        ["--service", "test_db", "--clean", "--schema", schema, "--in", str(dump_file)],
    )
    assert imported.returncode == 0, imported.stderr
    with engine.connect() as connection:
        assert enum_type_exists(connection, schema, "paper_data_gap_recovery_status")
        assert enum_labels(connection, schema, "paper_data_gap_recovery_status") == tuple(
            status.value for status in DataGapRecoveryStatus
        )
        assert table_exists(connection, schema, "paper_data_gap_recovery_gaps")


def test_full_export_import_preserves_recovery_append_only_triggers(
    postgres_schema: tuple[Engine, str], tmp_path: Path
) -> None:
    engine, schema = postgres_schema
    dump_file = tmp_path / "recovery.sql"
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(text("CREATE TABLE paper_data_gap_recovery_candidates (id integer primary key)"))
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION paper_data_gap_recovery_candidates_append_only() "
                "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'append-only'; END; $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER paper_data_gap_recovery_candidates_append_only "
                "BEFORE UPDATE OR DELETE ON paper_data_gap_recovery_candidates "
                "FOR EACH ROW EXECUTE FUNCTION paper_data_gap_recovery_candidates_append_only()"
            )
        )
    exported = _run_script(
        "db_export.sh", ["--service", "test_db", "--no-gzip", "--schema", schema, "--out", str(dump_file)]
    )
    assert exported.returncode == 0, exported.stderr
    dump = dump_file.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION" in dump
    imported = _run_script(
        "db_import.sh", ["--service", "test_db", "--clean", "--schema", schema, "--in", str(dump_file)]
    )
    assert imported.returncode == 0, imported.stderr
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_trigger "
                "WHERE tgname = 'paper_data_gap_recovery_candidates_append_only')"
            )
        ).scalar_one()


def test_plain_metadata_subset_create_does_not_install_recovery_triggers(
    postgres_schema: tuple[Engine, str],
) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        Base.metadata.create_all(connection, tables=[User.__table__])
        trigger_names = (
            connection.execute(
                text(
                    "SELECT tgname FROM pg_trigger AS trigger "
                    "JOIN pg_class AS table_ ON table_.oid = trigger.tgrelid "
                    "WHERE NOT trigger.tgisinternal AND table_.relname LIKE 'paper_data_gap_recovery_%'"
                )
            )
            .scalars()
            .all()
        )

    assert trigger_names == []


def test_monitor_notifications_export_restores_foreign_key_and_pending_row(
    postgres_schema: tuple[Engine, str], tmp_path: Path
) -> None:
    engine, schema = postgres_schema
    dump_file = tmp_path / "monitor_notifications.sql"

    with engine.begin() as connection:
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        _create_legacy_monitor_notification_tables(connection)
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets "
                "(id, stock_code, market, condition, frequency, reset_mode) VALUES "
                '(1, \'000001\', \'A\', \'{"type": "price_threshold", "direction": "above", "value": 1}\'::jsonb, '
                "'daily', 'auto')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO monitor_notifications "
                "(id, target_id, subject, body, state, attempt_count, next_attempt_at) VALUES "
                "('00000000-0000-0000-0000-000000000001', 1, 'Subject', 'Body', 'pending', 0, "
                "TIMESTAMPTZ '2026-09-08 00:00:00+00')"
            )
        )

    exported = _run_script(
        "db_export.sh",
        [
            "--service",
            "test_db",
            "--no-gzip",
            "--schema",
            schema,
            "--out",
            str(dump_file),
        ],
    )

    assert exported.returncode == 0, exported.stderr
    dump = dump_file.read_text(encoding="utf-8")
    table_marker = f"-- Name: monitor_notifications; Type: TABLE; Schema: {schema};"
    assert dump.index(f'CREATE TYPE "{schema}"."monitor_notification_delivery_state"') < dump.index(table_marker)

    imported = _run_script(
        "db_import.sh",
        [
            "--service",
            "test_db",
            "--clean",
            "--schema",
            schema,
            "--in",
            str(dump_file),
        ],
    )

    assert imported.returncode == 0, imported.stderr
    with engine.connect() as connection:
        assert enum_type_exists(connection, schema, "monitor_notification_delivery_state")
        assert (
            enum_labels(connection, schema, "monitor_notification_delivery_state")
            == ENUM_LABELS["monitor_notification_delivery_state"]
        )
        assert column_type(connection, schema, "monitor_notifications", "state") == (
            schema,
            "monitor_notification_delivery_state",
        )
        assert (
            connection.execute(text(f'SELECT state::text FROM "{schema}"."monitor_notifications"')).scalar_one()
            == "pending"
        )
        assert connection.execute(text(f'SELECT target_id FROM "{schema}"."monitor_notifications"')).scalar_one() == 1
        assert foreign_key_exists(connection, schema, "monitor_notifications", "monitor_notifications_target_id_fkey")


def test_clean_selected_table_export_is_rejected_before_mutation(
    postgres_schema: tuple[Engine, str], tmp_path: Path
) -> None:
    engine, schema = postgres_schema

    output_file = tmp_path / "orders.sql"
    output_file.write_text("existing dump\n", encoding="utf-8")
    result = _run_script(
        "db_export.sh",
        [
            "--service",
            "test_db",
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
            "--service",
            "test_db",
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
