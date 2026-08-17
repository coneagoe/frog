from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Self, cast

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import paper_trading.services.order_service as order_service_module
from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
)
from paper_trading.domain.enums import (
    CashEventType,
    ETFEligibilityStatus,
    Market,
    MatchingRunStatus,
    OrderSide,
    OrderStatus,
)
from paper_trading.services.etf_eligibility_service import ETFEligibilityService
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.services.order_service import OrderService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import DailyBar, StorageMarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from storage.model.etf_basic import ETFBasic
from test.paper_trading.fakes import FakeHistoryStorage, FakeMarketDataProvider, FakeTradeCalendar


class _TestDate(date):
    @classmethod
    def today(cls) -> Self:
        return cls(2026, 6, 16)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(order_service_module, "date", _TestDate)


def _services(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matching.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 6, 16)
    for business_date in (trade_date, date(2026, 6, 17)):
        for symbol in ("000001.SZ", "000001"):
            repo.upsert_daily_bar_diagnostic(
                business_date,
                Market.A_SHARE,
                symbol,
                "bfq",
                "missing_market_data",
                [],
                resolved=False,
            )
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


def _add_supported_etf(repo, symbol: str = "510300") -> None:
    provider = ETFBasic(基金代码=symbol, 中文简称="CSI 300 ETF", 交易所="SH", 存续状态="L")
    repo.session.add(provider)
    repo.session.flush()
    repo.upsert_etf_eligibility(
        symbol,
        provider.中文简称,
        provider.交易所,
        provider.存续状态,
        datetime(2026, 6, 16, tzinfo=timezone.utc),
        status=ETFEligibilityStatus.SUPPORTED,
    )


def test_etf_workflow_fills_buy_rejects_same_date_sell_and_settles_next_date_sell(tmp_path):
    engine, session, repo, _, _, trade_date = _services(tmp_path)
    _add_supported_etf(repo)
    next_date = date(2026, 6, 17)
    market_data = FakeMarketDataProvider(
        {
            ("510300", trade_date): DailyBar(
                "510300", trade_date, Decimal("3.100"), Decimal("3.200"), Decimal("3.000"), Decimal("3.150")
            ),
            ("510300", next_date): DailyBar(
                "510300", next_date, Decimal("3.200"), Decimal("3.300"), Decimal("3.100"), Decimal("3.250")
            ),
        }
    )
    order_service = OrderService(repo, market_data, etf_eligibility=ETFEligibilityService(repo))
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    account = repo.create_account("etf-workflow", Decimal("100000.00"), etf_commission_rate=Decimal("0.0001"))

    buy = order_service.place_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.150"), trade_date, market=Market.ETF
    )
    buy_run = matching_service.run(trade_date, account.id)
    assert buy_run.filled_count == 1
    assert repo.get_order(buy.id).status == OrderStatus.FILLED.value
    trade = repo.list_trades(account.id)[0]
    assert (trade.market, trade.fees) == (Market.ETF, Decimal("0.0315"))
    position = repo.get_position(account.id, Market.ETF, "510300")
    assert position is not None
    assert position.total_quantity == 100
    assert repo.get_lots(account.id, Market.ETF, "510300")[0].remaining_quantity == 100
    assert repo.list_pending_settlements(account.id) == []

    same_date_sell = order_service.place_order(
        account.id, "510300", OrderSide.SELL, 100, Decimal("3.150"), trade_date, market=Market.ETF
    )
    next_date_sell = order_service.place_order(
        account.id, "510300", OrderSide.SELL, 100, Decimal("3.250"), next_date, market=Market.ETF
    )
    sell_run = matching_service.run(next_date, account.id)
    session.commit()

    assert same_date_sell.status == OrderStatus.REJECTED.value
    assert same_date_sell.rejection_code == "ETF_T1_VIOLATION"
    assert same_date_sell.rejection_reason is not None
    assert "ETF T+1" in same_date_sell.rejection_reason
    assert "same-day purchases" in same_date_sell.rejection_reason
    assert sell_run.filled_count == 1
    assert repo.get_order(next_date_sell.id).status == OrderStatus.FILLED.value
    assert repo.get_position(account.id, Market.ETF, "510300") is None
    assert repo.get_cash_available(account.id) == Decimal("100009.9360")
    assert repo.list_pending_settlements(account.id) == []
    engine.dispose()


