# ruff: noqa: E501

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

from paper_trading.domain.enums import MigrationRepairReason
from paper_trading.storage.enum_migration import (
    PAPER_TRADING_ENUM_ADAPTER,
    PAPER_TRADING_ENUM_GROUPS,
    PaperTradingEnumMigrationError,
    ensure_snapshot_series_enum_types,
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
        "CREATE TABLE paper_accounts (id integer primary key, status varchar(20) NOT NULL DEFAULT 'active', fee_preset varchar(30) NOT NULL DEFAULT 'a_share', migration_repair_reason varchar(40))",
        "CREATE TABLE paper_cash_ledger (id integer primary key, event_type varchar(20) NOT NULL)",
        "CREATE TABLE paper_positions (id integer primary key, account_id integer NOT NULL, symbol varchar(20) NOT NULL, source varchar(20) NOT NULL DEFAULT 'trade', market varchar(20) NOT NULL DEFAULT 'a_share', CONSTRAINT uq_paper_positions_account_symbol UNIQUE (account_id, symbol))",
        "CREATE TABLE paper_position_lots (id integer primary key, source varchar(20) NOT NULL DEFAULT 'trade', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_orders (id integer primary key, side varchar(10) NOT NULL, status varchar(30) NOT NULL, validity_status varchar(20), market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_trades (id integer primary key, side varchar(10) NOT NULL, market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_position_round_trips (id integer primary key, account_id integer NOT NULL, symbol varchar(20) NOT NULL, status varchar(20) NOT NULL DEFAULT 'open')",
        "CREATE TABLE paper_trade_validity_checks (id integer primary key, side varchar(10) NOT NULL, status varchar(20) NOT NULL, data_granularity varchar(20) NOT NULL DEFAULT 'daily', market varchar(20) NOT NULL DEFAULT 'a_share')",
        "CREATE TABLE paper_pending_settlement (id integer primary key, source varchar(20) NOT NULL)",
        "CREATE TABLE paper_ledger_rebuilds (id integer primary key, status varchar(20) NOT NULL)",
        "CREATE TABLE daily_bar_diagnostics (id integer primary key, business_date date NOT NULL, stock_id varchar(20) NOT NULL, adjust varchar(10) NOT NULL, classification varchar(50) NOT NULL, provider_outcomes jsonb NOT NULL, CONSTRAINT uq_daily_bar_diagnostics_business_key UNIQUE (business_date, stock_id, adjust))",
        "CREATE TABLE paper_matching_runs (id integer primary key, trade_date date NOT NULL, scope_key varchar(40) NOT NULL, status varchar(32) NOT NULL)",
        "CREATE TABLE paper_etf_eligibility (symbol varchar(20) primary key, name varchar(200) NOT NULL, exchange varchar(10) NOT NULL, list_status varchar(10) NOT NULL, last_seen_at timestamptz NOT NULL, last_refresh_at timestamptz NOT NULL, status varchar(20) NOT NULL DEFAULT 'unknown', reviewed_at timestamptz, reviewed_by varchar(100), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())",
        "CREATE TABLE paper_account_snapshots (id integer primary key, account_id integer NOT NULL, point_type varchar(20) NOT NULL DEFAULT 'trading', quality_status varchar(20) NOT NULL DEFAULT 'valid')",
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
        "CREATE INDEX ix_paper_etf_eligibility_status ON paper_etf_eligibility (status)",
        "CREATE UNIQUE INDEX uq_paper_account_snapshots_account_initial ON paper_account_snapshots (account_id) WHERE point_type = 'initial'",
    )
    for statement in statements:
        connection.execute(text(statement))


def _create_legacy_diagnostics_table(connection: Connection) -> None:
    connection.execute(
        text(
            "CREATE TABLE daily_bar_diagnostics ("
            "id integer primary key, business_date date NOT NULL, stock_id varchar(20) NOT NULL, "
            "adjust varchar(10) NOT NULL, classification varchar(50) NOT NULL, provider_outcomes jsonb NOT NULL, "
            "CONSTRAINT uq_daily_bar_diagnostics_business_key UNIQUE (business_date, stock_id, adjust))"
        )
    )
    connection.execute(
        text("INSERT INTO daily_bar_diagnostics VALUES (1, '2026-08-07', '000001', 'bfq', 'downloaded', '[]'::jsonb)")
    )


