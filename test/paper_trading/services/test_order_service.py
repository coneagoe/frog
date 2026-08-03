from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import Mock

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import paper_trading.services.order_service as order_service_module
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
from paper_trading.domain.enums import Market, OrderSide, OrderStatus
from paper_trading.services.order_service import OrderService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import DailyBar, StorageMarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from storage.model.general_info_ggt import GeneralInfoGGT
from test.paper_trading.fakes import FakeHistoryStorage, FakeMarketDataProvider, FakeTradeCalendar


class _TestDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2026, 6, 16)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(order_service_module, "date", _TestDate)


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
    repo.upsert_daily_bar_diagnostic(date(2026, 6, 16), "000001.SZ", "bfq", "missing_market_data", [], resolved=False)
    session.commit()
    for business_date in (date(2026, 6, 16), date(2026, 6, 17), date(2026, 7, 21)):
        repo.upsert_daily_bar_diagnostic(
            business_date,
            "000001.SZ",
            "bfq",
            "missing_market_data",
            [],
            resolved=False,
        )
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


def test_place_order_rejects_closed_trade_date(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 14),
    )
    session.commit()

    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_TRADE_DATE"
    assert order.rejection_reason == "Trade date is not open"
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_place_order_replays_idempotency_key_without_second_reservation(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    first = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="same-order",
    )
    second = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="same-order",
    )

    assert second.id == first.id
    assert len(repo.list_cash_ledger(account.id)) == 2
    engine.dispose()


def test_place_order_normalizes_whitespace_idempotency_to_none_without_collision(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("whitespace-key", Decimal("100000.00"))

    first = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="   ",
    )
    second = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="\t \n",
    )
    session.commit()

    assert first.id != second.id
    assert first.idempotency_key is None
    assert second.idempotency_key is None
    assert len(repo.list_cash_ledger(account.id)) == 3  # initial deposit + two freezes
    engine.dispose()


def test_place_order_allows_same_idempotency_key_for_different_accounts(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    first_account = repo.create_account("first-account", Decimal("100000.00"))
    second_account = repo.create_account("second-account", Decimal("100000.00"))

    first = service.place_order(
        first_account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="shared-key",
    )
    second = service.place_order(
        second_account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="shared-key",
    )
    session.commit()

    assert first.id != second.id
    assert first.account_id == first_account.id
    assert second.account_id == second_account.id
    engine.dispose()


def test_place_order_integrity_collision_rolls_back_and_re_fetches_existing_order(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("collision-account", Decimal("100000.00"))
    existing = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="racing-key",
    )
    session.commit()

    original_create_order = repo.create_order
    create_order_calls = 0

    def collide_once(*args, **kwargs):
        nonlocal create_order_calls
        create_order_calls += 1
        if create_order_calls == 1:
            raise IntegrityError("simulated concurrent idempotency insert", {}, Exception())
        return original_create_order(*args, **kwargs)

    repo.get_order_by_idempotency_key = Mock(side_effect=[None, existing])
    repo.create_order = Mock(side_effect=collide_once)

    replayed = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="racing-key",
    )

    assert replayed.id == existing.id
    assert create_order_calls == 1
    assert len(repo.list_cash_ledger(account.id)) == 2  # initial deposit + original freeze
    engine.dispose()


