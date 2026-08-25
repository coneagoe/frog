from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection, Engine

from storage.storage_db import StorageDb

_FINANCIAL_COLUMNS = (
    "cash_available",
    "cash_frozen",
    "market_value",
    "total_assets",
    "realized_pnl",
    "unrealized_pnl",
    "position_count",
    "order_count",
    "trade_count",
    "net_asset_value",
    "share_count",
    "cumulative_deposit",
    "cumulative_withdrawal",
    "net_cash_flow",
    "pending_settlement",
)


def _engine() -> Engine:
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    assert url is not None
    return create_engine(url)


@pytest.fixture()
def postgres_legacy_db():
    engine = _engine()
    schema = f"nav_series_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    bound = create_engine(engine.url)
    event.listen(
        bound,
        "connect",
        lambda dbapi_connection, _: dbapi_connection.cursor().execute(f'SET search_path TO "{schema}"'),
    )
    with bound.begin() as connection:
        _create_legacy_schema(connection)
        _seed_legacy_rows(connection)
    try:
        yield bound
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        bound.dispose()
        engine.dispose()


def _create_legacy_schema(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE paper_accounts (
                id integer PRIMARY KEY,
                name varchar(100) NOT NULL UNIQUE,
                initial_cash numeric(20, 4) NOT NULL,
                share_count numeric(20, 6) NOT NULL DEFAULT 0,
                net_asset_value numeric(20, 6) NOT NULL DEFAULT 1,
                cumulative_deposit numeric(20, 4) NOT NULL DEFAULT 0,
                cumulative_withdrawal numeric(20, 4) NOT NULL DEFAULT 0,
                realized_pnl numeric(20, 4) NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE paper_orders (
                id integer PRIMARY KEY,
                account_id integer NOT NULL,
                idempotency_key varchar(100)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE paper_account_snapshots (
                id integer PRIMARY KEY,
                account_id integer NOT NULL REFERENCES paper_accounts (id),
                trade_date date NOT NULL,
                cash_available numeric(20, 4) NOT NULL,
                cash_frozen numeric(20, 4) NOT NULL,
                market_value numeric(20, 4) NOT NULL,
                total_assets numeric(20, 4) NOT NULL,
                realized_pnl numeric(20, 4) NOT NULL,
                unrealized_pnl numeric(20, 4) NOT NULL,
                position_count integer NOT NULL,
                order_count integer NOT NULL,
                trade_count integer NOT NULL,
                net_asset_value numeric(20, 6),
                share_count numeric(20, 6),
                cumulative_deposit numeric(20, 4),
                cumulative_withdrawal numeric(20, 4),
                net_cash_flow numeric(20, 4),
                pending_settlement numeric(20, 4) NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT uq_paper_account_snapshots_account_date UNIQUE (account_id, trade_date)
            )
            """
        )
    )


def _seed_legacy_rows(connection: Connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO paper_accounts (
                id, name, initial_cash, share_count, net_asset_value,
                cumulative_deposit, cumulative_withdrawal, realized_pnl, created_at
            ) VALUES
                (1, 'positive', 10000.0000, 10000.000000, 1.250000, 10000.0000, 0, 0,
                 '2026-01-01 08:00:00+00'),
                (2, 'zero', 0.0000, 0, 1.000000, 0, 0, 0, '2026-01-01 08:00:00+00'),
                (3, 'negative', -100.0000, 0, 1.000000, 0, 0, 0, '2026-01-01 08:00:00+00')
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO paper_account_snapshots (
                id, account_id, trade_date, cash_available, cash_frozen, market_value,
                total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                trade_count, net_asset_value, share_count, cumulative_deposit,
                cumulative_withdrawal, net_cash_flow, pending_settlement, created_at
            ) VALUES
                (1, 1, '2026-01-01', 9000.0000, 100.0000, 2500.0000, 11600.0000,
                 12.0000, 34.0000, 1, 2, 3, 1.250000, 10000.000000, 10000.0000,
                 0.0000, 10000.0000, 50.0000, '2026-01-01 16:00:00+00'),
                (2, 1, '2026-01-02', 9000.0000, 0.0000, 0.0000, 9000.0000,
                 0.0000, 0.0000, 0, 0, 0, NULL, 10000.000000, 10000.0000,
                 0.0000, 10000.0000, 0.0000, '2026-01-02 16:00:00+00'),
                (3, 1, '2026-01-03', 8000.0000, 0.0000, 0.0000, 8000.0000,
                 0.0000, 0.0000, 0, 0, 0, 0.000000, 10000.000000, 10000.0000,
                 0.0000, 10000.0000, 0.0000, '2026-01-03 16:00:00+00'),
                (4, 1, '2026-01-04', 7000.0000, 0.0000, 0.0000, 7000.0000,
                 0.0000, 0.0000, 0, 0, 0, -0.500000, 10000.000000, 10000.0000,
                 0.0000, 10000.0000, 0.0000, '2026-01-04 16:00:00+00'),
                (5, 1, '2026-01-05', 6000.0000, 0.0000, 0.0000, 6000.0000,
                 0.0000, 0.0000, 0, 0, 0, 'NaN'::numeric, 10000.000000, 10000.0000,
                 0.0000, 10000.0000, 0.0000, '2026-01-05 16:00:00+00'),
                (6, 2, '2026-01-01', 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0, 0, 0, 1.000000, 0.000000, 0.0000,
                 0.0000, 0.0000, 0.0000, '2026-01-01 16:00:00+00'),
                (7, 3, '2026-01-01', -100.0000, 0.0000, 0.0000, -100.0000,
                 0.0000, 0.0000, 0, 0, 0, 1.000000, 0.000000, 0.0000,
                 0.0000, 0.0000, 0.0000, '2026-01-01 16:00:00+00')
            """
        )
    )


def _storage(engine: Engine) -> StorageDb:
    db = StorageDb.__new__(StorageDb)
    db.engine = engine
    return db


def ensure_paper_trading_schema(engine: Engine) -> None:
    _storage(engine).ensure_paper_trading_schema()


def fetch_snapshots(engine: Engine, account_id: int):
    with engine.connect() as connection:
        return (
            connection.execute(
                text(
                    """
                    SELECT *
                    FROM paper_account_snapshots
                    WHERE account_id = :account_id
                    ORDER BY event_at ASC, id ASC
                    """
                ),
                {"account_id": account_id},
            )
            .mappings()
            .all()
        )


def _snapshot_by_id(engine: Engine, snapshot_id: int):
    with engine.connect() as connection:
        return (
            connection.execute(
                text("SELECT * FROM paper_account_snapshots WHERE id = :snapshot_id"),
                {"snapshot_id": snapshot_id},
            )
            .mappings()
            .one()
        )


def _financials(row) -> dict[str, object]:
    values: dict[str, object] = {}
    for column in _FINANCIAL_COLUMNS:
        value = row[column]
        values[column] = None if value is None else str(value)
    return values


def _constraint_exists(engine: Engine, constraint_name: str) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.execute(
                text(
                    "SELECT 1 FROM pg_constraint "
                    "WHERE conrelid = 'paper_account_snapshots'::regclass AND conname = :name"
                ),
                {"name": constraint_name},
            ).scalar_one_or_none()
        )