def _drop_reduced_schema_key_columns(connection: Connection) -> None:
    connection.execute(text("ALTER TABLE paper_positions DROP CONSTRAINT uq_paper_positions_account_symbol"))
    connection.execute(text("ALTER TABLE paper_positions DROP COLUMN account_id"))
    connection.execute(text("ALTER TABLE paper_positions DROP COLUMN symbol"))
    connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP CONSTRAINT uq_daily_bar_diagnostics_business_key"))
    connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP COLUMN business_date"))
    connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP COLUMN stock_id"))


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


def _column_type(connection: Connection, table_name: str, column_name: str) -> str | None:  # noqa: E501
    value = connection.execute(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid WHERE c.relnamespace = current_schema()::regnamespace AND c.relname = :table_name AND a.attname = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one_or_none()
    return None if value is None else str(value)


def _index_exists(connection: Connection, index_name: str) -> bool:
    return bool(
        connection.execute(text("SELECT to_regclass(:index_name) IS NOT NULL"), {"index_name": index_name}).scalar_one()
    )


def _constraint_columns(connection: Connection, table_name: str, constraint_name: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT a.attname FROM pg_constraint c "
                "JOIN unnest(c.conkey) WITH ORDINALITY AS key(attnum, ordinality) ON true "
                "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = key.attnum "
                "WHERE c.conrelid = CAST(:table_name AS regclass) AND c.conname = :constraint_name "
                "ORDER BY key.ordinality"
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).scalars()
    )


def _check_constraint_exists(connection: Connection, table_name: str, constraint_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_constraint "
                "WHERE conrelid = CAST(:table_name AS regclass) AND conname = :constraint_name AND contype = 'c')"
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).scalar_one()
    )


def _table_exists(connection: Connection, table_name: str) -> bool:
    return bool(
        connection.execute(text("SELECT to_regclass(:table_name) IS NOT NULL"), {"table_name": table_name}).scalar_one()
    )


def _repair_reason_group():
    return next(
        group for group in PAPER_TRADING_ENUM_GROUPS if group.type_name == "paper_account_migration_repair_reason"
    )


def test_migration_repair_reason_group_declares_nullable_varchar40_column():
    group = _repair_reason_group()
    assert group.labels == (MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value,)
    assert len(group.columns) == 1
    column = group.columns[0]
    assert (column.table_name, column.column_name) == ("paper_accounts", "migration_repair_reason")
    assert column.legacy_type_sql == "VARCHAR(40)"
    assert column.nullable is True
    assert column.default_sql is None
    assert column.indexes == ()


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
        assert _column_type(connection, "paper_etf_eligibility", "status") == "paper_etf_eligibility_status"
        assert _index_exists(connection, "ix_paper_etf_eligibility_status")
        assert _enum_labels(connection, "paper_etf_eligibility_status") == (
            "unknown",
            "supported",
            "money_market",
            "disabled",
        )
        assert _enum_labels(connection, "paper_snapshot_point_type") == ("initial", "trading")
        assert _enum_labels(connection, "paper_snapshot_quality_status") == ("valid", "invalid")
        assert _column_type(connection, "paper_account_snapshots", "point_type") == "paper_snapshot_point_type"
        assert _column_type(connection, "paper_account_snapshots", "quality_status") == "paper_snapshot_quality_status"
        assert _index_exists(connection, "uq_paper_account_snapshots_account_initial")
        assert "completed_with_warnings" in _enum_labels(connection, "paper_matching_run_status")
        assert _enum_labels(connection, "paper_account_migration_repair_reason") == ("legacy_ordering_uncertain",)
        assert _column_type(connection, "paper_accounts", "migration_repair_reason") == (
            "paper_account_migration_repair_reason"
        )

        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=True)
        assert PAPER_TRADING_ENUM_ADAPTER.rollback(connection) is True
        PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=True)

        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _enum_types(connection) == set()
        assert _index_exists(connection, "uq_matching_active_scope")
        assert _column_type(connection, "paper_etf_eligibility", "status") == "character varying(20)"
        assert _index_exists(connection, "ix_paper_etf_eligibility_status")
        assert _column_type(connection, "paper_account_snapshots", "point_type") == "character varying(20)"
        assert _column_type(connection, "paper_account_snapshots", "quality_status") == "character varying(20)"
        assert _index_exists(connection, "uq_paper_account_snapshots_account_initial")
        assert _column_type(connection, "paper_accounts", "migration_repair_reason") == "character varying(40)"