def test_historical_etf_buy_then_next_date_sell_rebuilds_full_lifecycle(tmp_path, monkeypatch):
    class ReplayToday(date):
        @classmethod
        def today(cls) -> Self:
            return cls(2026, 6, 17)

    monkeypatch.setattr(order_service_module, "date", ReplayToday)
    engine, session, repo, _, _, _ = _services(tmp_path)
    _add_supported_etf(repo)
    buy_date = date(2026, 6, 15)
    sell_date = date(2026, 6, 16)

    class RecordingETFMarketDataProvider(FakeMarketDataProvider):
        def __init__(self, bars: dict[tuple[str, date], DailyBar]) -> None:
            super().__init__(bars)
            self.requested_bars: list[tuple[str, date, str | None]] = []

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            self.requested_bars.append((symbol, trade_date, market))
            return super().get_daily_bar(symbol, trade_date, market)

    market_data = RecordingETFMarketDataProvider(
        {
            ("510300", buy_date): DailyBar(
                "510300", buy_date, Decimal("3.100"), Decimal("3.200"), Decimal("3.000"), Decimal("3.150")
            ),
            ("510300", sell_date): DailyBar(
                "510300", sell_date, Decimal("3.200"), Decimal("3.300"), Decimal("3.100"), Decimal("3.250")
            ),
        }
    )
    order_service = OrderService(repo, market_data, etf_eligibility=ETFEligibilityService(repo))
    account = repo.create_account("historical-etf", Decimal("100000.00"), etf_commission_rate=Decimal("0.0001"))
    automatic_rebuilds = []
    original_rebuild_account_from = OrderDeleteService.rebuild_account_from

    def record_automatic_rebuild(service, account_id, start_date, triggering_order_ids):
        rebuild = original_rebuild_account_from(service, account_id, start_date, triggering_order_ids)
        automatic_rebuilds.append((account_id, start_date, triggering_order_ids, rebuild.regenerated_counts))
        return rebuild

    monkeypatch.setattr(OrderDeleteService, "rebuild_account_from", record_automatic_rebuild)

    buy = order_service.place_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.150"), buy_date, market=Market.ETF
    )
    buy_trade = repo.list_trades(account.id)[0]
    buy_position = repo.get_position(account.id, Market.ETF, "510300")
    buy_lot = repo.get_lots(account.id, Market.ETF, "510300")[0]
    buy_snapshot = repo.list_snapshots(account.id)[0]

    assert (buy_trade.order_id, buy_trade.price, buy_trade.amount, buy_trade.trade_date) == (
        buy.id,
        Decimal("3.1500"),
        Decimal("315.0000"),
        buy_date,
    )
    assert buy_position is not None
    assert (buy_position.total_quantity, buy_position.frozen_quantity, buy_position.cost_amount) == (
        100,
        0,
        Decimal("315.0315"),
    )
    assert (
        buy_lot.buy_trade_date,
        buy_lot.original_quantity,
        buy_lot.remaining_quantity,
        buy_lot.cost_price,
        buy_lot.market,
    ) == (buy_date, 100, 100, Decimal("3.1500"), Market.ETF.value)
    assert (
        buy_snapshot.trade_date,
        buy_snapshot.cash_available,
        buy_snapshot.cash_frozen,
        buy_snapshot.market_value,
        buy_snapshot.total_assets,
        buy_snapshot.realized_pnl,
        buy_snapshot.unrealized_pnl,
        buy_snapshot.position_count,
        buy_snapshot.order_count,
        buy_snapshot.trade_count,
    ) == (
        buy_date,
        Decimal("99684.9685"),
        Decimal("0.0000"),
        Decimal("315.0000"),
        Decimal("99999.9685"),
        Decimal("0.0000"),
        Decimal("-0.0315"),
        1,
        1,
        1,
    )

    assert buy.frozen_cash == Decimal("315.0315")
    assert market_data.requested_bars == [
        ("510300", buy_date, Market.ETF),
        ("510300", buy_date, Market.ETF.value),
        ("510300", buy_date, Market.ETF),
        ("510300", buy_date, Market.ETF),
    ]

    market_data.requested_bars.clear()
    sell = order_service.place_order(
        account.id, "510300", OrderSide.SELL, 100, Decimal("3.250"), sell_date, market=Market.ETF
    )
    session.commit()

    assert automatic_rebuilds == [
        (account.id, buy_date, [buy.id], {"trades": 1, "snapshots": 1, "matching_runs": 1}),
        (account.id, sell_date, [sell.id], {"trades": 1, "snapshots": 1, "matching_runs": 1}),
    ]
    assert repo.get_order(buy.id).status == OrderStatus.FILLED.value
    assert repo.get_order(sell.id).status == OrderStatus.FILLED.value
    trades = repo.list_trades(account.id)
    assert [(trade.market, trade.side) for trade in trades] == [
        (Market.ETF.value, OrderSide.BUY.value),
        (Market.ETF.value, OrderSide.SELL.value),
    ]
    trades = repo.list_trades(account.id)
    assert [(trade.id, trade.price, trade.amount, trade.fees, trade.trade_date) for trade in trades] == [
        (trades[0].id, Decimal("3.1500"), Decimal("315.0000"), Decimal("0.0315"), buy_date),
        (trades[1].id, Decimal("3.2500"), Decimal("325.0000"), Decimal("0.0325"), sell_date),
    ]
    assert market_data.requested_bars == [
        ("510300", sell_date, Market.ETF.value),
        ("510300", sell_date, Market.ETF),
    ]
    assert repo.get_cash_available(account.id) == Decimal("100009.9360")
    assert repo.list_pending_settlements(account.id) == []
    assert [snapshot.trade_date for snapshot in repo.list_snapshots(account.id)] == [buy_date, sell_date]
    round_trips = repo.list_round_trips(account.id)
    assert len(round_trips) == 1
    assert round_trips[0].market == Market.ETF.value
    assert round_trips[0].status == "closed"
    assert [
        (event.event_type, event.amount, event.order_id, event.trade_id, event.trade_date)
        for event in repo.list_cash_ledger(account.id)
        if event.order_id is not None
    ] == [
        (CashEventType.FREEZE.value, Decimal("-315.0315"), buy.id, None, buy_date),
        (CashEventType.TRADE.value, Decimal("324.9675"), sell.id, trades[1].id, sell_date),
    ]
    assert [(trade.order_id, trade.price, trade.amount, trade.trade_date) for trade in trades] == [
        (buy.id, Decimal("3.1500"), Decimal("315.0000"), buy_date),
        (sell.id, Decimal("3.2500"), Decimal("325.0000"), sell_date),
    ]
    assert [
        (event.event_type, event.amount, event.order_id, event.trade_id) for event in repo.list_cash_ledger(account.id)
    ] == [
        (CashEventType.DEPOSIT.value, Decimal("100000.0000"), None, None),
        (CashEventType.FREEZE.value, Decimal("-315.0315"), buy.id, None),
        (CashEventType.TRADE.value, Decimal("324.9675"), sell.id, trades[1].id),
    ]
    snapshots = repo.list_snapshots(account.id)
    assert [
        (snapshot.trade_date, snapshot.cash_available, snapshot.market_value, snapshot.total_assets)
        for snapshot in snapshots
    ] == [
        (buy_date, Decimal("99684.9685"), Decimal("315.0000"), Decimal("99999.9685")),
        (sell_date, Decimal("100009.9360"), Decimal("0.0000"), Decimal("100009.9360")),
    ]
    assert (
        snapshots[1].realized_pnl,
        snapshots[1].unrealized_pnl,
        snapshots[1].position_count,
        snapshots[1].order_count,
        snapshots[1].trade_count,
    ) == (Decimal("9.9675"), Decimal("0.0000"), 0, 1, 1)
    round_trip = repo.list_round_trips(account.id)[0]
    assert (
        round_trip.status,
        round_trip.open_trade_id,
        round_trip.close_trade_id,
        round_trip.entry_amount,
        round_trip.exit_amount,
        round_trip.fees,
        round_trip.realized_pnl,
    ) == (
        "closed",
        trades[0].id,
        trades[1].id,
        Decimal("315.0000"),
        Decimal("325.0000"),
        Decimal("0.0640"),
        Decimal("9.9360"),
    )
    assert repo.get_position(account.id, Market.ETF, "510300") is None
    engine.dispose()


