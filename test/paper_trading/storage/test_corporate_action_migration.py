from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

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
            labels = connection.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'paper_corporate_action_processing_status' ORDER BY e.enumsortorder"
                )
            ).scalars().all()

        assert first == second
        assert labels == ["pending", "completed", "failed"]
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        scoped.dispose()
        engine.dispose()