def test_apply_adds_missing_nullable_migration_repair_reason_column(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("ALTER TABLE paper_accounts DROP COLUMN migration_repair_reason"))
        connection.execute(text("INSERT INTO paper_accounts (id, status, fee_preset) VALUES (1, 'active', 'a_share')"))

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "paper_accounts", "migration_repair_reason") == (
            "paper_account_migration_repair_reason"
        )
        assert _enum_labels(connection, "paper_account_migration_repair_reason") == ("legacy_ordering_uncertain",)
        assert (
            connection.execute(text("SELECT migration_repair_reason FROM paper_accounts WHERE id = 1")).scalar_one()
            is None
        )


def test_apply_adds_nullable_replay_time_provenance_without_backfilling_legacy_rows(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("INSERT INTO paper_accounts (id, status, fee_preset) VALUES (1, 'active', 'a_share')"))
        connection.execute(text("INSERT INTO paper_cash_ledger (id, event_type) VALUES (1, 'deposit')"))

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        for table_name in (
            "paper_cash_ledger",
            "paper_trades",
            "paper_corporate_actions",
            "paper_account_snapshots",
        ):
            assert _column_type(connection, table_name, "event_time_provenance") == "paper_replay_time_provenance"
        assert _enum_labels(connection, "paper_replay_time_provenance") == ("canonical_utc", "unknown")
        assert (
            connection.execute(text("SELECT event_time_provenance FROM paper_cash_ledger WHERE id = 1")).scalar_one()
            is None
        )
        assert migrate_paper_trading_enums(connection).converted is False


def test_apply_converts_legacy_migration_repair_reason_text_and_is_idempotent(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO paper_accounts (id, status, fee_preset, migration_repair_reason) "
                "VALUES (1, 'active', 'a_share', 'legacy_ordering_uncertain')"
            )
        )

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "paper_accounts", "migration_repair_reason") == (
            "paper_account_migration_repair_reason"
        )
        assert (
            connection.execute(
                text("SELECT migration_repair_reason::text FROM paper_accounts WHERE id = 1")
            ).scalar_one()
            == "legacy_ordering_uncertain"
        )
        assert migrate_paper_trading_enums(connection).converted is False
        assert _column_type(connection, "paper_accounts", "migration_repair_reason") == (
            "paper_account_migration_repair_reason"
        )


def test_unknown_legacy_migration_repair_reason_aborts_without_conversion(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO paper_accounts (id, status, fee_preset, migration_repair_reason) "
                "VALUES (1, 'active', 'a_share', 'unknown_repair')"
            )
        )
        with pytest.raises(PaperTradingEnumMigrationError, match="paper_account_migration_repair_reason"):
            migrate_paper_trading_enums(connection)
        assert _column_type(connection, "paper_accounts", "migration_repair_reason") == "character varying(40)"
        assert _enum_types(connection) == set()


def test_rollback_reverts_migration_repair_reason_to_varchar40_before_dropping_type(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO paper_accounts (id, status, fee_preset, migration_repair_reason) "
                "VALUES (1, 'active', 'a_share', 'legacy_ordering_uncertain')"
            )
        )
        assert migrate_paper_trading_enums(connection).converted is True
        assert migrate_paper_trading_enums(connection, rollback=True).rolled_back is True

        assert _column_type(connection, "paper_accounts", "migration_repair_reason") == "character varying(40)"
        assert "paper_account_migration_repair_reason" not in _enum_types(connection)
        assert (
            connection.execute(text("SELECT migration_repair_reason FROM paper_accounts WHERE id = 1")).scalar_one()
            == "legacy_ordering_uncertain"
        )