def test_place_order_accepts_open_historical_date_without_unresolved_bfq_diagnostic(tmp_path, monkeypatch):
    class HistoricalToday(date):
        @classmethod
        def today(cls) -> date:
            return cls(2026, 8, 2)

    monkeypatch.setattr(order_service_module, "date", HistoricalToday)
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("historical-date", Decimal("100000.00"))

    order = service.place_order(
        account.id,
        "000002.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.ACCEPTED.value
    assert order.rejection_code is None
    assert repo.get_cash_available(account.id) == Decimal("98994.9900")
    engine.dispose()


def test_place_order_replays_past_a_share_buy_without_current_cash_freeze(tmp_path, monkeypatch):
    class HistoricalToday(date):
        @classmethod
        def today(cls) -> date:
            return cls(2026, 8, 2)

    monkeypatch.setattr(order_service_module, "date", HistoricalToday)
    engine = create_engine(f"sqlite:///{tmp_path / 'historical_buy.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    service = OrderService(repo, FakeMarketDataProvider())
    account = repo.create_account("historical-buy", Decimal("100000.00"))
    trade_date = date(2026, 6, 16)

    order = service.place_order(
        account.id,
        "000002.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
    )

    assert order.status == OrderStatus.FILLED.value
    assert order.frozen_cash == Decimal("1005.0100")
    assert repo.get_cash_available(account.id) == Decimal("98994.9900")
    assert repo.get_position(account.id, "000002.SZ").total_quantity == 100
    engine.dispose()


def test_place_order_replays_past_sell_against_historical_matured_position(tmp_path, monkeypatch):
    class HistoricalToday(date):
        @classmethod
        def today(cls) -> date:
            return cls(2026, 8, 2)

    monkeypatch.setattr(order_service_module, "date", HistoricalToday)
    engine = create_engine(f"sqlite:///{tmp_path / 'historical_sell.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    service = OrderService(repo, FakeMarketDataProvider())
    account = repo.create_account("historical-sell", Decimal("100000.00"))
    buy_date = date(2026, 6, 15)
    sell_date = date(2026, 6, 16)

    service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        1100,
        Decimal("10.00"),
        buy_date,
    )
    sell = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.SELL,
        1100,
        Decimal("11.00"),
        sell_date,
    )

    assert sell.status == OrderStatus.FILLED.value
    assert sell.rejection_code is None
    assert repo.get_position(account.id, "000001.SZ").total_quantity == 0
    engine.dispose()


def test_historical_order_33_sell_is_not_rejected_for_past_date(tmp_path, monkeypatch):
    class HistoricalToday(date):
        @classmethod
        def today(cls) -> date:
            return cls(2026, 8, 2)

    monkeypatch.setattr(order_service_module, "date", HistoricalToday)
    engine = create_engine(f"sqlite:///{tmp_path / 'order_33.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    buy_date = date(2026, 7, 29)
    sell_date = date(2026, 7, 30)
    market_data = FakeMarketDataProvider(
        {
            ("002558", sell_date): DailyBar(
                "002558",
                sell_date,
                Decimal("28.00"),
                Decimal("29.65"),
                Decimal("27.52"),
                Decimal("28.00"),
            )
        }
    )
    service = OrderService(repo, market_data)
    account = repo.create_account("order-33", Decimal("100000.00"))
    service.place_order(account.id, "002558", OrderSide.BUY, 1100, Decimal("10.00"), buy_date)

    sell = service.place_order(account.id, "002558", OrderSide.SELL, 1100, Decimal("28.00"), sell_date)

    assert sell.status == OrderStatus.FILLED.value
    assert sell.rejection_code is None
    assert repo.get_position(account.id, "002558").total_quantity == 0
    engine.dispose()


def test_past_a_share_order_requires_unresolved_canonical_bfq_diagnostic(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("historical-canonical", Decimal("100000.00"))
    trade_date = date(2026, 6, 17)
    repo.upsert_daily_bar_diagnostic(trade_date, "000002.SZ", "bfq", "missing_market_data", [], resolved=False)

    order = service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
    )

    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == Market.A_SHARE.value
    engine.dispose()


def test_historical_diagnostic_gate_is_only_for_a_share_market(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("historical-market-guard", Decimal("100000.00"))
    service = OrderService(repo, FakeMarketDataProvider())

    order = service._place_a_share_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 21),
        Market.HK_CONNECT,
        None,
        None,
    )

    assert order.status == OrderStatus.ACCEPTED.value


def test_past_hk_connect_order_uses_hk_validation_without_bfq_diagnostic(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("historical-hk", Decimal("100000.00"))
    sqlite_session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    sqlite_session.flush()
    service = OrderService(
        repo,
        FakeMarketDataProvider(),
        hk_metadata=HkConnectMetadataProvider(sqlite_session),
    )

    order = service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )

    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == Market.HK_CONNECT.value


def test_place_order_rejects_idempotency_key_for_different_request(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        idempotency_key="same-order",
    )

    with pytest.raises(Exception, match="idempotency key already belongs"):
        service.place_order(
            account.id,
            "000001.SZ",
            OrderSide.BUY,
            200,
            Decimal("10.00"),
            date(2026, 6, 16),
            idempotency_key="same-order",
        )
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
    position = repo.get_position(account.id, "000001.SZ")
    assert position is not None
    assert position.frozen_quantity == 100
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
    repo.upsert_daily_bar_diagnostic(date(2026, 6, 16), "000001.SZ", "bfq", "missing_market_data", [], resolved=False)
    session.commit()

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


def test_place_sell_order_rejects_t1_violation(tmp_path):
    """Selling on the same trade date as the only position lot's buy_trade_date is rejected (A-share T+1)."""
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(
        account.id,
        "000001.SZ",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("900.00"),
    )
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 16), 100, 100, Decimal("9.00"))

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
    assert order.rejection_code == "A_SHARE_T1_VIOLATION"
    assert "A股 T+1" in order.rejection_reason
    assert "不可当日卖出" in order.rejection_reason
    position = repo.get_position(account.id, "000001.SZ")
    assert position is not None
    assert position.frozen_quantity == 0
    engine.dispose()


