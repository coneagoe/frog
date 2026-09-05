import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import Enum, create_engine, inspect, select, text
from sqlalchemy.orm import Session

from paper_trading.storage.models import PaperAccount, PaperAccountSnapshot, PaperCashLedger
from paper_trading.storage.repository import PaperTradingRepository
from storage.model import AuthToken, Base, User
from storage.storage_db import StorageDb


def test_auth_schema_is_fresh_and_idempotent_on_postgresql():
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    postgresql_url = cast(str, url)

    engine = create_engine(postgresql_url)
    tables = [User.__table__, AuthToken.__table__]
    try:
        Base.metadata.drop_all(engine, tables=tables)
        Base.metadata.create_all(engine, tables=tables)
        Base.metadata.create_all(engine, tables=tables)

        database_inspector = inspect(engine)
        assert database_inspector.has_table("users")
        assert database_inspector.has_table("auth_tokens")
        assert {index["name"] for index in database_inspector.get_indexes("users")} >= {"ix_users_email"}
        assert {index["name"] for index in database_inspector.get_indexes("auth_tokens")} >= {
            "ix_auth_tokens_user_id",
            "ix_auth_tokens_purpose_expires_at",
        }
        foreign_keys = database_inspector.get_foreign_keys("auth_tokens")
        assert any(
            foreign_key["referred_table"] == "users" and foreign_key["constrained_columns"] == ["user_id"]
            for foreign_key in foreign_keys
        )

        with Session(engine) as session:
            user = User(email=" Operator@Example.com ", password_hash="argon2-hash")
            session.add(user)
            session.flush()
            session.add(
                AuthToken(
                    user_id=user.id,
                    purpose="session",
                    token_hash="hashed-token",
                    expires_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
            assert session.scalar(select(User).where(User.email == "operator@example.com")) is not None
    finally:
        Base.metadata.drop_all(engine, tables=[AuthToken.__table__, User.__table__])
        engine.dispose()


def test_storage_startup_backfills_legacy_account_owner_once_on_postgresql(monkeypatch):
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    engine = create_engine(cast(str, url))
    monkeypatch.setenv("AUTH_OWNER_EMAIL", "owner@example.com")
    storage = object.__new__(StorageDb)
    storage.engine = engine
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS paper_accounts CASCADE"))
            connection.execute(text("DROP TABLE IF EXISTS users CASCADE"))
            connection.execute(
                text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL, email_verified_at TIMESTAMPTZ)")
            )
            connection.execute(text("CREATE TABLE paper_accounts (id INTEGER PRIMARY KEY, owner_user_id INTEGER)"))
            connection.execute(
                text(
                    "INSERT INTO users (id, email, email_verified_at) "
                    "VALUES (1, 'owner@example.com', NOW())"
                )
            )
            connection.execute(text("INSERT INTO paper_accounts (id, owner_user_id) VALUES (1, NULL), (2, NULL)"))

        # This is the same backfill invoked by StorageDb schema startup. The
        # second invocation models a repeated, idempotent application startup.
        storage._backfill_paper_account_ownership()
        storage._backfill_paper_account_ownership()

        with engine.connect() as connection:
            assert connection.execute(text("SELECT owner_user_id FROM paper_accounts ORDER BY id")).scalars().all() == [1, 1]
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS paper_accounts CASCADE"))
            connection.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        engine.dispose()


@pytest.mark.parametrize(
    ("owner_email", "users"),
    [
        (None, [(1, "owner@example.com", True)]),
        ("owner@example.com", [(1, "owner@example.com", False)]),
        ("owner@example.com", [(1, "owner@example.com", True), (2, "owner@example.com", True)]),
    ],
    ids=["missing", "unverified", "ambiguous"],
)
def test_storage_startup_backfill_fails_without_exactly_one_verified_owner_on_postgresql(
    monkeypatch, owner_email, users
):
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    engine = create_engine(cast(str, url))
    storage = object.__new__(StorageDb)
    storage.engine = engine
    if owner_email is None:
        monkeypatch.delenv("AUTH_OWNER_EMAIL", raising=False)
    else:
        monkeypatch.setenv("AUTH_OWNER_EMAIL", owner_email)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS paper_accounts CASCADE"))
            connection.execute(text("DROP TABLE IF EXISTS users CASCADE"))
            connection.execute(
                text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL, email_verified_at TIMESTAMPTZ)")
            )
            connection.execute(text("CREATE TABLE paper_accounts (id INTEGER PRIMARY KEY, owner_user_id INTEGER)"))
            for user_id, email, verified in users:
                connection.execute(
                    text("INSERT INTO users (id, email, email_verified_at) VALUES (:id, :email, :verified_at)"),
                    {"id": user_id, "email": email, "verified_at": "2026-01-01T00:00:00+00:00" if verified else None},
                )
            connection.execute(text("INSERT INTO paper_accounts (id, owner_user_id) VALUES (1, NULL)"))

        with pytest.raises(RuntimeError, match="exactly one verified user"):
            storage._backfill_paper_account_ownership()
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS paper_accounts CASCADE"))
            connection.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        engine.dispose()