def test_rollback_removes_additive_etf_commission_rate_column(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        connection.execute(text("ALTER TABLE paper_accounts ADD COLUMN etf_commission_rate NUMERIC(20, 8)"))

        assert migrate_paper_trading_enums(connection, rollback=True).rolled_back is True
        assert _column_type(connection, "paper_accounts", "etf_commission_rate") is None


def test_rollback_preserves_incompatible_etf_commission_rate_column(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        connection.execute(
            text("ALTER TABLE paper_accounts ADD COLUMN etf_commission_rate NUMERIC(20, 8) NOT NULL DEFAULT 0")
        )

        with pytest.raises(PaperTradingEnumMigrationError, match="incompatible"):
            migrate_paper_trading_enums(connection, rollback=True)

        assert _column_type(connection, "paper_accounts", "etf_commission_rate") == "numeric(20,8)"


def test_rollback_rejects_persisted_etf_market_value(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        assert _enum_labels(connection, "paper_market") == ("a_share", "hk_connect", "etf")
        connection.execute(text("INSERT INTO paper_orders (id, side, status, market) VALUES (1, 'buy', 'new', 'etf')"))

        with pytest.raises(PaperTradingEnumMigrationError):
            migrate_paper_trading_enums(connection, rollback=True)

        assert _column_type(connection, "paper_orders", "market") == "paper_market"


def test_dry_run_reports_every_group_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        result = migrate_paper_trading_enums(connection, dry_run=True)
        assert result.dry_run is True
        assert result.converted is False
        assert {group.type_name for group in result.groups} == EXPECTED_TYPE_NAMES
        assert _enum_types(connection) == set()


def test_preflight_allows_missing_additive_order_event_table(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert not _table_exists(connection, "paper_order_events")


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
        connection.execute(text("CREATE TYPE paper_market AS ENUM ('a_share', 'hk_connect', 'etf')"))
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

        assert result.converted is True
        assert _table_exists(connection, "paper_account_snapshots")
        assert _table_exists(connection, "paper_valuation_gaps")
        assert _column_type(connection, "paper_account_snapshots", "point_type") == "paper_snapshot_point_type"
        assert _column_type(connection, "paper_account_snapshots", "quality_status") == "paper_snapshot_quality_status"


def test_ensure_snapshot_series_enum_types_is_idempotent_and_leaves_columns_to_startup(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("DROP TABLE paper_account_snapshots"))
        connection.execute(
            text("CREATE TABLE paper_account_snapshots (id integer primary key, account_id integer NOT NULL)")
        )

        ensure_snapshot_series_enum_types(connection)
        ensure_snapshot_series_enum_types(connection)

        assert _enum_labels(connection, "paper_snapshot_point_type") == ("initial", "trading")
        assert _enum_labels(connection, "paper_snapshot_quality_status") == ("valid", "invalid")
        assert _column_type(connection, "paper_account_snapshots", "point_type") is None
        assert _column_type(connection, "paper_account_snapshots", "quality_status") is None
        assert not _index_exists(connection, "uq_paper_account_snapshots_account_initial")

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "paper_account_snapshots", "point_type") == "paper_snapshot_point_type"
        assert _column_type(connection, "paper_account_snapshots", "quality_status") == "paper_snapshot_quality_status"


def test_apply_adds_missing_snapshot_enum_columns_on_existing_table(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("DROP TABLE paper_account_snapshots"))
        connection.execute(
            text("CREATE TABLE paper_account_snapshots (id integer primary key, account_id integer NOT NULL)")
        )
        connection.execute(text("INSERT INTO paper_account_snapshots (id, account_id) VALUES (1, 7)"))

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "paper_account_snapshots", "point_type") == "paper_snapshot_point_type"
        assert _column_type(connection, "paper_account_snapshots", "quality_status") == "paper_snapshot_quality_status"
        assert _index_exists(connection, "uq_paper_account_snapshots_account_initial")
        assert connection.execute(
            text("SELECT point_type, quality_status FROM paper_account_snapshots WHERE id = 1")
        ).one() == (
            "trading",
            "valid",
        )


def test_apply_creates_missing_etf_eligibility_table_after_enum_conversion(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        connection.execute(text("DROP TABLE paper_etf_eligibility"))

        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=False)
        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _table_exists(connection, "paper_etf_eligibility")
        assert _column_type(connection, "paper_etf_eligibility", "status") == "paper_etf_eligibility_status"


def test_apply_adds_and_rollback_removes_etf_eligibility_symbol_check(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        assert migrate_paper_trading_enums(connection).converted is True
        connection.execute(
            text(
                "ALTER TABLE paper_etf_eligibility "
                "DROP CONSTRAINT IF EXISTS ck_paper_etf_eligibility_symbol_six_ascii_digits"
            )
        )
        assert not _check_constraint_exists(
            connection, "paper_etf_eligibility", "ck_paper_etf_eligibility_symbol_six_ascii_digits"
        )

        assert migrate_paper_trading_enums(connection).converted is True

        assert _check_constraint_exists(
            connection, "paper_etf_eligibility", "ck_paper_etf_eligibility_symbol_six_ascii_digits"
        )

        assert migrate_paper_trading_enums(connection, rollback=True).rolled_back is True

        assert not _check_constraint_exists(
            connection, "paper_etf_eligibility", "ck_paper_etf_eligibility_symbol_six_ascii_digits"
        )


def test_preflight_rejects_invalid_existing_etf_eligibility_symbol(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO paper_etf_eligibility "
                "(symbol, name, exchange, list_status, last_seen_at, last_refresh_at) "
                "VALUES ('510300.SH', 'CSI 300 ETF', 'SH', 'L', now(), now())"
            )
        )

        with pytest.raises(PaperTradingEnumMigrationError, match="invalid ETF eligibility symbols"):
            migrate_paper_trading_enums(connection)

        assert _enum_types(connection) == set()


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
                if column.table_name == "daily_bar_diagnostics":
                    continue
                assert _table_exists(connection, column.table_name)
                assert _column_type(connection, column.table_name, column.column_name) == group.type_name
        assert not _table_exists(connection, "daily_bar_diagnostics")
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


def test_apply_adds_market_and_backfills_diagnostics_with_a_share(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO daily_bar_diagnostics VALUES (1, '2026-08-07', '000001', 'bfq', 'downloaded', '[]'::jsonb)"
            )
        )
        assert migrate_paper_trading_enums(connection).converted is True

        assert _column_type(connection, "daily_bar_diagnostics", "market") == "paper_market"
        assert (
            connection.execute(text("SELECT market FROM daily_bar_diagnostics WHERE id = 1")).scalar_one() == "a_share"
        )
        assert (
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'daily_bar_diagnostics'::regclass AND conname = 'uq_daily_bar_diagnostics_business_key'"
                )
            ).scalar_one()
            == "uq_daily_bar_diagnostics_business_key"
        )
        assert _constraint_columns(connection, "daily_bar_diagnostics", "uq_daily_bar_diagnostics_business_key") == (
            "business_date",
            "market",
            "stock_id",
            "adjust",
        )


