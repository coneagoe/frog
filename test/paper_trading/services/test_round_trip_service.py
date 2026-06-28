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


def test_record_partial_sell_does_not_close_round_trip(tmp_path):
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
        account.id, "000001.SZ", OrderSide.SELL, 50, Decimal("11.00"), date(2026, 6, 20), OrderStatus.FILLED
    )
    sell_trade = repo.create_trade(
        sell_order.id,
        account.id,
        "000001.SZ",
        OrderSide.SELL,
        50,
        Decimal("11.00"),
        Decimal("550.0000"),
        Decimal("3.0000"),
        date(2026, 6, 20),
    )
    service.record_fill(sell_trade, post_position_quantity=50)
    session.commit()

    cycle = repo.get_open_round_trip(account.id, "000001.SZ")
    assert cycle is not None
    assert cycle.status == "open"
    assert cycle.exit_amount == Decimal("550.0000")
    assert cycle.fees == Decimal("8.0000")
    assert cycle.realized_pnl == Decimal("-458.0000")
    assert cycle.close_trade_id == sell_trade.id
    assert cycle.return_pct is None
    assert cycle.holding_days is None
    engine.dispose()


def test_rebuild_account_recreates_multiple_closed_cycles(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("rebuild-demo", Decimal("100000.00"))
    for idx, side, price, amount, fees, trade_date in [
        (1, OrderSide.BUY, "10.00", "1000.0000", "5.0000", date(2026, 6, 16)),
        (2, OrderSide.SELL, "11.00", "1100.0000", "6.0000", date(2026, 6, 20)),
        (3, OrderSide.BUY, "9.00", "900.0000", "5.0000", date(2026, 6, 21)),
        (4, OrderSide.SELL, "8.00", "800.0000", "5.0000", date(2026, 6, 25)),
    ]:
        order = repo.create_order(account.id, "000001.SZ", side, 100, Decimal(price), trade_date, OrderStatus.FILLED)
        repo.create_trade(order.id, account.id, "000001.SZ", side, 100, Decimal(price), Decimal(amount), Decimal(fees), trade_date)

    cycles = RoundTripService(repo).rebuild_account(account.id)
    session.commit()

    assert [cycle.status for cycle in cycles] == ["closed", "closed"]
    assert cycles[0].realized_pnl == Decimal("89.0000")
    assert cycles[1].realized_pnl == Decimal("-110.0000")
    engine.dispose()
