from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.order_service import OrderService
from paper_trading.storage.market_data import StorageMarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


def _repo_and_service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'orders.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    storage = FakeHistoryStorage({})
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16), date(2026, 6, 17)]))
    return engine, session, repo, OrderService(repo, market_data)


def test_place_buy_order_freezes_estimated_cash(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.ACCEPTED.value
    assert order.frozen_cash == Decimal("1005.0100")
    assert repo.get_cash_available(account.id) == Decimal("98994.9900")
    engine.dispose()


def test_place_order_rejects_invalid_lot_size(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=250,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_LOT_SIZE"
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_place_buy_order_rejects_insufficient_cash(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("1000.00"))

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INSUFFICIENT_CASH"
    assert repo.get_cash_available(account.id) == Decimal("1000.0000")
    engine.dispose()


def test_place_sell_order_freezes_sellable_position(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(
        account.id,
        "000001.SZ",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("1800.00"),
    )
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 15), 200, 200, Decimal("9.00"))

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.ACCEPTED.value
    assert order.frozen_quantity == 100
    assert repo.get_position(account.id, "000001.SZ").frozen_quantity == 100
    engine.dispose()


def test_cancel_accepted_buy_order_releases_cash(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16))

    cancelled = service.cancel_order(order.id)
    session.commit()

    assert cancelled.status == OrderStatus.CANCELLED.value
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_cancel_rejected_order_raises(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = service.place_order(account.id, "000001.SZ", OrderSide.BUY, 250, Decimal("10.00"), date(2026, 6, 16))

    with pytest.raises(ValueError):
        service.cancel_order(order.id)
    session.close()
    engine.dispose()
