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
                    COL_STOCK_ID: ["000001", "000001"],
                    COL_DATE: ["2026-06-16", "2026-06-17"],
                    COL_OPEN: [9.5, 10.2],
                    COL_HIGH: [10.5, 10.8],
                    COL_LOW: [9.0, 10.0],
                    COL_CLOSE: [10.0, 10.5],
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


def test_matching_closes_round_trip_when_position_returns_to_zero(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("round-trip-demo", Decimal("100000.00"))
    order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    matching_service.run(trade_date)
    next_date = date(2026, 6, 17)
    order_service.place_order(account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("10.50"), next_date)
    matching_service.run(next_date)
    session.commit()

    cycles = repo.list_round_trips(account.id)
    assert len(cycles) == 1
    assert cycles[0].status == "closed"
    assert cycles[0].close_trade_date == next_date
    engine.dispose()


def test_matching_uses_account_fee_config_for_trade_fees(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account(
        "custom-fee",
        Decimal("100000.00"),
        commission_rate=Decimal("0.001"),
        min_commission=Decimal("1.00"),
        stamp_duty_rate=Decimal("0.0005"),
        transfer_fee_rate=Decimal("0"),
    )
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    matching_service.run(trade_date)
    session.commit()

    trades = repo.list_trades(account.id)
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert trades[0].fees == Decimal("1.0000")
    assert repo.get_cash_available(account.id) == Decimal("98999.0000")
    engine.dispose()


def test_fee_update_keeps_existing_trade_and_applies_to_future_order(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("fee-update", Decimal("100000.00"))
    first_order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    matching_service.run(trade_date)
    session.commit()

    first_trade = repo.list_trades(account.id)[0]
    original_trade_fee = first_trade.fees
    original_cash_ledger = [
        (entry.event_type, entry.amount, entry.trade_id)
        for entry in repo.list_cash_ledger(account.id)
    ]

    repo.update_account_fees(
        account.id,
        commission_rate=Decimal("0.001"),
        min_commission=Decimal("1.00"),
        stamp_duty_rate=Decimal("0"),
        transfer_fee_rate=Decimal("0"),
    )
    future_order = order_service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 17),
    )
    session.commit()

    assert repo.get_order(first_order.id).status == OrderStatus.FILLED.value
    assert repo.list_trades(account.id)[0].fees == original_trade_fee
    assert [(entry.event_type, entry.amount, entry.trade_id) for entry in repo.list_cash_ledger(account.id)][
        : len(original_cash_ledger)
    ] == original_cash_ledger
    assert future_order.status == OrderStatus.ACCEPTED.value
    assert future_order.frozen_cash == Decimal("1001.0000")
    engine.dispose()


def test_matching_uses_account_fee_config_for_sell_fees(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account(
        "custom-sell-fee",
        Decimal("100000.00"),
        commission_rate=Decimal("0"),
        min_commission=Decimal("0"),
        stamp_duty_rate=Decimal("0.001"),
        transfer_fee_rate=Decimal("0"),
    )
    repo.upsert_position(account.id, "000001.SZ", 200, 0, Decimal("1800.00"))
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 15), 200, 200, Decimal("9.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("10.00"), trade_date)

    matching_service.run(trade_date)
    session.commit()

    trades = repo.list_trades(account.id)
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert trades[0].fees == Decimal("1.0000")
    assert repo.get_cash_available(account.id) == Decimal("100999.0000")
    engine.dispose()