def test_historical_etf_buy_rejection_replay_dates_cash_release(tmp_path, monkeypatch):
    class ReplayToday(date):
        @classmethod
        def today(cls) -> Self:
            return cls(2026, 6, 17)

    monkeypatch.setattr(order_service_module, "date", ReplayToday)
    engine, session, repo, _, _, _ = _services(tmp_path)
    _add_supported_etf(repo)
    buy_date = date(2026, 6, 15)
    market_data = FakeMarketDataProvider(
        {
            ("510300", buy_date): DailyBar(
                "510300",
                buy_date,
                Decimal("3.100"),
                Decimal("3.200"),
                Decimal("3.000"),
                Decimal("3.150"),
                suspended=True,
            )
        }
    )
    order_service = OrderService(repo, market_data, etf_eligibility=ETFEligibilityService(repo))
    account = repo.create_account("historical-etf-rejection", Decimal("100000.00"))

    buy = order_service.place_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.150"), buy_date, market=Market.ETF
    )
    session.commit()

    assert repo.get_order(buy.id).status == OrderStatus.REJECTED.value
    assert [
        (event.event_type, event.order_id, event.trade_date)
        for event in repo.list_cash_ledger(account.id)
        if event.event_type == CashEventType.RELEASE.value
    ] == [(CashEventType.RELEASE, buy.id, buy_date)]
    engine.dispose()


def test_matching_keeps_same_symbol_a_share_and_etf_orders_positions_and_trades_isolated(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("a-share-etf-collision", Decimal("100000.00"))
    trade_date = date(2026, 7, 21)
    a_share_order = repo.create_order(
        account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.01"),
        market=Market.A_SHARE.value,
    )
    etf_order = repo.create_order(
        account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.15"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("315.03"),
        market=Market.ETF.value,
    )
    market_data = FakeMarketDataProvider(
        {
            ("510300", trade_date): DailyBar(
                "510300", trade_date, Decimal("3.000"), Decimal("10.500"), Decimal("2.900"), Decimal("3.150")
            )
        }
    )
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))

    run = matching_service.run(trade_date, account.id)

    assert run.filled_count == 2
    assert [(order.id, order.market) for order in repo.list_orders(account.id)] == [
        (a_share_order.id, Market.A_SHARE.value),
        (etf_order.id, Market.ETF.value),
    ]
    assert [(trade.market, trade.symbol) for trade in repo.list_trades(account.id)] == [
        (Market.A_SHARE, "510300"),
        (Market.ETF, "510300"),
    ]
    a_share_position = repo.get_position(account.id, Market.A_SHARE, "510300")
    etf_position = repo.get_position(account.id, Market.ETF, "510300")
    assert a_share_position is not None
    assert etf_position is not None
    assert a_share_position.total_quantity == 100
    assert etf_position.total_quantity == 100
    assert repo.get_lots(account.id, Market.A_SHARE, "510300")[0].remaining_quantity == 100
    assert repo.get_lots(account.id, Market.ETF, "510300")[0].remaining_quantity == 100


def test_etf_limit_outside_daily_range_stays_accepted_and_skipped(tmp_path):
    engine, session, repo, _, _, trade_date = _services(tmp_path)
    _add_supported_etf(repo)
    market_data = FakeMarketDataProvider(
        {
            ("510300", trade_date): DailyBar(
                "510300", trade_date, Decimal("3.100"), Decimal("3.200"), Decimal("3.000"), Decimal("3.150")
            )
        }
    )
    order_service = OrderService(repo, market_data, etf_eligibility=ETFEligibilityService(repo))
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    account = repo.create_account("etf-limit", Decimal("100000.00"))
    order = order_service.place_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("2.900"), trade_date, market=Market.ETF
    )

    run = matching_service.run(trade_date, account.id)
    session.commit()

    assert run.skipped_count == 1
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    assert repo.list_trades(account.id) == []
    engine.dispose()


