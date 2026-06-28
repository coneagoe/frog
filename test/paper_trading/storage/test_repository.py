from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.storage.models import PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_create_account_deposits_initial_cash(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    session.commit()

    assert account.id is not None
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_create_order_persists_accepted_order(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))

    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.00"),
        frozen_quantity=0,
        idempotency_key="k1",
    )
    session.commit()

    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()


def test_order_validity_summary_and_detail_are_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )

    repo.update_order_validity(order, "valid", "VALID")
    check = repo.create_trade_validity_check(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        side="buy",
        input_price=Decimal("10.00"),
        daily_low=Decimal("9.00"),
        daily_high=Decimal("10.50"),
        limit_up_price=Decimal("11.00"),
        limit_down_price=Decimal("9.00"),
        touched_limit_up=False,
        touched_limit_down=True,
        price_in_range=True,
        status="valid",
        reason_code="VALID",
        reason_detail="Price is inside daily range",
        data_granularity="daily",
    )
    session.commit()

    saved = repo.get_order(order.id)
    assert saved.validity_status == "valid"
    assert saved.validity_reason == "VALID"
    assert saved.validity_checked_at is not None
    assert repo.list_trade_validity_checks(order.id)[0].id == check.id
    engine.dispose()


def test_delete_account_deletes_trade_validity_checks_before_orders(tmp_path):
    """delete_account removes PaperTradeValidityCheck rows so FK to orders does not fail."""
    engine = create_engine(f"sqlite:///{tmp_path / 'del_account.db'}")
    Base.metadata.create_all(engine)
    session: Session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account(name="demo", initial_cash=Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    repo.create_trade_validity_check(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        side="buy",
        input_price=Decimal("10.00"),
        daily_low=None,
        daily_high=None,
        status="unchecked",
        reason_code="MARKET_DATA_UNAVAILABLE",
        reason_detail="test",
        data_granularity="daily",
    )
    session.commit()

    # Verify the check exists before deletion
    assert session.query(PaperTradeValidityCheck).filter_by(account_id=account.id).count() == 1

    # Delete the account
    deleted = repo.delete_account(account.id)
    session.commit()

    assert deleted is True
    # Verify the account and its related rows are gone
    assert repo.get_account(account.id) is None
    assert session.query(PaperTradeValidityCheck).filter_by(account_id=account.id).count() == 0
    engine.dispose()


def test_round_trip_repository_creates_and_lists_closed_cycle(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("analytics-demo", Decimal("100000.00"))

    cycle = repo.create_round_trip(
        account_id=account.id,
        symbol="000001.SZ",
        open_trade_id=1,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )
    repo.update_round_trip(
        cycle,
        close_trade_id=2,
        close_trade_date=date(2026, 6, 20),
        exit_amount=Decimal("1100.0000"),
        fees=Decimal("10.0000"),
        realized_pnl=Decimal("90.0000"),
        return_pct=Decimal("0.090000"),
        holding_days=4,
        status="closed",
    )
    sqlite_session.commit()

    rows = repo.list_round_trips(account.id)
    assert len(rows) == 1
    assert rows[0].symbol == "000001.SZ"
    assert rows[0].status == "closed"
    assert rows[0].realized_pnl == Decimal("90.0000")


def test_delete_account_removes_round_trips(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("delete-round-trips", Decimal("100000.00"))
    repo.create_round_trip(
        account_id=account.id,
        symbol="000001.SZ",
        open_trade_id=1,
        open_trade_date=date(2026, 6, 16),
        entry_amount=Decimal("1000.0000"),
        fees=Decimal("5.0000"),
    )

    assert repo.delete_account(account.id) is True
    sqlite_session.commit()

    assert repo.list_round_trips(account.id) == []
