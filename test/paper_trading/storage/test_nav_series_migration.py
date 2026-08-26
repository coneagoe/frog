from __future__ import annotations

import os
import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from paper_trading.storage.repository import PaperTradingRepository
from storage.storage_db import _PAPER_SNAPSHOT_SERIES_LOCK_KEY, StorageDb

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


def _schema_engine(url, schema: str, *, lock_timeout: str | None = None) -> Engine:
    options = f"-csearch_path={schema}"
    if lock_timeout is not None:
        options = f"{options} -clock_timeout={lock_timeout}"
    return create_engine(url, connect_args={"options": options})


@pytest.fixture()
def postgres_legacy_db():
    engine = _engine()
    schema = f"nav_series_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    bound = _schema_engine(engine.url, schema)
    with bound.begin() as connection:
        _create_legacy_schema(connection)
        _seed_legacy_rows(connection)
    try:
        yield bound, schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        bound.dispose()
        engine.dispose()


def _create_legacy_schema(
    connection: Connection,
    *,
    unique: str = "constraint",
    nav_type: str = "NUMERIC(20, 6)",
) -> None:
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
            f"""
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
                net_asset_value {nav_type},
                share_count numeric(20, 6),
                cumulative_deposit numeric(20, 4),
                cumulative_withdrawal numeric(20, 4),
                net_cash_flow numeric(20, 4),
                pending_settlement numeric(20, 4) NOT NULL DEFAULT 0,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    )
    if unique == "constraint":
        connection.execute(
            text(
                "ALTER TABLE paper_account_snapshots "
                "ADD CONSTRAINT uq_paper_account_snapshots_account_date UNIQUE (account_id, trade_date)"
            )
        )
    elif unique == "index":
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_paper_account_snapshots_account_date "
                "ON paper_account_snapshots (account_id, trade_date)"
            )
        )
        connection.execute(
            text("CREATE INDEX ix_paper_account_snapshots_trade_date ON paper_account_snapshots (trade_date)")
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
                 '2025-12-31 08:00:00+00'),
                (2, 'zero', 0.0000, 0, 1.000000, 0, 0, 0, '2025-12-31 08:00:00+00'),
                (3, 'negative', -100.0000, 0, 1.000000, 0, 0, 0, '2025-12-31 08:00:00+00')
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


def _repair_reasons(engine: Engine) -> dict[int, object]:
    with engine.connect() as connection:
        return {
            row["id"]: row["migration_repair_reason"]
            for row in connection.execute(text("SELECT id, migration_repair_reason FROM paper_accounts")).mappings()
        }


def _initial_ids(engine: Engine, account_id: int) -> list[int]:
    return [row["id"] for row in fetch_snapshots(engine, account_id) if row["point_type"] == "initial"]


def _create_cash_ledger_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE paper_cash_ledger (
                id integer PRIMARY KEY,
                account_id integer NOT NULL,
                event_type varchar(20) NOT NULL,
                amount numeric(20, 4) NOT NULL,
                occurred_at timestamptz NOT NULL,
                trade_date date
            )
            """
        )
    )


def _create_trades_table(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE paper_trades (
                id integer PRIMARY KEY,
                account_id integer NOT NULL,
                trade_date date NOT NULL,
                trade_time timestamptz NOT NULL
            )
            """
        )
    )


def _insert_positive_account_and_later_snapshot(
    connection: Connection,
    *,
    account_id: int = 1,
    name: str = "later",
    snapshot_id: int = 1,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
            VALUES (:account_id, :name, 10000.0000, 10000.000000, '2026-01-01 08:00:00+00')
            """
        ),
        {"account_id": account_id, "name": name},
    )
    connection.execute(
        text(
            """
            INSERT INTO paper_account_snapshots (
                id, account_id, trade_date, cash_available, cash_frozen, market_value,
                total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                trade_count, net_asset_value, created_at
            ) VALUES (
                :snapshot_id, :account_id, '2026-01-03', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                '2026-01-03 16:00:00+00'
            )
            """
        ),
        {"snapshot_id": snapshot_id, "account_id": account_id},
    )