def test_canonical_trading_snapshot_is_utc_aware_and_idempotent_on_postgresql():
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    postgresql_url = cast(str, url)

    engine = create_engine(postgresql_url)
    tables = [User.__table__, PaperAccount.__table__, PaperCashLedger.__table__, PaperAccountSnapshot.__table__]
    trade_date = date(2026, 8, 25)
    try:
        Base.metadata.drop_all(engine, tables=list(reversed(tables)))
        for table in tables:
            for column in table.columns:
                if isinstance(column.type, Enum):
                    column.type.create(engine, checkfirst=True)
        Base.metadata.create_all(engine, tables=tables)
        Base.metadata.create_all(engine, tables=tables)

        database_inspector = inspect(engine)
        assert database_inspector.has_table("paper_accounts")
        assert database_inspector.has_table("paper_account_snapshots")
        assert {index["name"] for index in database_inspector.get_indexes("paper_account_snapshots")} >= {
            "uq_paper_account_snapshots_account_trading",
        }

        with Session(engine) as session:
            repo = PaperTradingRepository(session)
            account = repo.create_account("postgres-canonical-snapshot", Decimal("100000.00"))
            first = repo.save_trading_snapshot(
                **_trading_snapshot_values(account.id, trade_date, datetime(2026, 8, 25, 9, tzinfo=timezone.utc))
            )
            second = repo.save_trading_snapshot(
                **_trading_snapshot_values(account.id, trade_date, datetime(2026, 8, 25, 15, tzinfo=timezone.utc))
            )
            session.commit()

            assert second.id == first.id
            account_id = account.id

        with Session(engine) as session:
            snapshot = session.scalar(
                select(PaperAccountSnapshot).where(
                    PaperAccountSnapshot.account_id == account_id,
                    PaperAccountSnapshot.trade_date == trade_date,
                    PaperAccountSnapshot.point_type == "trading",
                )
            )
            assert snapshot is not None
            assert snapshot.event_at.tzinfo is not None
            assert snapshot.event_at.utcoffset() == timedelta(0)
            assert snapshot.event_at == datetime.combine(trade_date, time.max, tzinfo=timezone.utc)
    finally:
        Base.metadata.drop_all(engine, tables=list(reversed(tables)))
        engine.dispose()


def _trading_snapshot_values(account_id: int, trade_date: date, event_at: datetime) -> dict[str, object]:
    return {
        "account_id": account_id,
        "trade_date": trade_date,
        "event_at": event_at,
        "point_type": "trading",
        "quality_status": "valid",
        "cash_available": Decimal("99000.0000"),
        "cash_frozen": Decimal("0.0000"),
        "market_value": Decimal("1000.0000"),
        "total_assets": Decimal("100000.0000"),
        "realized_pnl": Decimal("0.0000"),
        "unrealized_pnl": Decimal("0.0000"),
        "position_count": 1,
        "order_count": 1,
        "trade_count": 1,
        "pending_settlement": Decimal("0.0000"),
    }