def test_apply_upgrades_legacy_diagnostics_when_paper_tables_are_missing(empty_postgres_schema):
    engine, schema = empty_postgres_schema
    with _connection(engine, schema) as connection:
        _create_legacy_diagnostics_table(connection)

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "daily_bar_diagnostics", "market") == "paper_market"
        assert (
            connection.execute(text("SELECT market FROM daily_bar_diagnostics WHERE id = 1")).scalar_one() == "a_share"
        )
        assert _constraint_columns(connection, "daily_bar_diagnostics", "uq_daily_bar_diagnostics_business_key") == (
            "business_date",
            "market",
            "stock_id",
            "adjust",
        )
        assert _enum_types(connection) == EXPECTED_TYPE_NAMES
        for group in PAPER_TRADING_ENUM_GROUPS:
            for column in group.columns:
                if column.table_name != "daily_bar_diagnostics":
                    assert _table_exists(connection, column.table_name)
                    assert _column_type(connection, column.table_name, column.column_name) == group.type_name


def test_reduced_schemas_skip_market_qualified_keys_during_apply_verify_and_rollback(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        _drop_reduced_schema_key_columns(connection)
        connection.execute(text("INSERT INTO paper_positions (id, source, market) VALUES (1, 'trade', 'a_share')"))
        connection.execute(
            text(
                "INSERT INTO daily_bar_diagnostics "
                "(id, adjust, classification, provider_outcomes) VALUES "
                "(1, 'bfq', 'downloaded', '[]'::jsonb)"
            )
        )

        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=False)
        assert PAPER_TRADING_ENUM_ADAPTER.apply(connection) is True
        PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=False)
        assert _column_type(connection, "paper_positions", "market") == "paper_market"
        assert _column_type(connection, "daily_bar_diagnostics", "market") == "paper_market"
        assert connection.execute(text("SELECT market FROM paper_positions WHERE id = 1")).scalar_one() == "a_share"
        assert (
            connection.execute(text("SELECT market FROM daily_bar_diagnostics WHERE id = 1")).scalar_one() == "a_share"
        )
        assert _constraint_columns(connection, "paper_positions", "uq_paper_positions_account_market_symbol") == ()
        assert _constraint_columns(connection, "daily_bar_diagnostics", "uq_daily_bar_diagnostics_business_key") == ()

        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=True)
        assert PAPER_TRADING_ENUM_ADAPTER.rollback(connection) is True
        PAPER_TRADING_ENUM_ADAPTER.verify(connection, rollback=True)
        assert _column_type(connection, "paper_positions", "market") == "character varying(20)"
        assert _column_type(connection, "daily_bar_diagnostics", "market") is None
        assert connection.execute(text("SELECT market FROM paper_positions WHERE id = 1")).scalar_one() == "a_share"


