from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'round_trip.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_record_buy_opens_round_trip(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.FILLED
    )
    trade = repo.create_trade(
        order.id,
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.0000"),
        Decimal("5.0000"),
        date(2026, 6, 16),
    )

    RoundTripService(repo).record_fill(trade, post_position_quantity=100)
    session.commit()

    cycle = repo.get_open_round_trip(account.id, "000001.SZ")
    assert cycle is not None
    assert cycle.entry_amount == Decimal("1000.0000")
    assert cycle.fees == Decimal("5.0000")
    engine.dispose()


def test_record_full_sell_closes_round_trip(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    buy_order = repo.create_order(
        account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16), OrderStatus.FILLED
    )
    buy_trade = repo.create_trade(
        buy_order.id,
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        Decimal("1000.0000"),
        Decimal("5.0000"),
        date(2026, 6, 16),
    )
    service = RoundTripService(repo)
    service.record_fill(buy_trade, post_position_quantity=100)
    sell_order = repo.create_order(
        account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("11.00"), date(2026, 6, 20), OrderStatus.FILLED
    )
    sell_trade = repo.create_trade(
        sell_order.id,
        account.id,
        "000001.SZ",
        OrderSide.SELL,
        100,
        Decimal("11.00"),
        Decimal("1100.0000"),
        Decimal("6.0000"),
        date(2026, 6, 20),
    )

    service.record_fill(sell_trade, post_position_quantity=0)
    session.commit()

    cycle = repo.list_round_trips(account.id)[0]
    assert cycle.status == "closed"
    assert cycle.exit_amount == Decimal("1100.0000")
    assert cycle.fees == Decimal("11.0000")
    assert cycle.realized_pnl == Decimal("89.0000")
    assert cycle.return_pct == Decimal("0.089000")
    assert cycle.holding_days == 4
    engine.dispose()
