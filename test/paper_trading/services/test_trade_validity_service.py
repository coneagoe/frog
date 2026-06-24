from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


class StaticMarketData:
    def __init__(self, bar: DailyBar | None):
        self.bar = bar

    def is_trade_date(self, trade_date: date) -> bool:
        return True

    def next_trade_date(self, trade_date: date) -> date:
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        if self.bar is None:
            raise KeyError(f"No daily bar for {symbol} on {trade_date.isoformat()}")
        return self.bar


class FailingMarketData:
    """Market data that raises an unexpected (non-market-data) error."""

    def is_trade_date(self, trade_date: date) -> bool:
        return True

    def next_trade_date(self, trade_date: date) -> date:
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        raise RuntimeError("Unexpected infrastructure failure")


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'validity.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_analyze_order_persists_validity_detail_and_summary(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    service = TradeValidityService(
        repo,
        StaticMarketData(
            DailyBar(
                symbol="000001.SZ",
                trade_date=date(2026, 6, 16),
                open=Decimal("9.50"),
                high=Decimal("10.50"),
                low=Decimal("9.00"),
                close=Decimal("10.00"),
                up_limit=Decimal("11.00"),
                down_limit=Decimal("8.00"),
            )
        ),
    )

    check = service.analyze_order(order)
    session.commit()

    assert check.status == "valid"
    assert repo.get_order(order.id).validity_status == "valid"
    assert repo.list_trade_validity_checks(order.id)[0].reason_code == "VALID"
    engine.dispose()


def test_analyze_order_marks_missing_market_data_unchecked(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    service = TradeValidityService(repo, StaticMarketData(None))

    check = service.analyze_order(order)
    session.commit()

    assert check.status == "unchecked"
    assert check.reason_code == "MARKET_DATA_UNAVAILABLE"
    assert repo.get_order(order.id).validity_status == "unchecked"
    engine.dispose()


def test_analyze_order_marks_unchecked_when_limit_prices_missing(tmp_path):
    """When bar is loaded but up_limit/down_limit are both None, mark unchecked."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    # Bar with no limit prices (default None for up_limit/down_limit)
    bar = DailyBar(
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        open=Decimal("9.50"),
        high=Decimal("10.50"),
        low=Decimal("9.00"),
        close=Decimal("10.00"),
    )
    service = TradeValidityService(repo, StaticMarketData(bar))

    check = service.analyze_order(order)
    session.commit()

    assert check.status == "unchecked"
    assert check.reason_code == "LIMIT_PRICE_UNAVAILABLE"
    assert check.limit_up_price is None
    assert check.limit_down_price is None
    assert check.touched_limit_up is None
    assert check.touched_limit_down is None
    assert repo.get_order(order.id).validity_status == "unchecked"
    engine.dispose()


def test_analyze_order_still_rejects_out_of_range_when_limit_prices_missing(tmp_path):
    """When limit prices are missing but price is outside daily range, still invalid."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("20.00"),  # Above daily high of 10.50
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    bar = DailyBar(
        symbol="000001.SZ",
        trade_date=date(2026, 6, 16),
        open=Decimal("9.50"),
        high=Decimal("10.50"),
        low=Decimal("9.00"),
        close=Decimal("10.00"),
    )
    service = TradeValidityService(repo, StaticMarketData(bar))

    check = service.analyze_order(order)
    session.commit()

    assert check.status == "invalid"
    assert check.reason_code == "PRICE_OUT_OF_DAILY_RANGE"
    assert check.price_in_range is False
    engine.dispose()


def test_analyze_order_lets_unexpected_errors_propagate(tmp_path):
    """Non-market-data exceptions must propagate, not be swallowed."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    service = TradeValidityService(repo, FailingMarketData())

    with pytest.raises(RuntimeError, match="Unexpected infrastructure failure"):
        service.analyze_order(order)

    session.rollback()
    engine.dispose()