def test_rollback_rejects_rows_colliding_on_legacy_marketless_keys(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_paper_trading_enums(connection)
        connection.execute(
            text("INSERT INTO paper_positions (id, account_id, symbol, market) VALUES (1, 7, '000001', 'a_share')")
        )
        connection.execute(
            text("INSERT INTO paper_positions (id, account_id, symbol, market) VALUES (2, 7, '000001', 'hk_connect')")
        )
        with pytest.raises(PaperTradingEnumMigrationError, match="legacy uniqueness"):
            migrate_paper_trading_enums(connection, rollback=True)


def test_rollback_rejects_diagnostic_rows_colliding_on_legacy_marketless_key(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_paper_trading_enums(connection)
        connection.execute(
            text(
                "INSERT INTO daily_bar_diagnostics "
                "(id, business_date, stock_id, market, adjust, classification, provider_outcomes) "
                "VALUES (1, '2026-08-07', '000001', 'a_share', 'bfq', 'downloaded', '[]'::jsonb), "
                "(2, '2026-08-07', '000001', 'hk_connect', 'bfq', 'downloaded', '[]'::jsonb)"
            )
        )
        with pytest.raises(PaperTradingEnumMigrationError, match="legacy uniqueness"):
            migrate_paper_trading_enums(connection, rollback=True)


def test_apply_upgrades_fully_preconverted_schema_with_missing_new_market_columns(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        migrate_paper_trading_enums(connection)
        connection.execute(text("DROP INDEX ix_paper_position_round_trips_market"))
        connection.execute(text("DROP INDEX ix_daily_bar_diagnostics_market"))
        connection.execute(text("ALTER TABLE paper_position_round_trips DROP COLUMN market"))
        connection.execute(
            text("ALTER TABLE daily_bar_diagnostics DROP CONSTRAINT uq_daily_bar_diagnostics_business_key")
        )
        connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP COLUMN market"))
        connection.execute(
            text(
                "ALTER TABLE daily_bar_diagnostics ADD CONSTRAINT uq_daily_bar_diagnostics_business_key "
                "UNIQUE (business_date, stock_id, adjust)"
            )
        )

        result = migrate_paper_trading_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "paper_position_round_trips", "market") == "paper_market"
        assert _column_type(connection, "daily_bar_diagnostics", "market") == "paper_market"
        assert _index_exists(connection, "ix_paper_position_round_trips_market")
        assert _index_exists(connection, "ix_daily_bar_diagnostics_market")
        assert _constraint_columns(connection, "daily_bar_diagnostics", "uq_daily_bar_diagnostics_business_key") == (
            "business_date",
            "market",
            "stock_id",
            "adjust",
        )