def test_place_sell_order_rejects_partial_t1_violation_with_mixed_lots(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(
        account.id,
        "000001.SZ",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("1800.00"),
    )
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 15), 100, 100, Decimal("9.00"))
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 16), 100, 100, Decimal("9.00"))

    order = service.place_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=200,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
    )
    session.commit()

    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "A_SHARE_T1_VIOLATION"
    assert "A股 T+1" in order.rejection_reason
    assert "不可当日卖出" in order.rejection_reason
    position = repo.get_position(account.id, "000001.SZ")
    assert position is not None
    assert position.frozen_quantity == 0
    engine.dispose()


def test_place_sell_order_keeps_existing_frozen_quantity_after_t1_rejection(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(
        account.id,
        "000001.SZ",
        total_quantity=200,
        frozen_quantity=100,
        cost_amount=Decimal("1800.00"),
    )
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 16), 100, 100, Decimal("9.00"))

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
    assert order.rejection_code == "A_SHARE_T1_VIOLATION"
    position = repo.get_position(account.id, "000001.SZ")
    assert position is not None
    assert position.frozen_quantity == 100
    engine.dispose()


def test_place_sell_order_keeps_insufficient_position_precedence_when_position_is_frozen(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(
        account.id,
        "000001.SZ",
        total_quantity=100,
        frozen_quantity=100,
        cost_amount=Decimal("900.00"),
    )
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 16), 100, 100, Decimal("9.00"))

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
    position = repo.get_position(account.id, "000001.SZ")
    assert position is not None
    assert position.frozen_quantity == 100
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


