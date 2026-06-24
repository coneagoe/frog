from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_DOWN_LIMIT,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_PRE_CLOSE,
    COL_STOCK_ID,
    COL_UP_LIMIT,
)
from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.order_service import OrderService
from paper_trading.storage.market_data import StorageMarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


class FakeHistoryStorageWithEngine:
    def __init__(self, engine: Any, data: dict[str, pd.DataFrame]):
        self.engine = engine
        self._inner = FakeHistoryStorage(data)

    def load_history_data_stock(self, stock_id, period, adjust, start_date=None, end_date=None):
        return self._inner.load_history_data_stock(stock_id, period, adjust, start_date, end_date)


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


def test_place_buy_order_sets_validity_unchecked_when_market_data_missing(tmp_path):
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
    assert order.validity_status == "unchecked"
    assert order.validity_reason == "MARKET_DATA_UNAVAILABLE"
    engine.dispose()


def test_place_buy_order_sets_validity_valid_with_daily_bar(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'valid-bar.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    bar = pd.DataFrame(
        [
            {
                COL_DATE: "2026-06-16",
                COL_OPEN: "9.50",
                COL_HIGH: "10.50",
                COL_LOW: "9.00",
                COL_CLOSE: "10.00",
            }
        ]
    )
    # Populate stk_limit_a_stock for limit prices
    from storage.model.stk_limit_a_stock import StkLimitAStock

    Base.metadata.create_all(engine, tables=[StkLimitAStock.__table__])
    with engine.begin() as conn:
        conn.execute(
            StkLimitAStock.__table__.insert(),
            {
                COL_DATE: date(2026, 6, 16),
                COL_STOCK_ID: "000001",
                COL_PRE_CLOSE: 10.0,
                COL_UP_LIMIT: 11.0,
                COL_DOWN_LIMIT: 9.0,
            },
        )

    storage = FakeHistoryStorageWithEngine(engine, {"000001": bar})
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))
    service = OrderService(repo, market_data)
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
    assert order.validity_status == "valid"
    assert order.validity_reason == "VALID"
    engine.dispose()


def test_place_sell_order_sets_validity_unchecked_when_market_data_missing(tmp_path):
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
    assert order.validity_status == "unchecked"
    assert order.validity_reason == "MARKET_DATA_UNAVAILABLE"
    engine.dispose()


def test_rejected_buy_order_has_validity_check(tmp_path):
    """A rejected buy order should still have a validity check record."""
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

    checks = repo.list_trade_validity_checks(order.id)
    assert len(checks) == 1
    assert checks[0].status is not None
    assert checks[0].reason_code is not None
    engine.dispose()


def test_rejected_sell_order_has_validity_check(tmp_path):
    """A rejected sell order due to insufficient position should have a validity check."""
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INSUFFICIENT_POSITION"

    checks = repo.list_trade_validity_checks(order.id)
    assert len(checks) == 1
    assert checks[0].status is not None
    assert checks[0].reason_code is not None
    engine.dispose()