def test_etf_missing_bar_records_raw_diagnostic_without_a_share_rebuild_eligibility(tmp_path):
    engine, session, repo, _, _, trade_date = _services(tmp_path)
    _add_supported_etf(repo)
    bars: dict[tuple[str, date], DailyBar] = {}

    class DelayedETFMarketData(FakeMarketDataProvider):
        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            assert market == Market.ETF.value
            try:
                return bars[(symbol, trade_date)]
            except KeyError:
                raise KeyError(f"No ETF daily bar for {symbol} on {trade_date}") from None

    market_data = DelayedETFMarketData()
    order_service = OrderService(repo, market_data, etf_eligibility=ETFEligibilityService(repo))
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    account = repo.create_account("etf-rebuild", Decimal("100000.00"))
    order = order_service.place_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.150"), trade_date, market=Market.ETF
    )

    first_run = matching_service.run(trade_date, account.id)
    diagnostic = next(item for item in repo.list_daily_bar_diagnostics() if item.stock_id == "510300")
    assert first_run.warning_count == 1
    assert (diagnostic.market, diagnostic.adjust.value, diagnostic.resolved) == ("etf", "raw", False)
    assert repo.list_eligible_daily_bar_rebuild_orders() == []

    bars[("510300", trade_date)] = DailyBar(
        "510300", trade_date, Decimal("3.100"), Decimal("3.200"), Decimal("3.000"), Decimal("3.150")
    )
    eligible = repo.list_eligible_daily_bar_rebuild_orders()
    assert eligible == []
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    assert repo.list_trades(account.id) == []
    engine.dispose()


def test_matching_fills_etf_order_from_raw_etf_daily_without_adjusted_fallback(tmp_path, monkeypatch):
    class MatchingToday(date):
        @classmethod
        def today(cls) -> Self:
            return cls(2026, 8, 7)

    monkeypatch.setattr(order_service_module, "date", MatchingToday)
    engine = create_engine(f"sqlite:///{tmp_path / 'raw-etf.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 8, 7)
    _add_supported_etf(repo, "518880")
    storage = FakeHistoryStorage(
        {},
        etf_daily_data={
            "518880": pd.DataFrame(
                {
                    COL_STOCK_ID: ["518880"],
                    COL_DATE: [trade_date.isoformat()],
                    COL_OPEN: [8.800],
                    COL_HIGH: [8.892],
                    COL_LOW: [8.774],
                    COL_CLOSE: [8.818],
                }
            )
        },
    )
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([trade_date]))
    order_service = OrderService(repo, market_data, etf_eligibility=ETFEligibilityService(repo))
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    account = repo.create_account("raw-etf-daily", Decimal("100000.00"))
    order = order_service.place_order(
        account.id,
        "518880",
        OrderSide.BUY,
        100,
        Decimal("8.818"),
        trade_date,
    )
    assert order.market == Market.ETF.value

    run = matching_service.run(trade_date, account.id)

    assert run.filled_count == 1
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert len(repo.list_trades(account.id)) == 1
    assert storage.etf_daily_calls
    assert storage.etf_calls == []
    assert storage.calls == []
    engine.dispose()


