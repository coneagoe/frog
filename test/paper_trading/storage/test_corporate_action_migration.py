from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Enum as SqlAlchemyEnum
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from paper_trading.domain.enums import CashEventType, CorporateActionProcessingStatus, CorporateActionType
from paper_trading.storage.enum_migration import _GOVERNED_TABLES, migrate_paper_trading_enums
from storage.model import Base
from storage.storage_db import StorageDb


def _storage(engine: Engine) -> StorageDb:
    storage = StorageDb.__new__(StorageDb)
    storage.engine = engine
    return storage


def _create_paper_trading_tables(connection: Connection) -> None:
    tables = list(_GOVERNED_TABLES)
    enum_types = {
        column.type for table in tables for column in table.columns if isinstance(column.type, SqlAlchemyEnum)
    }
    for enum_type in enum_types:
        enum_type.create(connection, checkfirst=True)
    Base.metadata.create_all(connection, tables=tables)


def _postgres_enum_labels(connection: Connection, type_name: str) -> list[str]:
    return (
        connection.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :type_name AND t.typnamespace = current_schema()::regnamespace "
                "ORDER BY e.enumsortorder"
            ),
            {"type_name": type_name},
        )
        .scalars()
        .all()
    )


def test_sqlite_startup_adds_corporate_actions_and_preserves_legacy_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE paper_accounts ("
                "id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, initial_cash NUMERIC(20, 4) NOT NULL, "
                "share_count NUMERIC(20, 6) NOT NULL DEFAULT 0, net_asset_value NUMERIC(20, 6) NOT NULL DEFAULT 1, "
                "cumulative_deposit NUMERIC(20, 4) NOT NULL DEFAULT 0, "
                "cumulative_withdrawal NUMERIC(20, 4) NOT NULL DEFAULT 0, "
                "realized_pnl NUMERIC(20, 4) NOT NULL DEFAULT 0)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_cash_ledger ("
                "id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, event_type VARCHAR(20) NOT NULL, "
                "amount NUMERIC(20, 4) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_positions ("
                "id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, symbol VARCHAR(20) NOT NULL, "
                "total_quantity INTEGER NOT NULL DEFAULT 0, frozen_quantity INTEGER NOT NULL DEFAULT 0, "
                "cost_amount NUMERIC(20, 4) NOT NULL DEFAULT 0, realized_pnl NUMERIC(20, 4) NOT NULL DEFAULT 0)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_position_lots ("
                "id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, symbol VARCHAR(20) NOT NULL, "
                "buy_trade_date DATE NOT NULL, original_quantity INTEGER NOT NULL, "
                "remaining_quantity INTEGER NOT NULL, "
                "cost_price NUMERIC(20, 4) NOT NULL)"
            )
        )
        connection.execute(text("INSERT INTO paper_accounts VALUES (1, 'legacy', 10000, 10000, 1.25, 10000, 0, 12.5)"))
        connection.execute(text("INSERT INTO paper_cash_ledger VALUES (1, 1, 'deposit', 10000)"))
        connection.execute(text("INSERT INTO paper_positions VALUES (1, 1, '000001', 100, 0, 123.4567, 1.2345)"))
        connection.execute(
            text("INSERT INTO paper_position_lots VALUES (1, 1, '000001', '2026-08-27', 100, 100, 1.2345)")
        )

    storage = _storage(engine)
    storage.ensure_paper_trading_schema()
    first_columns = {column["name"] for column in inspect(engine).get_columns("paper_corporate_actions")}
    account = engine.connect().execute(text("SELECT * FROM paper_accounts WHERE id = 1")).mappings().one()
    ledger = engine.connect().execute(text("SELECT * FROM paper_cash_ledger WHERE id = 1")).mappings().one()
    storage.ensure_paper_trading_schema()
    second_columns = {column["name"] for column in inspect(engine).get_columns("paper_corporate_actions")}

    assert first_columns == second_columns
    assert {"parameters", "processing_status", "before_quantity", "after_quantity"} <= first_columns
    indexes = {index["name"] for index in inspect(engine).get_indexes("paper_corporate_actions")}
    assert {
        "uq_paper_corporate_actions_account_idempotency",
        "ix_paper_corporate_actions_account_event",
        "ix_paper_corporate_actions_event_type",
        "ix_paper_corporate_actions_processing_status",
        "ix_paper_corporate_actions_market",
    } <= indexes
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO paper_corporate_actions "
                "(account_id, symbol, event_type, event_at, idempotency_key, parameters, "
                "before_quantity, after_quantity, before_cost_amount, after_cost_amount, "
                "before_cash_available, after_cash_available) VALUES "
                "(1, '000001', 'split', '2026-08-27 09:00:00', 'unique', '{}', 1, 2, 1, 1, 1, 1)"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO paper_corporate_actions "
                    "(account_id, symbol, event_type, event_at, idempotency_key, parameters, "
                    "before_quantity, after_quantity, before_cost_amount, after_cost_amount, "
                    "before_cash_available, after_cash_available) VALUES "
                    "(1, '000001', 'split', '2026-08-27 09:00:00', 'unique', '{}', 1, 2, 1, 1, 1, 1)"
                )
            )
    assert account["share_count"] == 10000
    assert account["net_asset_value"] == 1.25
    assert ledger["amount"] == 10000
    assert ledger["rounding_residual"] == 0
    position_columns = {column["name"]: column["type"] for column in inspect(engine).get_columns("paper_positions")}
    lot_columns = {column["name"]: column["type"] for column in inspect(engine).get_columns("paper_position_lots")}
    assert (position_columns["cost_amount"].precision, position_columns["cost_amount"].scale) == (30, 12)
    assert (position_columns["realized_pnl"].precision, position_columns["realized_pnl"].scale) == (30, 12)
    assert (lot_columns["cost_price"].precision, lot_columns["cost_price"].scale) == (30, 12)
    assert engine.connect().execute(
        text("SELECT cost_amount, realized_pnl FROM paper_positions WHERE id = 1")
    ).one() == (
        123.4567,
        1.2345,
    )
    assert (
        engine.connect().execute(text("SELECT cost_price FROM paper_position_lots WHERE id = 1")).scalar_one() == 1.2345
    )
    engine.dispose()