def _index_exists(engine: Engine, index_name: str) -> bool:
    with engine.connect() as connection:
        return bool(connection.execute(text("SELECT to_regclass(:name)"), {"name": index_name}).scalar_one())


def test_nav_series_migration_backfills_legacy_snapshot_metadata_and_baseline(postgres_legacy_db):
    original = {
        snapshot_id: _financials(_snapshot_by_id(postgres_legacy_db, snapshot_id)) for snapshot_id in range(1, 8)
    }

    ensure_paper_trading_schema(postgres_legacy_db)
    rows = fetch_snapshots(postgres_legacy_db, account_id=1)

    assert rows[0]["point_type"] == "initial"
    assert Decimal(str(rows[0]["net_asset_value"])) == Decimal("1.000000")
    assert all(row["event_at"] is not None for row in rows)

    assert [row["id"] for row in rows[1:]] == [1, 2, 3, 4, 5]
    assert all(row["point_type"] == "trading" for row in rows[1:])
    assert {row["quality_status"] for row in rows[1:]} == {"valid", "invalid"}
    assert rows[1]["quality_status"] == "valid"
    assert rows[1]["invalid_reason"] is None
    assert [row["quality_status"] for row in rows[2:]] == ["invalid"] * 4
    assert [row["invalid_reason"] for row in rows[2:]] == [
        "missing_nav",
        "non_positive_nav",
        "non_positive_nav",
        "non_finite_nav",
    ]
    assert [row["event_at"] for row in rows[1:]] == [row["created_at"] for row in rows[1:]]

    for snapshot_id, financials in original.items():
        assert _financials(_snapshot_by_id(postgres_legacy_db, snapshot_id)) == financials

    zero_rows = fetch_snapshots(postgres_legacy_db, account_id=2)
    negative_rows = fetch_snapshots(postgres_legacy_db, account_id=3)
    assert [row["id"] for row in zero_rows] == [6]
    assert [row["id"] for row in negative_rows] == [7]
    assert zero_rows[0]["point_type"] == "trading"
    assert negative_rows[0]["point_type"] == "trading"
    assert _financials(zero_rows[0]) == original[6]
    assert _financials(negative_rows[0]) == original[7]

    initial = rows[0]
    assert initial["trade_date"].isoformat() == "2026-01-01"
    assert Decimal(str(initial["cash_available"])) == Decimal("10000.0000")
    assert Decimal(str(initial["total_assets"])) == Decimal("10000.0000")
    assert Decimal(str(initial["share_count"])) == Decimal("10000.000000")
    assert Decimal(str(initial["cumulative_deposit"])) == Decimal("10000.0000")
    assert Decimal(str(initial["net_cash_flow"])) == Decimal("10000.0000")
    assert initial["quality_status"] == "valid"

    assert not _constraint_exists(postgres_legacy_db, "uq_paper_account_snapshots_account_date")
    assert _index_exists(postgres_legacy_db, "ix_paper_account_snapshots_account_event")
    assert _index_exists(postgres_legacy_db, "uq_paper_account_snapshots_account_initial")

    with postgres_legacy_db.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO paper_account_snapshots (
                    id, account_id, trade_date, point_type, event_at, quality_status,
                    cash_available, cash_frozen, market_value, total_assets, realized_pnl,
                    unrealized_pnl, position_count, order_count, trade_count, net_asset_value
                ) VALUES (
                    100, 1, '2026-01-01', 'trading', '2026-01-01 18:00:00+00', 'valid',
                    9000.0000, 0, 0, 9000.0000, 0, 0, 0, 0, 0, 1.100000
                )
                """
            )
        )

    ensure_paper_trading_schema(postgres_legacy_db)
    rerun_rows = fetch_snapshots(postgres_legacy_db, account_id=1)
    assert [row["point_type"] for row in rerun_rows if row["point_type"] == "initial"] == ["initial"]
    assert [row["id"] for row in fetch_snapshots(postgres_legacy_db, account_id=2)] == [6]
    assert [row["id"] for row in fetch_snapshots(postgres_legacy_db, account_id=3)] == [7]
    inspector = inspect(postgres_legacy_db)
    snapshot_columns = {column["name"] for column in inspector.get_columns("paper_account_snapshots")}
    assert {"point_type", "event_at", "quality_status", "invalid_reason"} <= snapshot_columns
