from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from paper_trading.storage.enum_migration import migrate_paper_trading_enums
from storage.model import Base
from storage.storage_db import StorageDb


def _storage(engine: Engine) -> StorageDb:
    storage = StorageDb.__new__(StorageDb)
    storage.engine = engine
    return storage


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
        connection.execute(text("INSERT INTO paper_accounts VALUES (1, 'legacy', 10000, 10000, 1.25, 10000, 0, 12.5)"))
        connection.execute(text("INSERT INTO paper_cash_ledger VALUES (1, 1, 'deposit', 10000)"))

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
            Base.metadata.create_all(connection)
            connection.execute(text("DROP TABLE paper_corporate_actions"))
            connection.execute(text("DROP TYPE paper_corporate_action_type"))
            connection.execute(text("DROP TYPE paper_corporate_action_processing_status"))
            connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN share_count TYPE NUMERIC(20, 6)"))
            connection.execute(text("ALTER TABLE paper_cash_ledger ALTER COLUMN amount TYPE NUMERIC(20, 4)"))
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
            labels = (
                connection.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'paper_corporate_action_processing_status' ORDER BY e.enumsortorder"
                    )
                )
                .scalars()
                .all()
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
        assert labels == ["pending", "completed", "failed"]
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
            Base.metadata.create_all(connection)
            connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN initial_cash TYPE NUMERIC(20, 4)"))
            connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN share_count TYPE NUMERIC(40, 20)"))
            connection.execute(text("ALTER TABLE paper_cash_ledger ALTER COLUMN amount TYPE NUMERIC(20, 4)"))
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
                text("INSERT INTO paper_cash_ledger (account_id, event_type, amount) VALUES (1, 'deposit', 123.4567)")
            )
            connection.execute(
                text(
                    "INSERT INTO paper_account_snapshots "
                    "(account_id, trade_date, event_at, total_assets, net_asset_value, share_count, "
                    "cumulative_deposit, cumulative_withdrawal, net_cash_flow) "
                    "VALUES (1, '2026-08-27', '2026-08-27 09:00:00+00', 123, 1.234567, 9, 123, 0, 123)"
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
                    "OR (table_name = 'paper_account_snapshots' AND column_name = 'net_asset_value'))"
                )
            ).all()
            observed = {(row[0], row[1]): (row[2], row[3]) for row in types}
            assert observed[("paper_accounts", "initial_cash")] == (30, 12)
            assert observed[("paper_accounts", "share_count")] == (40, 20)
            assert observed[("paper_cash_ledger", "amount")] == (30, 12)
            assert observed[("paper_cash_ledger", "rounding_residual")] == (30, 24)
            assert observed[("paper_account_snapshots", "net_asset_value")] == (30, 12)
            assert connection.execute(
                text("SELECT initial_cash, share_count FROM paper_accounts WHERE id = 1")
            ).one() == (
                123.4567,
                9.87654321,
            )
            assert (
                connection.execute(text("SELECT amount FROM paper_cash_ledger WHERE id = 1")).scalar_one() == 123.4567
            )

        _storage(scoped).ensure_paper_trading_schema()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        scoped.dispose()
        engine.dispose()