def test_place_buy_order_uses_account_fee_config(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account(
        "custom-fee",
        Decimal("100000.00"),
        commission_rate=Decimal("0.001"),
        min_commission=Decimal("1.00"),
        stamp_duty_rate=Decimal("0.0005"),
        transfer_fee_rate=Decimal("0"),
    )

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
    assert order.frozen_cash == Decimal("1001.0000")
    assert repo.get_cash_available(account.id) == Decimal("98999.0000")
    engine.dispose()


# ── HK Connect tests ──────────────────────────────────────────────────


def test_hk_connect_buy_rejects_unknown_symbol(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-buy", Decimal("100000.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(sqlite_session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "99999",
        OrderSide.BUY,
        100,
        Decimal("50.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "UNKNOWN_HK_SECURITY"


def test_hk_connect_buy_rejects_non_board_lot(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-lot", Decimal("100000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        50,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_LOT_SIZE"


def test_a_share_order_unchanged_with_market_omitted(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-demo", Decimal("100000.00"))
    repo.upsert_daily_bar_diagnostic(date(2026, 7, 21), "000001.SZ", "bfq", "missing_market_data", [], resolved=False)
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(sqlite_session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 21),
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == "a_share"


def test_a_share_explicit_market_still_works(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-explicit", Decimal("100000.00"))
    repo.upsert_daily_bar_diagnostic(date(2026, 7, 21), "000001.SZ", "bfq", "missing_market_data", [], resolved=False)
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(sqlite_session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 21),
        market=Market.A_SHARE,
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == "a_share"


def test_hk_connect_accepts_board_lot_buy(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-ok", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == "hk_connect"
    assert Decimal(order.frozen_cash or 0) > 0


def test_hk_connect_rejects_off_tick_price(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-tick", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("400.025"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_TICK_SIZE"


def test_place_order_rejects_unknown_market(sqlite_session):
    """An unsupported market string should produce a controlled rejection, not a ValueError."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("bad-mkt", Decimal("100000.00"))
    md = FakeMarketDataProvider()
    service = OrderService(repo, md)
    order = service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 21),
        market="unknown_market",
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_MARKET"


# ── HK Connect sell tests ─────────────────────────────────────────────


def test_hk_connect_sell_board_lot_ok(sqlite_session):
    """Sell a board-lot multiple of an HK position."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-sell", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    repo.upsert_position(account.id, "00700", total_quantity=200, frozen_quantity=0, cost_amount=Decimal("80000.00"))
    repo.create_position_lot(account.id, "00700", date(2026, 7, 20), 200, 200, Decimal("400.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.SELL,
        100,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.frozen_quantity == 100


def test_hk_connect_sell_odd_lot_ok(sqlite_session):
    """Sell an odd lot that exactly matches the odd-lot remainder."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-odd-sell", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    repo.upsert_position(account.id, "00700", total_quantity=250, frozen_quantity=0, cost_amount=Decimal("100000.00"))
    repo.create_position_lot(account.id, "00700", date(2026, 7, 20), 250, 250, Decimal("400.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    # odd_lot_remainder = 250 % 100 = 50, selling 50 is OK
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.SELL,
        50,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.frozen_quantity == 50


def test_hk_connect_sell_rejects_invalid_odd_lot(sqlite_session):
    """Sell an odd lot that doesn't match the odd-lot remainder or a board-lot multiple."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-bad-odd", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    repo.upsert_position(account.id, "00700", total_quantity=250, frozen_quantity=0, cost_amount=Decimal("100000.00"))
    repo.create_position_lot(account.id, "00700", date(2026, 7, 20), 250, 250, Decimal("400.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    # odd_lot_remainder = 250 % 100 = 50; selling 60 exceeds remainder and is not a board lot multiple
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.SELL,
        60,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_ODD_LOT_SELL"


def test_hk_connect_sell_rejects_partial_odd_lot(sqlite_session):
    """Partial odd-lot sell (less than full remainder) must be rejected."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-partial", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    repo.upsert_position(account.id, "00700", total_quantity=250, frozen_quantity=0, cost_amount=Decimal("100000.00"))
    repo.create_position_lot(account.id, "00700", date(2026, 7, 20), 250, 250, Decimal("400.00"))
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    # odd_lot_remainder = 250 % 100 = 50; selling 40 < remainder must reject
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.SELL,
        40,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "INVALID_ODD_LOT_SELL"


# ── Market/symbol mismatch tests ──────────────────────────────────────


def test_a_share_default_rejects_hk_symbol(sqlite_session):
    """Default (A-share) market should reject a 5-digit HK-style symbol."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-hk-sym", Decimal("100000.00"))
    md = FakeMarketDataProvider()
    service = OrderService(repo, md)
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 21),
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "MARKET_SYMBOL_MISMATCH"


def test_a_share_explicit_rejects_hk_symbol(sqlite_session):
    """Explicit A_SHARE market should reject a 5-digit HK-style symbol."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-hk-sym2", Decimal("100000.00"))
    md = FakeMarketDataProvider()
    service = OrderService(repo, md)
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 21),
        market=Market.A_SHARE,
    )
    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_code == "MARKET_SYMBOL_MISMATCH"


def test_hk_connect_accepts_hk_symbol(sqlite_session):
    """HK_CONNECT market should accept a 5-digit HK symbol that exists in metadata."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-hk-sym", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    md = FakeMarketDataProvider()
    hk_meta = HkConnectMetadataProvider(session)
    service = OrderService(repo, md, hk_metadata=hk_meta)
    order = service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )
    assert order.status == OrderStatus.ACCEPTED.value
    assert order.market == "hk_connect"