def test_matching_fills_buy_order_and_creates_lot(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    run = matching_service.run(trade_date)
    session.commit()

    filled = repo.get_order(order.id)
    lots = repo.get_lots(account.id, Market.A_SHARE, "000001.SZ")
    assert run.filled_count == 1
    assert filled.status == OrderStatus.FILLED.value
    assert filled.filled_quantity == 100
    assert repo.get_cash_available(account.id) == Decimal("98994.9900")
    assert lots[0].remaining_quantity == 100
    diagnostic = repo.list_daily_bar_diagnostics()[0]
    assert diagnostic.classification == "resolved"
    assert diagnostic.resolved is True
    engine.dispose()


def test_matching_snapshot_retry_resolves_gap_without_duplicate_fill(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("retry-gap", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    class MutableMarketData:
        available = False

        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            requested_date = trade_date
            if symbol == "300996" and not self.available:
                raise KeyError(f"No daily bar for {symbol} on {requested_date}")
            return DailyBar(symbol, requested_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("10"))

    market_data = MutableMarketData()
    matching_service.market_data = market_data
    matching_service.snapshot_service.market_data = market_data

    first_run = matching_service.run(trade_date)
    assert first_run.warning_count == 1
    assert repo.get_valuation_gap(account.id, trade_date).resolved is False
    assert repo.list_snapshots(account.id) == []
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    cash_after_fill = repo.get_cash_available(account.id)
    position_after_fill = repo.get_position(account.id, Market.A_SHARE, "000001.SZ").total_quantity

    market_data.available = True
    second_run = matching_service.run(trade_date)
    session.commit()

    assert second_run.filled_count == 0
    assert len(repo.list_trades(account.id)) == 1
    assert repo.get_cash_available(account.id) == cash_after_fill
    assert repo.get_position(account.id, Market.A_SHARE, "000001.SZ").total_quantity == position_after_fill
    assert len(repo.list_snapshots(account.id)) == 1
    gap = repo.get_valuation_gap(account.id, trade_date)
    assert gap is not None
    assert gap.resolved is True
    assert gap.missing_symbols == ["300996"]
    assert gap.details == [
        {"symbol": "300996", "market": "a_share", "error": "'No daily bar for 300996 on 2026-06-16'"}
    ]
    assert repo.list_snapshots(account.id)[0].market_value == Decimal("2000.0000")
    engine.dispose()


def test_matching_mixed_accounts_create_snapshot_and_valuation_gap(tmp_path):
    engine, session, repo, _, _, trade_date = _services(tmp_path)
    complete = repo.create_account("complete", Decimal("100000.00"))
    incomplete = repo.create_account("incomplete", Decimal("100000.00"))
    repo.upsert_position(complete.id, Market.A_SHARE, "000001.SZ", 100, 0, Decimal("900.00"))
    repo.upsert_position(incomplete.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class MixedMarketData:
        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            requested_date = trade_date
            if symbol == "300996":
                raise KeyError(f"No daily bar for {symbol} on {requested_date}")
            return DailyBar(symbol, requested_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("10"))

    market_data = MixedMarketData()
    service = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    run = service.run(trade_date)
    session.commit()

    assert run.warning_count == 1
    assert len(repo.list_snapshots(complete.id)) == 1
    assert repo.get_valuation_gap(complete.id, trade_date) is None
    gap = repo.get_valuation_gap(incomplete.id, trade_date)
    assert gap is not None
    assert gap.resolved is False
    assert gap.missing_symbols == ["300996"]
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
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 200, 0, Decimal("1800.00"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001.SZ", date(2026, 6, 15), 200, 200, Decimal("9.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("10.00"), trade_date)

    run = matching_service.run(trade_date)
    session.commit()

    position = repo.get_position(account.id, Market.A_SHARE, "000001.SZ")
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
    assert repo.get_position(account.id, Market.A_SHARE, "000001.SZ") is None
    assert repo.get_account(account.id).realized_pnl == Decimal("44.4600")
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
        (entry.event_type, entry.amount, entry.trade_id) for entry in repo.list_cash_ledger(account.id)
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
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 200, 0, Decimal("1800.00"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001.SZ", date(2026, 6, 15), 200, 200, Decimal("9.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.SELL, 100, Decimal("10.00"), trade_date)

    matching_service.run(trade_date)
    session.commit()

    trades = repo.list_trades(account.id)
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert trades[0].fees == Decimal("1.0000")
    assert repo.get_cash_available(account.id) == Decimal("100999.0000")
    engine.dispose()


def test_etf_sell_uses_only_overridden_commission(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("etf", Decimal("100000"), etf_commission_rate=Decimal("0.00008"))
    repo.upsert_position(account.id, Market.ETF, "510300", 100, 0, Decimal("900.00"))
    repo.create_position_lot(account.id, Market.ETF, "510300", date(2026, 6, 15), 100, 100, Decimal("9.00"))
    order = order_service.place_order(
        account.id,
        "510300",
        OrderSide.SELL,
        100,
        Decimal("10.00"),
        trade_date,
        market=Market.ETF,
    )

    matching_service.market_data = FakeMarketDataProvider(
        {
            ("510300", trade_date): DailyBar(
                "510300", trade_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10")
            )
        }
    )
    assert matching_service.match_order(order) == "filled"
    session.commit()

    trade = repo.list_trades(account.id)[0]
    assert trade.fees == Decimal("0.0800")
    assert repo.get_cash_available(account.id) == Decimal("100999.9200")
    assert repo.list_pending_settlements(account.id) == []
    engine.dispose()


def test_etf_zero_commission_rate_has_no_fill_fee(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("zero-etf-fee", Decimal("100000"), etf_commission_rate=Decimal("0"))
    order = order_service.place_order(
        account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        market=Market.ETF,
    )
    matching_service.market_data = FakeMarketDataProvider(
        {
            ("510300", trade_date): DailyBar(
                "510300", trade_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10")
            )
        }
    )

    assert matching_service.match_order(order) == "filled"
    session.commit()

    assert repo.list_trades(account.id)[0].fees == Decimal("0.0000")
    engine.dispose()


def test_matching_copies_order_comment_to_trade(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = order_service.place_order(
        account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"), trade_date, comment="突破买入"
    )

    matching_service.run(trade_date)
    session.commit()

    assert repo.get_order(order.id).comment == "突破买入"
    assert repo.list_trades(account.id)[0].comment == "突破买入"
    engine.dispose()


@pytest.mark.parametrize(
    "snapshot_exception",
    [
        KeyError("No daily bar for 00700 on 2026-06-16"),
        ValueError("Invalid OHLC for 00700 on 2026-06-16"),
    ],
)
def test_snapshot_market_data_failure_marks_run_failed_and_preserves_fill(tmp_path, snapshot_exception):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("market-data-failure", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    class FailingSnapshotService:
        def generate_snapshot_or_gap(self, account_id, snapshot_date):
            assert account_id == account.id
            assert snapshot_date == trade_date
            raise snapshot_exception

    matching_service.snapshot_service = FailingSnapshotService()
    run = matching_service.run(trade_date, account.id)
    session.commit()

    assert run.status == MatchingRunStatus.FAILED.value
    assert f"account={account.id}, trade_date={trade_date}" in run.error_details
    assert str(snapshot_exception) in run.error_details
    assert repo.list_snapshots(account.id) == []
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert len(repo.list_trades(account.id)) == 1
    engine.dispose()


def test_snapshot_failure_does_not_attempt_another_market(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("market-data-failure", Decimal("100000.00"))
    order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    calls = []

    class FailingSnapshotService:
        def generate_snapshot_or_gap(self, account_id, snapshot_date):
            raise KeyError("No daily bar for 00700")

    class CapturingMarketData:
        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            snapshot_date = trade_date
            calls.append((symbol, snapshot_date, market))
            return DailyBar(symbol, snapshot_date, Decimal("10"), Decimal("100"), Decimal("1"), Decimal("50"))

    matching_service.snapshot_service = FailingSnapshotService()
    matching_service.market_data = CapturingMarketData()
    matching_service.run(trade_date, account.id)

    assert calls == [("000001.SZ", trade_date, "a_share")]
    engine.dispose()


def test_non_market_data_snapshot_exception_still_raises(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("unexpected-failure", Decimal("100000.00"))
    order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    class FailingSnapshotService:
        def generate_snapshot_or_gap(self, account_id, snapshot_date):
            raise RuntimeError("database failure")

    matching_service.snapshot_service = FailingSnapshotService()
    with pytest.raises(RuntimeError, match="database failure"):
        matching_service.run(trade_date, account.id)
    engine.dispose()


def test_matching_mixed_exact_date_data_keeps_missing_order_accepted(tmp_path):
    engine, session, repo, order_service, _, trade_date = _services(tmp_path)
    account = repo.create_account("mixed-data", Decimal("100000.00"))
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "000002.SZ", "bfq", "missing_market_data", [], resolved=False
    )
    available = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    missing = order_service.place_order(account.id, "000002.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    bars = {
        ("000001.SZ", trade_date): DailyBar(
            "000001.SZ", trade_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10")
        )
    }

    class MixedMarketData:
        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            if (symbol, trade_date) not in bars:
                raise KeyError(f"No daily bar for {symbol} on {trade_date}")
            return bars[(symbol, trade_date)]

    matching_service = MatchingService(repo, MixedMarketData(), SnapshotService(repo, MixedMarketData()))
    run = matching_service.run(trade_date, account.id)
    session.commit()

    assert run.filled_count == 1
    assert run.warning_count == 1
    assert repo.get_order(available.id).status == OrderStatus.FILLED.value
    assert repo.get_order(missing.id).status == OrderStatus.ACCEPTED.value
    diagnostic = repo.list_daily_bar_diagnostics()
    assert any(item.stock_id == "000002" and item.resolved is False for item in diagnostic)
    engine.dispose()


def test_matching_order_processing_failure_marks_run_failed(tmp_path, monkeypatch):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("fatal-order", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    monkeypatch.setattr(
        matching_service,
        "_fill_order",
        lambda current_order: (_ for _ in ()).throw(RuntimeError("cash ledger unavailable")),
    )

    run = matching_service.run(trade_date, account.id)

    assert run.failed_count == 1
    assert run.status == MatchingRunStatus.FAILED.value
    assert f"order={order.id}" in run.error_details
    assert "cash ledger unavailable" in run.error_details
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()


def test_matching_order_persistence_failure_propagates(tmp_path, monkeypatch):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("persistence-failure", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    def fail_create_trade(*args, **kwargs):
        raise SQLAlchemyError("trade insert failed")

    monkeypatch.setattr(repo, "create_trade", fail_create_trade)

    with pytest.raises(SQLAlchemyError, match="trade insert failed"):
        matching_service.run(trade_date, account.id)

    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()


def test_match_order_missing_exact_date_records_warning_diagnostic(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("missing-bar", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    class MissingMarketData:
        def get_daily_bar(self, symbol, requested_date, market=None):
            raise KeyError(f"No daily bar for {symbol} on {requested_date}")

    matching_service.market_data = MissingMarketData()

    assert matching_service.match_order(order) == "warning"
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    diagnostic = next(item for item in repo.list_daily_bar_diagnostics() if item.stock_id == "000001")
    assert diagnostic.classification == "missing_exact_date"
    assert diagnostic.resolved is False
    engine.dispose()


def test_matching_etf_missing_bar_warns_then_same_date_retry_fills(tmp_path):
    engine, session, repo, order_service, _, trade_date = _services(tmp_path)
    account = repo.create_account("etf-retry", Decimal("100000.00"))
    order = order_service.place_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.100"), trade_date, market=Market.ETF
    )

    class RetryETFMarketData:
        available = False

        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            assert market == "etf"
            if not self.available:
                raise KeyError(f"No daily bar for {symbol} on {trade_date}")
            return DailyBar(symbol, trade_date, Decimal("3.100"), Decimal("3.200"), Decimal("3.000"), Decimal("3.100"))

    market_data = RetryETFMarketData()
    matching = MatchingService(repo, market_data, SnapshotService(repo, market_data))

    assert matching.match_order(order) == "warning"
    diagnostic = next(
        item for item in repo.list_daily_bar_diagnostics() if item.market == "etf" and item.stock_id == "510300"
    )
    assert (diagnostic.market, diagnostic.stock_id, diagnostic.classification) == (
        "etf",
        "510300",
        "missing_exact_date",
    )
    assert diagnostic.adjust.value == "raw"
    market_data.available = True
    assert matching.match_order(order) == "filled"
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    assert diagnostic.resolved is True
    engine.dispose()


@pytest.mark.parametrize(
    ("method_name", "error"),
    [
        ("_fill_order", SQLAlchemyError("trade insert failed")),
        ("_resolve_matching_diagnostic", SQLAlchemyError("diagnostic update failed")),
        ("_fill_order", RuntimeError("cash ledger unavailable")),
    ],
)
def test_match_order_propagates_sqlalchemy_errors_but_returns_failed_for_other_errors(
    tmp_path, monkeypatch, method_name, error
):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("match-order-errors", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    if method_name == "_resolve_matching_diagnostic":
        monkeypatch.setattr(matching_service, "_fill_order", lambda current_order: None)
    monkeypatch.setattr(
        matching_service,
        method_name,
        lambda current_order: (_ for _ in ()).throw(error),
    )

    if isinstance(error, SQLAlchemyError):
        with pytest.raises(SQLAlchemyError, match=str(error)):
            matching_service.match_order(order)
    else:
        assert matching_service.match_order(order) == "failed"
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    session.rollback()
    engine.dispose()


def test_matching_same_date_retry_fills_only_previously_accepted_order(tmp_path):
    engine, session, repo, order_service, _, trade_date = _services(tmp_path)
    account = repo.create_account("retry-data", Decimal("100000.00"))
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "000002.SZ", "bfq", "missing_market_data", [], resolved=False
    )
    available = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    missing = order_service.place_order(account.id, "000002.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    missing_bar: dict[str, object] = {}

    class RetryMarketData:
        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            requested_date = trade_date
            if symbol == "000001.SZ":
                return DailyBar(symbol, requested_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"))
            if not missing_bar:
                raise KeyError(f"No daily bar for {symbol} on {requested_date}")
            return cast(dict[tuple[str, date], DailyBar], missing_bar)[(symbol, requested_date)]

    market_data = RetryMarketData()
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    matching_service.run(trade_date, account.id)
    session.commit()
    cast(dict[tuple[str, date], DailyBar], missing_bar)[("000002.SZ", trade_date)] = DailyBar(
        "000002.SZ", trade_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10")
    )
    retry = matching_service.run(trade_date, account.id)
    session.commit()

    assert retry.filled_count == 1
    assert repo.get_order(available.id).status == OrderStatus.FILLED.value
    assert repo.get_order(missing.id).status == OrderStatus.FILLED.value
    assert len(repo.list_trades(account.id)) == 2
    engine.dispose()


def test_matching_fill_resolves_historical_retry_diagnostic(tmp_path):
    engine, session, repo, order_service, _, trade_date = _services(tmp_path)
    account = repo.create_account("historical-retry", Decimal("100000.00"))
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "000001.SZ", "bfq", "missing_exact_date", [], resolved=False
    )
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)

    class ExactDateMarketData:
        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            return DailyBar(symbol, trade_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"))

    market_data = ExactDateMarketData()
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    result = matching_service.match_order(order)
    session.commit()

    assert result == "filled"
    diagnostic = next(item for item in repo.list_daily_bar_diagnostics() if item.stock_id == "000001")
    assert diagnostic.resolved is True
    assert diagnostic.classification == "resolved"

    retry = order_service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
    )
    assert retry.status == OrderStatus.ACCEPTED.value
    assert retry.rejection_code is None
    engine.dispose()


def test_matching_hk_fill_does_not_resolve_historical_bfq_diagnostic(tmp_path):
    engine, session, repo, order_service, _, trade_date = _services(tmp_path)
    account = repo.create_account("hk-historical-retry", Decimal("100000.00"))
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.HK_CONNECT, "00700", "bfq", "missing_exact_date", [], resolved=False
    )
    order = order_service.place_order(
        account.id, "00700", OrderSide.BUY, 100, Decimal("400.00"), trade_date, market=Market.HK_CONNECT
    )

    class ExactDateMarketData:
        def is_trade_date(self, trade_date: date) -> bool:
            return True

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

        def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
            return None

        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            return DailyBar(symbol, trade_date, Decimal("400"), Decimal("410"), Decimal("390"), Decimal("400"))

    market_data = ExactDateMarketData()
    matching_service = MatchingService(repo, market_data, SnapshotService(repo, market_data))

    assert matching_service.match_order(order) == "filled"
    diagnostic = next(item for item in repo.list_daily_bar_diagnostics() if item.stock_id == "00700")
    assert diagnostic.resolved is False
    assert diagnostic.classification == "missing_exact_date"
    engine.dispose()


def test_matching_duplicate_active_run_returns_non_owner_without_double_fill(tmp_path):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("duplicate-run", Decimal("100000.00"))
    order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    first, owner = repo.acquire_matching_run(trade_date, account.id)
    second, second_owner = repo.acquire_matching_run(trade_date, account.id)

    assert owner is True
    assert second_owner is False
    assert second.id == first.id

    run = matching_service.run(trade_date, account.id)
    session.commit()
    assert run.id == first.id
    assert len(repo.list_trades(account.id)) == 0
    engine.dispose()


def test_account_scoped_matching_locks_account_before_processing(tmp_path, monkeypatch):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("account-lock", Decimal("100000.00"))
    locked_accounts: list[int] = []

    def lock_account(account_id: int):
        locked_accounts.append(account_id)
        return repo.get_account(account_id)

    monkeypatch.setattr(repo, "lock_account", lock_account)
    matching_service.run(trade_date, account.id)

    assert locked_accounts == [account.id]
    engine.dispose()


# ── HK Connect matching ──────────────────────────────────────────────────────


def test_hk_connect_matching_uses_hk_fees_and_persists_market(sqlite_session):
    """HK Connect matching should use HK fee calculation and persist market on trade."""
    from storage.model.general_info_ggt import GeneralInfoGGT
    from test.paper_trading.fakes import FakeMarketDataProvider

    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-match", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("50000.00"),
        market="hk_connect",
    )
    bars = {
        ("00700", date(2026, 7, 21)): DailyBar(
            symbol="00700",
            trade_date=date(2026, 7, 21),
            open=Decimal("400"),
            high=Decimal("410"),
            low=Decimal("395"),
            close=Decimal("405"),
        )
    }
    md = FakeMarketDataProvider(bars)
    snapshot_service = SnapshotService(repo, md)
    service = MatchingService(repo, md, snapshot_service)
    result = service.match_order(order)
    assert result == "filled", f"Expected filled, got {result}"
    trades = repo.list_trades(account.id)
    assert len(trades) == 1
    # HK fees should differ from A-share fees
    assert trades[0].fees != Decimal("0.00")
    assert trades[0].market == "hk_connect"
    # Position created by HK buy fill must also carry market
    positions = repo.get_positions(account.id)
    assert len(positions) == 1
    assert positions[0].market == "hk_connect"
    lots = repo.get_lots(account.id, Market.HK_CONNECT, "00700")
    assert len(lots) == 1
    assert lots[0].market == "hk_connect"


def test_hk_connect_matching_get_daily_bar_receives_market(sqlite_session):
    """HK Connect matching should pass market=order.market to get_daily_bar."""
    from storage.model.general_info_ggt import GeneralInfoGGT
    from test.paper_trading.fakes import FakeMarketDataProvider

    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-mkt", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("50000.00"),
        market="hk_connect",
    )

    class MarketCaptureProvider(FakeMarketDataProvider):
        def __init__(self):
            super().__init__()
            self.captured: list[str | None] = []

        def get_daily_bar(self, symbol, trade_date, market=None):
            self.captured.append(market)
            return DailyBar(
                symbol=symbol,
                trade_date=trade_date,
                open=Decimal("400"),
                high=Decimal("410"),
                low=Decimal("395"),
                close=Decimal("405"),
            )

    md = MarketCaptureProvider()
    snapshot_service = SnapshotService(repo, md)
    service = MatchingService(repo, md, snapshot_service)
    service.match_order(order)
    assert md.captured == ["hk_connect"]


def test_hk_connect_matching_sell_creates_pending_settlement(sqlite_session):
    """HK Connect sell should create pending settlement (T+2) instead of immediate cash credit."""
    from storage.model.general_info_ggt import GeneralInfoGGT
    from test.paper_trading.fakes import FakeMarketDataProvider

    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-sell", Decimal("0.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    repo.upsert_position(account.id, Market.HK_CONNECT, "00700", 100, 0, Decimal("30000.00"))
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.SELL,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        frozen_quantity=100,
        market="hk_connect",
    )
    bars = {
        ("00700", date(2026, 7, 21)): DailyBar(
            symbol="00700",
            trade_date=date(2026, 7, 21),
            open=Decimal("400"),
            high=Decimal("410"),
            low=Decimal("395"),
            close=Decimal("405"),
        )
    }
    md = FakeMarketDataProvider(bars)
    snapshot_service = SnapshotService(repo, md)
    service = MatchingService(repo, md, snapshot_service)
    result = service.match_order(order)
    assert result == "filled", f"Expected filled, got {result}"
    pending = repo.list_pending_settlements(account.id)
    assert len(pending) == 1
    assert pending[0].settled is False
    # Cash should NOT be immediately available for HK sell
    assert repo.get_cash_available(account.id) == Decimal("0.0000")


def test_hk_connect_matching_buy_does_not_create_pending_settlement(sqlite_session):
    """HK Connect buy should NOT create pending settlement."""
    from storage.model.general_info_ggt import GeneralInfoGGT
    from test.paper_trading.fakes import FakeMarketDataProvider

    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("hk-buy-ns", Decimal("500000.00"))
    session = sqlite_session
    session.add(GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"))
    session.flush()
    order = repo.create_order(
        account_id=account.id,
        symbol="00700",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("400.00"),
        trade_date=date(2026, 7, 21),
        status=OrderStatus.ACCEPTED,
        frozen_cash=Decimal("50000.00"),
        market="hk_connect",
    )
    bars = {
        ("00700", date(2026, 7, 21)): DailyBar(
            symbol="00700",
            trade_date=date(2026, 7, 21),
            open=Decimal("400"),
            high=Decimal("410"),
            low=Decimal("395"),
            close=Decimal("405"),
        )
    }
    md = FakeMarketDataProvider(bars)
    snapshot_service = SnapshotService(repo, md)
    service = MatchingService(repo, md, snapshot_service)
    service.match_order(order)
    pending = repo.list_pending_settlements(account.id)
    assert len(pending) == 0


def test_matching_same_symbol_isolates_fills_lots_pnl_and_diagnostics(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("market-matching", Decimal("100000.00"))
    trade_date = date(2026, 7, 21)
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 100, Decimal("900.00"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 7, 20), 100, 100, Decimal("9.00"))
    repo.upsert_position(account.id, Market.HK_CONNECT, "000001", 200, 0, Decimal("1600.00"))
    repo.create_position_lot(account.id, Market.HK_CONNECT, "000001", date(2026, 7, 20), 200, 200, Decimal("8.00"))
    a_share_order = repo.create_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_quantity=100,
        market=Market.A_SHARE.value,
    )
    hk_order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        market=Market.HK_CONNECT.value,
    )

    class MarketSeparatedBars(FakeMarketDataProvider):
        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None):
            if market == Market.HK_CONNECT.value:
                raise KeyError("HK bar unavailable")
            return DailyBar(symbol, trade_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"))

        def next_trade_date(self, trade_date: date) -> date:
            return trade_date

    market_data = MarketSeparatedBars()
    service = MatchingService(repo, market_data, SnapshotService(repo, market_data))

    assert service.match_order(a_share_order) == "filled"
    assert service.match_order(hk_order) == "warning"
    assert repo.get_position(account.id, Market.A_SHARE, "000001") is None
    hk_connect_position = repo.get_position(account.id, Market.HK_CONNECT, "000001")
    assert hk_connect_position is not None
    assert hk_connect_position.total_quantity == 200
    assert repo.get_lots(account.id, Market.HK_CONNECT, "000001")[0].remaining_quantity == 200
    reloaded_account = repo.get_account(account.id)
    assert reloaded_account is not None
    assert reloaded_account.realized_pnl == Decimal("94.4900")
    diagnostics = repo.list_daily_bar_diagnostics()
    assert [(item.market, item.stock_id, item.resolved) for item in diagnostics] == [("hk_connect", "000001", False)]