def test_sqlite_precision_upgrade_is_monotonic_and_preserves_dependent_foreign_keys(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'precision_upgrade.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE paper_orders ("
                "id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL, "
                "limit_price NUMERIC(40, 4) NOT NULL, frozen_cash NUMERIC(40, 18) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_paper_orders_active_account ON paper_orders (account_id) "
                "WHERE status = 'active'"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_trades ("
                "id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, account_id INTEGER NOT NULL, "
                "price NUMERIC(40, 18) NOT NULL, amount NUMERIC(20, 4) NOT NULL, fees NUMERIC(20, 4) NOT NULL, "
                "FOREIGN KEY (order_id) REFERENCES paper_orders (id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_trade_validity_checks ("
                "id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, input_price NUMERIC(20, 4) NOT NULL, "
                "daily_low NUMERIC(20, 4), daily_high NUMERIC(20, 4), limit_up_price NUMERIC(20, 4), "
                "limit_down_price NUMERIC(20, 4), FOREIGN KEY (order_id) REFERENCES paper_orders (id))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_position_round_trips ("
                "id INTEGER PRIMARY KEY, open_trade_id INTEGER NOT NULL, close_trade_id INTEGER, "
                "entry_amount NUMERIC(20, 4) NOT NULL, exit_amount NUMERIC(20, 4) NOT NULL, "
                "fees NUMERIC(20, 4) NOT NULL, realized_pnl NUMERIC(20, 4) NOT NULL, return_pct NUMERIC(20, 18), "
                "FOREIGN KEY (open_trade_id) REFERENCES paper_trades (id), "
                "FOREIGN KEY (close_trade_id) REFERENCES paper_trades (id))"
            )
        )
        connection.execute(text("INSERT INTO paper_orders VALUES (1, 7, 'active', 123.4567, 0.123456789012345678)"))
        connection.execute(text("INSERT INTO paper_trades VALUES (1, 1, 7, 12.123456789012345678, 12.5, 0.5)"))
        connection.execute(text("INSERT INTO paper_trade_validity_checks VALUES (1, 1, 12.5, 12, 13, 14, 11)"))
        connection.execute(text("INSERT INTO paper_position_round_trips VALUES (1, 1, NULL, 12.5, 0, 0.5, 0, 1.5)"))

    storage = _storage(engine)
    storage._widen_sqlite_numeric_columns()
    with engine.connect() as connection:
        columns = {
            table_name: {column["name"]: column["type"] for column in inspect(connection).get_columns(table_name)}
            for table_name in (
                "paper_orders",
                "paper_trades",
                "paper_trade_validity_checks",
                "paper_position_round_trips",
            )
        }
        assert (columns["paper_orders"]["limit_price"].precision, columns["paper_orders"]["limit_price"].scale) == (
            40,
            12,
        )
        assert (columns["paper_orders"]["frozen_cash"].precision, columns["paper_orders"]["frozen_cash"].scale) == (
            40,
            18,
        )
        assert (columns["paper_trades"]["price"].precision, columns["paper_trades"]["price"].scale) == (40, 18)
        assert (
            columns["paper_position_round_trips"]["return_pct"].precision,
            columns["paper_position_round_trips"]["return_pct"].scale,
        ) == (30, 18)
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("SELECT limit_price, frozen_cash FROM paper_orders")).one() == (
            123.4567,
            0.12345678901234568,
        )
        assert connection.execute(text("SELECT COUNT(*) FROM paper_trades")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM paper_trade_validity_checks")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM paper_position_round_trips")).scalar_one() == 1
        index_sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_paper_orders_active_account'")
        ).scalar_one()
        assert "WHERE status = 'active'" in index_sql

    storage._widen_sqlite_numeric_columns()
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert connection.execute(text("SELECT COUNT(*) FROM paper_position_round_trips")).scalar_one() == 1
    engine.dispose()