def test_nav_series_migration_backfills_legacy_snapshot_metadata_and_baseline(postgres_legacy_db):
    engine, _schema = postgres_legacy_db
    original = {snapshot_id: _financials(_snapshot_by_id(engine, snapshot_id)) for snapshot_id in range(1, 8)}

    ensure_paper_trading_schema(engine)
    rows = fetch_snapshots(engine, account_id=1)

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
        assert _financials(_snapshot_by_id(engine, snapshot_id)) == financials

    zero_rows = fetch_snapshots(engine, account_id=2)
    negative_rows = fetch_snapshots(engine, account_id=3)
    assert [row["id"] for row in zero_rows] == [6]
    assert [row["id"] for row in negative_rows] == [7]
    assert zero_rows[0]["point_type"] == "trading"
    assert negative_rows[0]["point_type"] == "trading"
    assert _financials(zero_rows[0]) == original[6]
    assert _financials(negative_rows[0]) == original[7]

    initial = rows[0]
    assert initial["trade_date"].isoformat() == "2025-12-31"
    assert Decimal(str(initial["cash_available"])) == Decimal("10000.0000")
    assert Decimal(str(initial["total_assets"])) == Decimal("10000.0000")
    assert Decimal(str(initial["share_count"])) == Decimal("10000.000000")
    assert Decimal(str(initial["cumulative_deposit"])) == Decimal("10000.0000")
    assert Decimal(str(initial["net_cash_flow"])) == Decimal("10000.0000")
    assert initial["quality_status"] == "valid"

    assert _repair_reasons(engine) == {1: None, 2: None, 3: None}
    assert not _constraint_exists(engine, "uq_paper_account_snapshots_account_date")
    assert _index_exists(engine, "ix_paper_account_snapshots_account_event")
    assert _index_exists(engine, "uq_paper_account_snapshots_account_initial")

    with engine.begin() as connection:
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

    ensure_paper_trading_schema(engine)
    rerun_rows = fetch_snapshots(engine, account_id=1)
    assert [row["point_type"] for row in rerun_rows if row["point_type"] == "initial"] == ["initial"]
    assert _repair_reasons(engine) == {1: None, 2: None, 3: None}
    assert [row["id"] for row in fetch_snapshots(engine, account_id=2)] == [6]
    assert [row["id"] for row in fetch_snapshots(engine, account_id=3)] == [7]
    inspector = inspect(engine)
    snapshot_columns = {column["name"] for column in inspector.get_columns("paper_account_snapshots")}
    assert {"point_type", "event_at", "quality_status", "invalid_reason"} <= snapshot_columns


def test_nav_series_migration_marks_infinity_and_nan_nav_invalid():
    engine = _engine()
    schema = f"nav_series_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    bound = _schema_engine(engine.url, schema)
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection, nav_type="NUMERIC")
            connection.execute(
                text(
                    """
                    INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
                    VALUES (1, 'positive', 10000.0000, 10000.000000, '2025-12-31 08:00:00+00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_account_snapshots (
                        id, account_id, trade_date, cash_available, cash_frozen, market_value,
                        total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                        trade_count, net_asset_value, created_at
                    ) VALUES
                        (1, 1, '2026-01-01', 1, 0, 0, 1, 0, 0, 0, 0, 0, 'NaN'::numeric,
                         '2026-01-01 16:00:00+00'),
                        (2, 1, '2026-01-02', 1, 0, 0, 1, 0, 0, 0, 0, 0, 'Infinity'::numeric,
                         '2026-01-02 16:00:00+00'),
                        (3, 1, '2026-01-03', 1, 0, 0, 1, 0, 0, 0, 0, 0, '-Infinity'::numeric,
                         '2026-01-03 16:00:00+00')
                    """
                )
            )
        original = {snapshot_id: _financials(_snapshot_by_id(bound, snapshot_id)) for snapshot_id in (1, 2, 3)}

        ensure_paper_trading_schema(bound)
        rows = fetch_snapshots(bound, account_id=1)

        trading = [row for row in rows if row["point_type"] == "trading"]
        assert [row["id"] for row in trading] == [1, 2, 3]
        assert [row["quality_status"] for row in trading] == ["invalid", "invalid", "invalid"]
        assert [row["invalid_reason"] for row in trading] == [
            "non_finite_nav",
            "non_finite_nav",
            "non_finite_nav",
        ]
        for snapshot_id, financials in original.items():
            assert _financials(_snapshot_by_id(bound, snapshot_id)) == financials
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        bound.dispose()
        engine.dispose()


