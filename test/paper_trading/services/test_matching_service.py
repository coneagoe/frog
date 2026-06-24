from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
)
from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_service import OrderService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import StorageMarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


def _services(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matching.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 6, 16)
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.5],
                    COL_HIGH: [10.5],
                    COL_LOW: [9.0],
                    COL_CLOSE: [10.0],
                }
            ),
        }
    )
    market_data = StorageMarketDataProvider(
        storage,
        FakeTradeCalendar([date(2026, 6, 15), trade_date, date(2026, 6, 17)]),
    )
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)
    order_service = OrderService(repo, market_data)
    return engine, session, repo, order_service, matching_service, trade_date


def test_matching_fills_buy_order_and_creates_lot(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    run = matching_service.run(trade_date)
    session.commit()

    filled = repo.get_order(order.id)
    lots = repo.get_lots(account.id, "000001.SZ")
    assert run.filled_count == 1
    assert filled.status == OrderStatus.FILLED.value
    assert filled.filled_quantity == 100
    assert repo.get_cash_available(account.id) == Decimal("98994.9900")
    assert lots[0].remaining_quantity == 100
    engine.dispose()


def test_default_matching_does_not_skip_invalid_validity_order(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    repo.update_order_validity(order, "invalid", "BUY_AT_LIMIT_UP_TOUCH")

    run = matching_service.run(trade_date)
    session.commit()

    assert run.filled_count == 1
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    engine.dispose()


def test_matching_skips_limit_order_not_touched(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("8.50"), trade_date)

    run = matching_service.run(trade_date)
    session.commit()

    assert run.skipped_count == 1
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()


def test_matching_fills_sell_order_and_releases_frozen_position(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, "000001.SZ", 200, 0, Decimal("1800.00"))
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 15), 200, 200, Decimal("9.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("10.00"), trade_date)

    run = matching_service.run(trade_date)
    session.commit()

    position = repo.get_position(account.id, "000001.SZ")
    assert run.filled_count == 1
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert position.total_quantity == 100
    assert position.frozen_quantity == 0
    assert repo.get_cash_available(account.id) == Decimal("100994.4900")
    engine.dispose()
