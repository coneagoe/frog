from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from storage.model.general_info_ggt import GeneralInfoGGT
from test.paper_trading.fakes import FakeMarketDataProvider


class StaticMarketData:
    def __init__(self, bar: DailyBar | None):
        self.bar = bar

    def is_trade_date(self, trade_date: date) -> bool:
        return True

    def next_trade_date(self, trade_date: date) -> date:
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
        if self.bar is None:
            raise KeyError(f"No daily bar for {symbol} on {trade_date.isoformat()}")
        return self.bar


class FailingMarketData:
    """Market data that raises an unexpected (non-market-data) error."""

    def is_trade_date(self, trade_date: date) -> bool:
        return True

    def next_trade_date(self, trade_date: date) -> date:
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
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


# ── HK Connect validity tests ──────────────────────────────────────────


def test_hk_connect_validity_checks_tick_alignment(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-val", Decimal("100000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    hk_meta = HkConnectMetadataProvider(session)
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.025"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    bar = DailyBar(
        symbol="00700",
        trade_date=date(2026, 7, 21),
        open=Decimal("400"),
        high=Decimal("410"),
        low=Decimal("395"),
        close=Decimal("405"),
    )
    bars = {("00700", date(2026, 7, 21)): bar}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md, hk_metadata=hk_meta)
    check = service.analyze_order(order)
    assert check.status == "invalid"
    assert "tick" in check.reason_code.lower()


def test_hk_connect_validity_no_limit_up_down(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-nolimit", Decimal("100000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    hk_meta = HkConnectMetadataProvider(session)
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    bar = DailyBar(
        symbol="00700",
        trade_date=date(2026, 7, 21),
        open=Decimal("400"),
        high=Decimal("410"),
        low=Decimal("395"),
        close=Decimal("405"),
    )
    bars = {("00700", date(2026, 7, 21)): bar}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md, hk_metadata=hk_meta)
    check = service.analyze_order(order)
    assert check.touched_limit_up is None
    assert check.touched_limit_down is None
    assert check.price_in_range is True


def test_a_share_validity_unchanged(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-val", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
    )
    bar = DailyBar(
        symbol="000001.SZ",
        trade_date=date(2026, 7, 21),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        up_limit=Decimal("11.5"),
        down_limit=Decimal("8.5"),
    )
    bars = {("000001.SZ", date(2026, 7, 21)): bar}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md)
    check = service.analyze_order(order)
    assert check.touched_limit_up is not None  # A-share sets these


def test_hk_connect_passes_market_to_provider(sqlite_session):
    """Verify that the HK validity path passes market='hk_connect' to get_daily_bar."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-mkt", Decimal("100000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    hk_meta = HkConnectMetadataProvider(session)
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )

    class MarketAwareProvider(FakeMarketDataProvider):
        def __init__(self):
            super().__init__()
            self.captured_markets: list[str | None] = []

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            self.captured_markets.append(market)
            return DailyBar(
                symbol=symbol,
                trade_date=trade_date,
                open=Decimal("400"),
                high=Decimal("410"),
                low=Decimal("395"),
                close=Decimal("405"),
            )

    md = MarketAwareProvider()
    service = TradeValidityService(repo, md, hk_metadata=hk_meta)
    service.analyze_order(order)
    assert md.captured_markets == ["hk_connect"]


def test_hk_connect_unknown_symbol_returns_unknown_security_before_market_data(sqlite_session):
    """Metadata check happens before market-data fetch; an unknown HK symbol
    must get UNKNOWN_HK_SECURITY even when the provider can return a bar."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-unk", Decimal("100000.00"))
    session = sqlite_session
    # Do NOT register the symbol in GeneralInfoGGT.
    hk_meta = HkConnectMetadataProvider(session)
    order = repo.create_order(
        account_id=account.id,
        symbol="99999",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("100.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )

    # This provider would return a bar for any symbol, but the metadata
    # check should short-circuit before get_daily_bar is ever called.
    class CatchCallsProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            raise AssertionError("get_daily_bar should not be called for unknown HK symbol")

    md = CatchCallsProvider()
    service = TradeValidityService(repo, md, hk_metadata=hk_meta)
    check = service.analyze_order(order)
    assert check.status == "unchecked"
    assert check.reason_code == "UNKNOWN_HK_SECURITY"
    assert check.daily_low is None
    assert check.daily_high is None


# ── Existing tests ─────────────────────────────────────────────────────


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


# ── Validity check market persistence ────────────────────────────────────────


def test_hk_connect_validity_check_persists_market(sqlite_session):
    """HK validity check rows must persist market == 'hk_connect'."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-vcm", Decimal("100000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    hk_meta = HkConnectMetadataProvider(session)
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        market="hk_connect",
    )
    bar = DailyBar(
        symbol="00700",
        trade_date=date(2026, 7, 21),
        open=Decimal("400"),
        high=Decimal("410"),
        low=Decimal("395"),
        close=Decimal("405"),
    )
    bars = {("00700", date(2026, 7, 21)): bar}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md, hk_metadata=hk_meta)
    check = service.analyze_order(order)
    assert check.market == "hk_connect"


def test_a_share_validity_check_persists_market_a_share(sqlite_session):
    """A-share validity check rows must persist market == 'a_share'."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-vcm", Decimal("100000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
    )
    bar = DailyBar(
        symbol="000001.SZ",
        trade_date=date(2026, 7, 21),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        up_limit=Decimal("11.5"),
        down_limit=Decimal("8.5"),
    )
    bars = {("000001.SZ", date(2026, 7, 21)): bar}
    md = FakeMarketDataProvider(bars)
    service = TradeValidityService(repo, md)
    check = service.analyze_order(order)
    assert check.market == "a_share"