def test_nav_series_migration_drops_standalone_account_date_unique_index():
    engine = _engine()
    schema = f"nav_series_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    bound = _schema_engine(engine.url, schema)
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection, unique="index")
            connection.execute(
                text(
                    """
                    INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
                    VALUES (1, 'positive', 10000.0000, 10000.000000, '2026-01-01 08:00:00+00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_account_snapshots (
                        id, account_id, trade_date, cash_available, cash_frozen, market_value,
                        total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                        trade_count, net_asset_value, created_at
                    ) VALUES (1, 1, '2026-01-02', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                              '2026-01-02 16:00:00+00')
                    """
                )
            )

        ensure_paper_trading_schema(bound)

        assert not _constraint_exists(bound, "uq_paper_account_snapshots_account_date")
        assert not _index_exists(bound, "uq_paper_account_snapshots_account_date")
        assert _index_exists(bound, "ix_paper_account_snapshots_trade_date")
        assert _index_exists(bound, "ix_paper_account_snapshots_account_event")
        assert _index_exists(bound, "uq_paper_account_snapshots_account_initial")

        with bound.begin() as connection:
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
        rows = fetch_snapshots(bound, account_id=1)
        assert [row["point_type"] for row in rows if row["point_type"] == "initial"] == ["initial"]
        assert [row["id"] for row in rows if row["point_type"] == "trading"] == [100, 1]
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        bound.dispose()
        engine.dispose()


def test_nav_series_migration_waits_on_transaction_advisory_lock(postgres_legacy_db):
    engine, schema = postgres_legacy_db
    with engine.connect() as holder:
        trans = holder.begin()
        holder.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:lock_key AS text), 0))"),
            {"lock_key": _PAPER_SNAPSHOT_SERIES_LOCK_KEY},
        )
        waiter = _schema_engine(engine.url, schema, lock_timeout="200ms")
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                ensure_paper_trading_schema(waiter)
            with engine.connect() as connection:
                assert connection.execute(text("SELECT COUNT(*) FROM paper_account_snapshots")).scalar_one() == 7
        finally:
            waiter.dispose()
            trans.rollback()

    ensure_paper_trading_schema(engine)
    rows = fetch_snapshots(engine, account_id=1)
    assert [row["point_type"] for row in rows if row["point_type"] == "initial"] == ["initial"]


def test_nav_series_migration_serializes_concurrent_startup(postgres_legacy_db):
    engine, schema = postgres_legacy_db
    errors: list[BaseException] = []
    workers_engines = [_schema_engine(engine.url, schema) for _ in range(2)]

    def _run(worker_engine: Engine) -> None:
        try:
            db = _storage(worker_engine)
            with worker_engine.begin() as connection:
                db._ensure_paper_account_snapshot_series(connection)
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    workers = [threading.Thread(target=_run, args=(worker_engine,)) for worker_engine in workers_engines]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    for worker_engine in workers_engines:
        worker_engine.dispose()

    assert errors == []
    rows = fetch_snapshots(engine, account_id=1)
    assert [row["point_type"] for row in rows if row["point_type"] == "initial"] == ["initial"]
    assert _repair_reasons(engine) == {1: None, 2: None, 3: None}
    assert len({row["id"] for row in rows}) == len(rows)


def _isolated_postgres_schema():
    engine = _engine()
    schema = f"nav_series_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    bound = _schema_engine(engine.url, schema)
    return engine, bound, schema