def test_sqlite_precision_upgrade_rolls_back_when_foreign_key_check_fails(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'precision_upgrade_fk_failure.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE paper_orders ("
                "id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL, "
                "limit_price NUMERIC(20, 4) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_paper_orders_active_account ON paper_orders (account_id) "
                "WHERE status = 'active'"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE paper_trades ("
                "id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, account_id INTEGER NOT NULL, "
                "price NUMERIC(20, 4) NOT NULL, FOREIGN KEY (order_id) REFERENCES paper_orders (id))"
            )
        )
        connection.execute(text("INSERT INTO paper_orders VALUES (1, 7, 'active', 123.4567)"))

    raw_connection = engine.raw_connection()
    try:
        raw_connection.rollback()
        raw_connection.execute("PRAGMA foreign_keys = OFF")
        raw_connection.execute("INSERT INTO paper_trades VALUES (1, 999, 7, 12.5)")
        raw_connection.commit()
        raw_connection.execute("PRAGMA foreign_keys = ON")
    finally:
        raw_connection.close()

    with pytest.raises(IntegrityError, match="foreign_key_check"):
        _storage(engine)._widen_sqlite_numeric_columns()

    with engine.connect() as connection:
        order_type = inspect(connection).get_columns("paper_orders")[3]["type"]
        assert (order_type.precision, order_type.scale) == (20, 4)
        assert connection.execute(text("SELECT * FROM paper_orders")).one() == (1, 7, "active", 123.4567)
        assert connection.execute(text("SELECT * FROM paper_trades")).one() == (1, 999, 7, 12.5)
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == [("paper_trades", 1, "paper_orders", 0)]
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_paper_orders_active_account'")
        ).scalar_one()

    engine.dispose()


def _postgres_engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