def _drop_isolated_postgres_schema(engine: Engine, bound: Engine, schema: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    bound.dispose()
    engine.dispose()


def test_nav_series_migration_marks_null_created_at_for_repair_without_baseline():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            connection.execute(text("ALTER TABLE paper_accounts ALTER COLUMN created_at DROP NOT NULL"))
            connection.execute(
                text(
                    """
                    INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
                    VALUES (1, 'missing-created-at', 10000.0000, 10000.000000, NULL)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_account_snapshots (
                        id, account_id, trade_date, cash_available, cash_frozen, market_value,
                        total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                        trade_count, net_asset_value, created_at
                    ) VALUES (1, 1, '2026-01-02', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                              '2026-01-02 16:00:00+00')
                    """
                )
            )
        original = _financials(_snapshot_by_id(bound, 1))

        ensure_paper_trading_schema(bound)
        rows = fetch_snapshots(bound, account_id=1)

        assert _repair_reasons(bound) == {1: "legacy_ordering_uncertain"}
        assert [row["id"] for row in rows] == [1]
        assert [row["point_type"] for row in rows] == ["trading"]
        assert _financials(_snapshot_by_id(bound, 1)) == original

        ensure_paper_trading_schema(bound)
        assert _repair_reasons(bound) == {1: "legacy_ordering_uncertain"}
        assert _initial_ids(bound, 1) == []
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_nav_series_migration_marks_pre_creation_snapshot_event_time_and_date():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            connection.execute(
                text(
                    """
                    INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
                    VALUES
                        (1, 'early-event', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00'),
                        (2, 'early-date', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00'),
                        (3, 'safe', 10000.0000, 10000.000000, '2026-01-01 08:00:00+00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_account_snapshots (
                        id, account_id, trade_date, cash_available, cash_frozen, market_value,
                        total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                        trade_count, net_asset_value, created_at
                    ) VALUES
                        (1, 1, '2026-01-02', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-01 16:00:00+00'),
                        (2, 2, '2026-01-01', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-02 16:00:00+00'),
                        (3, 3, '2026-01-02', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-02 16:00:00+00')
                    """
                )
            )
        original = {snapshot_id: _financials(_snapshot_by_id(bound, snapshot_id)) for snapshot_id in (1, 2, 3)}

        ensure_paper_trading_schema(bound)

        assert _repair_reasons(bound) == {
            1: "legacy_ordering_uncertain",
            2: "legacy_ordering_uncertain",
            3: None,
        }
        assert _initial_ids(bound, 1) == []
        assert _initial_ids(bound, 2) == []
        assert len(_initial_ids(bound, 3)) == 1
        for snapshot_id, financials in original.items():
            assert _financials(_snapshot_by_id(bound, snapshot_id)) == financials
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_nav_series_migration_marks_pre_creation_cash_flow_and_trading_times():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            _create_cash_ledger_table(connection)
            _create_trades_table(connection)
            connection.execute(
                text(
                    """
                    ALTER TABLE paper_orders
                    ADD COLUMN created_at timestamptz,
                    ADD COLUMN trade_date date
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
                    VALUES
                        (1, 'early-cash-time', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00'),
                        (2, 'early-cash-date', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00'),
                        (3, 'early-trade-time', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00'),
                        (4, 'early-trade-date', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00'),
                        (5, 'early-order', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_account_snapshots (
                        id, account_id, trade_date, cash_available, cash_frozen, market_value,
                        total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                        trade_count, net_asset_value, created_at
                    ) VALUES
                        (1, 1, '2026-01-03', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-03 16:00:00+00'),
                        (2, 2, '2026-01-03', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-03 16:00:00+00'),
                        (3, 3, '2026-01-03', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-03 16:00:00+00'),
                        (4, 4, '2026-01-03', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-03 16:00:00+00'),
                        (5, 5, '2026-01-03', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                         '2026-01-03 16:00:00+00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_cash_ledger (id, account_id, event_type, amount, occurred_at, trade_date)
                    VALUES
                        (1, 1, 'deposit', 10000.0000, '2026-01-01 16:00:00+00', '2026-01-02'),
                        (2, 2, 'deposit', 10000.0000, '2026-01-02 16:00:00+00', '2026-01-01')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_trades (id, account_id, trade_date, trade_time)
                    VALUES
                        (1, 3, '2026-01-02', '2026-01-01 16:00:00+00'),
                        (2, 4, '2026-01-01', '2026-01-02 16:00:00+00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_orders (id, account_id, created_at, trade_date)
                    VALUES (1, 5, '2026-01-01 16:00:00+00', '2026-01-01')
                    """
                )
            )
        original = {snapshot_id: _financials(_snapshot_by_id(bound, snapshot_id)) for snapshot_id in range(1, 6)}

        ensure_paper_trading_schema(bound)

        assert _repair_reasons(bound) == {
            1: "legacy_ordering_uncertain",
            2: "legacy_ordering_uncertain",
            3: "legacy_ordering_uncertain",
            4: "legacy_ordering_uncertain",
            5: "legacy_ordering_uncertain",
        }
        for account_id in range(1, 6):
            assert _initial_ids(bound, account_id) == []
        for snapshot_id, financials in original.items():
            assert _financials(_snapshot_by_id(bound, snapshot_id)) == financials
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_nav_series_migration_preserves_existing_repair_state_and_skips_baseline():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            connection.execute(text("ALTER TABLE paper_accounts ADD COLUMN migration_repair_reason VARCHAR(40)"))
            connection.execute(
                text(
                    """
                    INSERT INTO paper_accounts (
                        id, name, initial_cash, share_count, created_at, migration_repair_reason
                    ) VALUES (
                        1, 'already-marked', 10000.0000, 10000.000000, '2026-01-01 08:00:00+00',
                        'legacy_ordering_uncertain'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_account_snapshots (
                        id, account_id, trade_date, cash_available, cash_frozen, market_value,
                        total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                        trade_count, net_asset_value, created_at
                    ) VALUES (1, 1, '2026-01-01', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                              '2026-01-01 16:00:00+00')
                    """
                )
            )
        original = _financials(_snapshot_by_id(bound, 1))

        ensure_paper_trading_schema(bound)
        ensure_paper_trading_schema(bound)

        assert _repair_reasons(bound) == {1: "legacy_ordering_uncertain"}
        assert _initial_ids(bound, 1) == []
        assert _financials(_snapshot_by_id(bound, 1)) == original
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_nav_series_migration_marks_equal_day_date_only_evidence():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            connection.execute(
                text(
                    """
                    INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
                    VALUES (1, 'same-day', 10000.0000, 10000.000000, '2026-01-02 08:00:00+00')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_account_snapshots (
                        id, account_id, trade_date, cash_available, cash_frozen, market_value,
                        total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                        trade_count, net_asset_value, created_at
                    ) VALUES (1, 1, '2026-01-02', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                              '2026-01-02 16:00:00+00')
                    """
                )
            )
        original = _financials(_snapshot_by_id(bound, 1))

        ensure_paper_trading_schema(bound)

        assert _repair_reasons(bound) == {1: "legacy_ordering_uncertain"}
        assert _initial_ids(bound, 1) == []
        assert _financials(_snapshot_by_id(bound, 1)) == original
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_nav_series_migration_marks_null_and_missing_source_temporal_evidence():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            _create_cash_ledger_table(connection)
            connection.execute(text("ALTER TABLE paper_cash_ledger ALTER COLUMN occurred_at DROP NOT NULL"))
            _insert_positive_account_and_later_snapshot(connection, account_id=1, name="null-time", snapshot_id=1)
            _insert_positive_account_and_later_snapshot(connection, account_id=2, name="null-date", snapshot_id=2)
            _insert_positive_account_and_later_snapshot(connection, account_id=3, name="missing-columns", snapshot_id=3)
            connection.execute(
                text(
                    """
                    INSERT INTO paper_cash_ledger (id, account_id, event_type, amount, occurred_at, trade_date)
                    VALUES
                        (1, 1, 'deposit', 10000.0000, NULL, '2026-01-03'),
                        (2, 2, 'deposit', 10000.0000, '2026-01-03 16:00:00+00', NULL)
                    """
                )
            )
            connection.execute(
                text("INSERT INTO paper_orders (id, account_id, idempotency_key) VALUES (1, 3, 'legacy')")
            )
        original = {snapshot_id: _financials(_snapshot_by_id(bound, snapshot_id)) for snapshot_id in (1, 2, 3)}

        ensure_paper_trading_schema(bound)

        assert _repair_reasons(bound) == {
            1: "legacy_ordering_uncertain",
            2: "legacy_ordering_uncertain",
            3: "legacy_ordering_uncertain",
        }
        for account_id in (1, 2, 3):
            assert _initial_ids(bound, account_id) == []
        for snapshot_id, financials in original.items():
            assert _financials(_snapshot_by_id(bound, snapshot_id)) == financials
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_nav_series_migration_marks_omitted_historical_trading_tables():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            connection.execute(
                text(
                    """
                    CREATE TABLE paper_position_lots (
                        id integer PRIMARY KEY,
                        account_id integer NOT NULL,
                        buy_trade_date date NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE paper_position_round_trips (
                        id integer PRIMARY KEY,
                        account_id integer NOT NULL,
                        open_trade_date date NOT NULL,
                        close_trade_date date
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE paper_matching_runs (
                        id integer PRIMARY KEY,
                        account_id integer,
                        trade_date date NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE paper_trade_validity_checks (
                        id integer PRIMARY KEY,
                        account_id integer NOT NULL,
                        trade_date date NOT NULL
                    )
                    """
                )
            )
            _insert_positive_account_and_later_snapshot(connection, account_id=1, name="lots", snapshot_id=1)
            _insert_positive_account_and_later_snapshot(connection, account_id=2, name="round-trips", snapshot_id=2)
            _insert_positive_account_and_later_snapshot(connection, account_id=3, name="matching", snapshot_id=3)
            _insert_positive_account_and_later_snapshot(connection, account_id=4, name="validity", snapshot_id=4)
            connection.execute(
                text("INSERT INTO paper_position_lots (id, account_id, buy_trade_date) VALUES (1, 1, '2026-01-01')")
            )
            connection.execute(
                text(
                    """
                    INSERT INTO paper_position_round_trips (
                        id, account_id, open_trade_date, close_trade_date
                    ) VALUES (1, 2, '2026-01-03', '2026-01-01')
                    """
                )
            )
            connection.execute(
                text("INSERT INTO paper_matching_runs (id, account_id, trade_date) VALUES (1, 3, '2026-01-01')")
            )
            connection.execute(
                text("INSERT INTO paper_trade_validity_checks (id, account_id, trade_date) VALUES (1, 4, '2026-01-01')")
            )
        original = {snapshot_id: _financials(_snapshot_by_id(bound, snapshot_id)) for snapshot_id in range(1, 5)}

        db = _storage(bound)
        with bound.begin() as connection:
            db._ensure_paper_account_snapshot_series(connection)

        assert _repair_reasons(bound) == {
            1: "legacy_ordering_uncertain",
            2: "legacy_ordering_uncertain",
            3: "legacy_ordering_uncertain",
            4: "legacy_ordering_uncertain",
        }
        for account_id in range(1, 5):
            assert _initial_ids(bound, account_id) == []
        for snapshot_id, financials in original.items():
            assert _financials(_snapshot_by_id(bound, snapshot_id)) == financials
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_nav_series_migration_marks_global_pre_creation_matching_run():
    engine, bound, schema = _isolated_postgres_schema()
    try:
        with bound.begin() as connection:
            _create_legacy_schema(connection)
            connection.execute(
                text(
                    """
                    CREATE TABLE paper_matching_runs (
                        id integer PRIMARY KEY,
                        account_id integer,
                        trade_date date NOT NULL
                    )
                    """
                )
            )
            _insert_positive_account_and_later_snapshot(connection, account_id=1, name="global-run", snapshot_id=1)
            connection.execute(
                text("INSERT INTO paper_matching_runs (id, account_id, trade_date) VALUES (1, NULL, '2026-01-01')")
            )
        original = _financials(_snapshot_by_id(bound, 1))

        db = _storage(bound)
        with bound.begin() as connection:
            db._ensure_paper_account_snapshot_series(connection)

        assert _repair_reasons(bound) == {1: "legacy_ordering_uncertain"}
        assert _initial_ids(bound, 1) == []
        assert _financials(_snapshot_by_id(bound, 1)) == original
    finally:
        _drop_isolated_postgres_schema(engine, bound, schema)


def test_sqlite_legacy_snapshots_are_listed_by_event_at(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy_snapshots.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE paper_orders (
                    id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE paper_accounts (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    initial_cash NUMERIC(20, 4) NOT NULL,
                    share_count NUMERIC(20, 6) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE paper_account_snapshots (
                    id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    trade_date DATE NOT NULL,
                    cash_available NUMERIC(20, 4) NOT NULL,
                    cash_frozen NUMERIC(20, 4) NOT NULL,
                    market_value NUMERIC(20, 4) NOT NULL,
                    total_assets NUMERIC(20, 4) NOT NULL,
                    realized_pnl NUMERIC(20, 4) NOT NULL,
                    unrealized_pnl NUMERIC(20, 4) NOT NULL,
                    position_count INTEGER NOT NULL,
                    order_count INTEGER NOT NULL,
                    trade_count INTEGER NOT NULL,
                    net_asset_value NUMERIC(20, 6),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_accounts (id, name, initial_cash, share_count, created_at)
                VALUES (1, 'positive', 10000.0000, 10000.000000, '2026-01-01 08:00:00')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_account_snapshots (
                    id, account_id, trade_date, cash_available, cash_frozen, market_value,
                    total_assets, realized_pnl, unrealized_pnl, position_count, order_count,
                    trade_count, net_asset_value, created_at
                ) VALUES
                    (1, 1, '2026-01-02', 9000, 0, 0, 9000, 0, 0, 0, 0, 0, 1.250000,
                     '2026-01-02 16:00:00'),
                    (2, 1, '2026-01-01', 8000, 0, 0, 8000, 0, 0, 0, 0, 0, NULL,
                     '2026-01-01 16:00:00'),
                    (3, 1, '2026-01-03', 7000, 0, 0, 7000, 0, 0, 0, 0, 0, 0,
                     '2026-01-03 16:00:00')
                """
            )
        )

    ensure_paper_trading_schema(engine)
    inspector = inspect(engine)
    snapshot_columns = {column["name"] for column in inspector.get_columns("paper_account_snapshots")}
    assert {"point_type", "event_at", "quality_status", "invalid_reason"} <= snapshot_columns
    account_columns = {column["name"]: column for column in inspector.get_columns("paper_accounts")}
    assert "migration_repair_reason" in account_columns
    assert account_columns["migration_repair_reason"]["nullable"] is True

    with Session(engine) as session:
        rows = PaperTradingRepository(session).list_snapshots(1)

    assert [row.id for row in rows] == [2, 1, 3]
    assert all(row.event_at is not None for row in rows)
    assert all(row.point_type == "trading" for row in rows)
    assert [row.quality_status for row in rows] == ["invalid", "valid", "invalid"]
    assert [row.invalid_reason for row in rows] == ["missing_nav", None, "non_positive_nav"]
    assert _initial_ids(engine, 1) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM paper_account_snapshots")).scalar_one() == 3
        assert (
            connection.execute(text("SELECT migration_repair_reason FROM paper_accounts WHERE id = 1")).scalar_one()
            is None
        )

    ensure_paper_trading_schema(engine)
    with Session(engine) as session:
        rerun_rows = PaperTradingRepository(session).list_snapshots(1)
    assert [row.id for row in rerun_rows] == [2, 1, 3]
    assert _initial_ids(engine, 1) == []
    engine.dispose()