def test_postgresql_additive_corporate_action_migration_is_repeatable():
    engine = _postgres_engine()
    schema = f"corporate_action_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(engine.url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with scoped.begin() as connection:
            _create_paper_trading_tables(connection)
            connection.execute(text("DROP TABLE paper_corporate_actions"))
            connection.execute(text("DROP TYPE paper_corporate_action_type"))
            connection.execute(text("DROP TYPE paper_corporate_action_processing_status"))
            connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN share_count TYPE NUMERIC(20, 6)"))
            connection.execute(text("ALTER TABLE paper_cash_ledger ALTER COLUMN amount TYPE NUMERIC(40, 4)"))
            connection.execute(text("INSERT INTO paper_accounts (name, initial_cash) VALUES ('legacy', 10000)"))

            migrate_paper_trading_enums(connection)
            first = connection.execute(
                text(
                    "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
                    "FROM information_schema.columns WHERE table_schema = current_schema() "
                    "AND table_name = 'paper_corporate_actions' ORDER BY column_name"
                )
            ).all()
            migrate_paper_trading_enums(connection)
            second = connection.execute(
                text(
                    "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
                    "FROM information_schema.columns WHERE table_schema = current_schema() "
                    "AND table_name = 'paper_corporate_actions' ORDER BY column_name"
                )
            ).all()
            enum_labels = {
                type_name: _postgres_enum_labels(connection, type_name)
                for type_name in (
                    "paper_corporate_action_type",
                    "paper_corporate_action_processing_status",
                    "paper_cash_event_type",
                )
            }
            defaults = dict(
                connection.execute(
                    text(
                        "SELECT a.attname, pg_get_expr(d.adbin, d.adrelid) "
                        "FROM pg_attrdef d JOIN pg_attribute a "
                        "ON a.attrelid = d.adrelid AND a.attnum = d.adnum "
                        "JOIN pg_class c ON c.oid = d.adrelid "
                        "WHERE c.relname = 'paper_corporate_actions' "
                        "AND c.relnamespace = current_schema()::regnamespace"
                    )
                ).all()
            )
            indexes = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE schemaname = current_schema() AND tablename = 'paper_corporate_actions'"
                    )
                )
            }
            assert {
                "uq_paper_corporate_actions_account_idempotency",
                "ix_paper_corporate_actions_account_event",
                "ix_paper_corporate_actions_event_type",
                "ix_paper_corporate_actions_processing_status",
                "ix_paper_corporate_actions_market",
            } <= indexes

        assert first == second
        assert enum_labels == {
            "paper_corporate_action_type": [member.value for member in CorporateActionType],
            "paper_corporate_action_processing_status": [member.value for member in CorporateActionProcessingStatus],
            "paper_cash_event_type": [member.value for member in CashEventType],
        }
        assert {
            name: defaults[name]
            for name in ("market", "processing_status", "cash_delta", "quantity_delta", "created_at")
        } == {
            "market": "'a_share'::paper_market",
            "processing_status": "'completed'::paper_corporate_action_processing_status",
            "cash_delta": "0",
            "quantity_delta": "0",
            "created_at": "now()",
        }
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        scoped.dispose()
        engine.dispose()


def test_postgresql_startup_widening_is_monotonic_and_preserves_legacy_state():
    engine = _postgres_engine()
    schema = f"corporate_action_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(engine.url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with scoped.begin() as connection:
            _create_paper_trading_tables(connection)
            connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN initial_cash TYPE NUMERIC(20, 4)"))
            connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN share_count TYPE NUMERIC(40, 20)"))
            connection.execute(text("ALTER TABLE paper_cash_ledger ALTER COLUMN amount TYPE NUMERIC(40, 4)"))
            connection.execute(
                text("ALTER TABLE paper_account_snapshots ALTER COLUMN net_asset_value TYPE NUMERIC(20, 6)")
            )
            connection.execute(
                text(
                    "INSERT INTO paper_accounts (name, initial_cash, share_count) "
                    "VALUES ('legacy', 123.4567, 9.87654321)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO paper_positions "
                    "(account_id, symbol, total_quantity, frozen_quantity, cost_amount, realized_pnl) "
                    "VALUES (1, '000001', 100, 20, 123.4567, 1.2345)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO paper_position_lots "
                    "(account_id, symbol, buy_trade_date, original_quantity, remaining_quantity, cost_price) "
                    "VALUES (1, '000001', '2026-08-27', 100, 80, 1.2345)"
                )
            )
            connection.execute(
                text("INSERT INTO paper_cash_ledger (account_id, event_type, amount) VALUES (1, 'deposit', 123.4567)")
            )
            connection.execute(
                text(
                    "INSERT INTO paper_account_snapshots "
                    "(account_id, trade_date, event_at, cash_available, cash_frozen, market_value, total_assets, "
                    "realized_pnl, unrealized_pnl, position_count, order_count, trade_count, net_asset_value, "
                    "share_count, cumulative_deposit, cumulative_withdrawal, net_cash_flow) "
                    "VALUES (1, '2026-08-27', '2026-08-27 09:00:00+00', 123, 0, 0, 123, 0, 0, 0, 0, 0, "
                    "1.234567, 9, 123, 0, 123)"
                )
            )

        _storage(scoped).ensure_paper_trading_schema()
        with scoped.connect() as connection:
            types = connection.execute(
                text(
                    "SELECT table_name, column_name, numeric_precision, numeric_scale "
                    "FROM information_schema.columns WHERE table_schema = current_schema() "
                    "AND ((table_name = 'paper_accounts' AND column_name IN ('initial_cash', 'share_count')) "
                    "OR (table_name = 'paper_cash_ledger' AND column_name IN ('amount', 'rounding_residual')) "
                    "OR (table_name = 'paper_account_snapshots' AND column_name = 'net_asset_value') "
                    "OR (table_name = 'paper_positions' AND column_name IN ('total_quantity', 'frozen_quantity')) "
                    "OR (table_name = 'paper_position_lots' AND column_name IN "
                    "('original_quantity', 'remaining_quantity')))"
                )
            ).all()
            observed = {(row[0], row[1]): (row[2], row[3]) for row in types}
            assert observed[("paper_accounts", "initial_cash")] == (30, 12)
            assert observed[("paper_accounts", "share_count")] == (40, 20)
            assert observed[("paper_cash_ledger", "amount")] == (40, 12)
            assert observed[("paper_cash_ledger", "rounding_residual")] == (30, 24)
            assert observed[("paper_account_snapshots", "net_asset_value")] == (30, 12)
            assert observed[("paper_positions", "total_quantity")] == (32, 0)
            assert observed[("paper_positions", "frozen_quantity")] == (32, 0)
            assert observed[("paper_position_lots", "original_quantity")] == (32, 0)
            assert observed[("paper_position_lots", "remaining_quantity")] == (32, 0)
            assert connection.execute(
                text("SELECT initial_cash, share_count FROM paper_accounts WHERE id = 1")
            ).one() == (
                Decimal("123.4567"),
                Decimal("9.87654321"),
            )
            assert connection.execute(
                text("SELECT amount FROM paper_cash_ledger WHERE id = 1")
            ).scalar_one() == Decimal("123.4567")
            assert connection.execute(
                text("SELECT total_quantity, frozen_quantity FROM paper_positions WHERE id = 1")
            ).one() == (100, 20)
            assert connection.execute(
                text("SELECT original_quantity, remaining_quantity FROM paper_position_lots WHERE id = 1")
            ).one() == (100, 80)
            assert connection.execute(
                text("SELECT net_asset_value, share_count FROM paper_account_snapshots WHERE account_id = 1")
            ).one() == (Decimal("1.234567"), Decimal("9.000000000000"))

        _storage(scoped).ensure_paper_trading_schema()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        scoped.dispose()
        engine.dispose()
