from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Self

import pytest

import paper_trading.services.order_service as order_service_module
from paper_trading.domain.enums import (
    REPLAY_REJECTION_MARKER,
    CashEventType,
    Market,
    MatchingRunStatus,
    OrderSide,
    OrderStatus,
    PaperOrderEventType,
    SnapshotPointType,
)
from paper_trading.schemas.analytics import AnalyticsResponse
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.nav_series import NavSeriesBuilder
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.services.order_service import OrderService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import PaperOrderEvent
from paper_trading.storage.repository import PaperTradingRepository, canonical_trading_snapshot_event_at
from storage.model.base import Base
from storage.model.general_info_ggt import GeneralInfoGGT
from test.paper_trading.fakes import FakeMarketDataProvider


class _TestDate(date):
    @classmethod
    def today(cls) -> Self:
        return cls(2026, 7, 17)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(order_service_module, "date", _TestDate)


@pytest.fixture(autouse=True)
def seed_historical_a_share_diagnostics(session):
    """Seed diagnostics needed by delayed-data replay scenarios."""
    repo = PaperTradingRepository(session)
    symbols = ("000001", "000002", "000003", "999999")
    trade_dates = tuple(date(2026, 7, day) for day in (15, 16, 17, 18, 19, 21, 22))
    for trade_date in trade_dates:
        for symbol in symbols:
            repo.upsert_daily_bar_diagnostic(
                trade_date,
                Market.A_SHARE,
                symbol,
                "bfq",
                "missing_market_data",
                [],
                resolved=False,
            )


def test_delete_missing_order_returns_false(session):
    repo = PaperTradingRepository(session)
    service = OrderDeleteService(repo, FakeMarketDataProvider())

    assert service.delete_order(999999) is False


def test_delete_filled_order_rebuilds_account_from_remaining_orders(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))
    first = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    second = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("2005.0000"),
    )
    snapshot_service = SnapshotService(repo, market_data)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 17), account.id)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 18), account.id)
    assert len(repo.list_trades(account.id)) == 2

    deleted = OrderDeleteService(repo, market_data).delete_order(first.id)

    assert deleted is True
    with pytest.raises(KeyError):
        repo.get_order(first.id)
    remaining_orders = repo.list_orders(account.id)
    assert [order.id for order in remaining_orders] == [second.id]
    trades = repo.list_trades(account.id)
    assert len(trades) == 1
    assert trades[0].order_id == second.id
    positions = repo.get_positions(account.id)
    assert [(position.symbol, int(position.total_quantity)) for position in positions] == [("000002", 100)]
    snapshots = repo.list_snapshots(account.id)
    assert len(snapshots) == 2
    assert sum(snapshot.point_type == SnapshotPointType.INITIAL.value for snapshot in snapshots) == 1
    trading_snapshots = [
        snapshot for snapshot in snapshots if snapshot.point_type == SnapshotPointType.TRADING.value
    ]
    assert len(trading_snapshots) == 1
    trading_snapshot = next(
        snapshot
        for snapshot in snapshots
        if snapshot.point_type == SnapshotPointType.TRADING.value and snapshot.trade_date == date(2026, 7, 18)
    )
    assert trading_snapshot.trade_date == date(2026, 7, 18)
    ledger = repo.list_cash_ledger(account.id)
    assert ledger[0].note == "initial_cash"
    assert repo.get_cash_available(account.id) < Decimal("100000")


def test_delete_filled_order_records_valuation_gap_when_replay_cannot_value_position(session):
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 7, 18)
    account = repo.create_account("replay-valuation-gap", Decimal("100000"))
    deleted = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    surviving = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("2005.0000"),
    )
    market_data = FakeMarketDataProvider()
    MatchingService(repo, market_data, SnapshotService(repo, market_data)).run(trade_date, account.id)

    class MissingSurvivingValuation(FakeMarketDataProvider):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def get_daily_bar(self, symbol, trade_date, market=None):
            if symbol == "000002":
                self.calls += 1
                if self.calls > 1:
                    raise KeyError(f"No daily bar for {symbol} on {trade_date}")
            return super().get_daily_bar(symbol, trade_date, market)

    assert OrderDeleteService(repo, MissingSurvivingValuation()).delete_order(deleted.id) is True

    assert [trade.order_id for trade in repo.list_trades(account.id)] == [surviving.id]
    assert all(
        snapshot.trade_date != trade_date or snapshot.point_type != SnapshotPointType.TRADING.value
        for snapshot in repo.list_snapshots(account.id)
    )
    gap = repo.get_valuation_gap(account.id, trade_date)
    assert gap is not None
    assert gap.missing_symbols == ["000002"]
    assert gap.details == [
        {
            "symbol": "000002",
            "market": "a_share",
            "requested_date": "2026-07-18",
            "source_date": None,
            "reason": "missing_exact_bar",
        }
    ]
    runs = repo.list_matching_runs()
    assert len(runs) == 1
    assert runs[0].status == MatchingRunStatus.COMPLETED_WITH_WARNINGS.value
    assert runs[0].warning_count == 1


def test_rebuild_from_creation_date_preserves_initial_snapshot(session):
    repo = PaperTradingRepository(session)
    account = repo.create_account("preserve-initial", Decimal("100000"))

    repo.clear_account_rebuild_state_from(account.id, account.created_at.date())

    assert [point.point_type for point in repo.list_snapshots(account.id)] == [SnapshotPointType.INITIAL.value]


def test_delete_order_preserves_initial_snapshot_and_regenerates_trading_points(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("delete-preserves-initial", Decimal("100000"))
    initial = next(
        point for point in repo.list_snapshots(account.id) if point.point_type == SnapshotPointType.INITIAL.value
    )
    first = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("2005.0000"),
    )
    snapshot_service = SnapshotService(repo, market_data)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 17), account.id)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 18), account.id)

    deleted = OrderDeleteService(repo, market_data).delete_order(first.id)

    assert deleted is True
    snapshots = repo.list_snapshots(account.id)
    assert len(snapshots) == 2
    assert sum(point.point_type == SnapshotPointType.INITIAL.value for point in snapshots) == 1
    assert sum(
        point.point_type == SnapshotPointType.TRADING.value and point.trade_date == date(2026, 7, 18)
        for point in snapshots
    ) == 1
    initial_snapshot = next(point for point in snapshots if point.point_type == SnapshotPointType.INITIAL.value)
    trading_snapshot = next(
        point
        for point in snapshots
        if point.point_type == SnapshotPointType.TRADING.value and point.trade_date == date(2026, 7, 18)
    )
    assert initial_snapshot.id == initial.id
    assert trading_snapshot.trade_date == date(2026, 7, 18)


def test_rebuild_from_creation_date_regenerates_same_day_trading_points(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("same-day-rebuild", Decimal("100000"))
    created_date = account.created_at.date()
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        created_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    MatchingService(repo, market_data, SnapshotService(repo, market_data)).run(created_date, account.id)
    before = repo.list_snapshots(account.id)
    assert len(before) == 2
    assert sum(point.point_type == SnapshotPointType.INITIAL.value for point in before) == 1
    original_trading_event_at = next(
        point.event_at
        for point in before
        if point.point_type == SnapshotPointType.TRADING.value and point.trade_date == created_date
    )

    rebuild = OrderDeleteService(repo, market_data).rebuild_account_from(account.id, created_date, [order.id])

    after = repo.list_snapshots(account.id)
    assert len(after) == 2
    assert sum(point.point_type == SnapshotPointType.INITIAL.value for point in after) == 1
    initial_after = next(point for point in after if point.point_type == SnapshotPointType.INITIAL.value)
    assert initial_after.id == next(point for point in before if point.point_type == SnapshotPointType.INITIAL.value).id
    assert rebuild.regenerated_counts["snapshots"] == 1
    rebuilt_trading_snapshot = next(
        point
        for point in after
        if point.point_type == SnapshotPointType.TRADING.value and point.trade_date == created_date
    )
    canonical_event_at = canonical_trading_snapshot_event_at(created_date)
    for event_at in (original_trading_event_at, rebuilt_trading_snapshot.event_at):
        if event_at.tzinfo is None:
            assert event_at == canonical_event_at.replace(tzinfo=None)
            actual_event_at = event_at.replace(tzinfo=timezone.utc)
        else:
            actual_event_at = event_at.astimezone(timezone.utc)
        assert actual_event_at == canonical_event_at


def test_rebuild_from_fills_delayed_order_and_replays_later_ledger(session):
    repo = PaperTradingRepository(session)
    early_date = date(2026, 7, 17)
    later_date = date(2026, 7, 18)
    account = repo.create_account("delayed-history", Decimal("100000"))
    early_order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        early_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    later_order = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        later_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("2005.0000"),
    )
    market_data = FakeMarketDataProvider()
    matching = MatchingService(repo, market_data, SnapshotService(repo, market_data))
    matching.run(later_date, account.id)
    repo.upsert_daily_bar_diagnostic(
        early_date, Market.A_SHARE, "000001", "bfq", "missing_exact_date", [], resolved=False
    )

    rebuild = OrderDeleteService(repo, market_data).rebuild_account_from(account.id, early_date, [early_order.id])

    assert repo.get_order(early_order.id).status == OrderStatus.FILLED.value
    assert repo.get_order(later_order.id).status == OrderStatus.FILLED.value
    assert [trade.order_id for trade in repo.list_trades(account.id)] == [early_order.id, later_order.id]
    assert rebuild.start_date == early_date


def test_historical_rebuild_regenerates_buy_freezes_before_replayed_trades_and_analytics(session):
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 7, 17)
    account = repo.create_account("rebuild-buy-freeze-replay", Decimal("100000"))
    first_order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0100"),
    )
    second_order = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("2005.0200"),
    )
    reservation_times = {
        order.id: next(
            event.event_at
            for event in repo.list_effective_order_events(account.id, order.id)
            if event.event_type == PaperOrderEventType.RESERVED.value
        )
        for order in (first_order, second_order)
    }

    OrderDeleteService(repo, FakeMarketDataProvider()).rebuild_account_from(
        account.id, trade_date, [first_order.id, second_order.id]
    )

    freezes = {
        event.order_id: event
        for event in repo.list_cash_ledger(account.id)
        if event.event_type == CashEventType.FREEZE.value
    }
    trades = {trade.order_id: trade for trade in repo.list_trades(account.id)}
    assert set(freezes) == {first_order.id, second_order.id}
    assert [freezes[order_id].amount for order_id in (first_order.id, second_order.id)] == [
        Decimal("-1005.0100"),
        Decimal("-2005.0200"),
    ]

    def normalize_utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    for order_id in freezes:
        assert order_id is not None
        assert normalize_utc(freezes[order_id].occurred_at) == normalize_utc(reservation_times[order_id])
        assert normalize_utc(freezes[order_id].occurred_at) < normalize_utc(trades[order_id].trade_time)
    NavSeriesBuilder(repo).build(account.id)
    assert isinstance(AnalyticsService(repo).get_account_analytics(account.id), AnalyticsResponse)


def test_historical_rebuild_replays_legacy_filled_order_without_reserved_event(session):
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 7, 17)
    account = repo.create_account("rebuild-legacy-no-reservation", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0100"),
    )
    matching = MatchingService(repo, FakeMarketDataProvider(), SnapshotService(repo, FakeMarketDataProvider()))
    assert matching.match_order(order) == "filled"
    accepted_at = next(
        event.event_at
        for event in repo.list_effective_order_events(account.id, order.id)
        if event.event_type == PaperOrderEventType.ACCEPTED.value
    )
    repo.session.query(PaperOrderEvent).filter(
        PaperOrderEvent.account_id == account.id,
        PaperOrderEvent.order_id == order.id,
        PaperOrderEvent.event_type == PaperOrderEventType.RESERVED.value,
    ).delete(synchronize_session=False)
    repo.session.flush()
    assert [event.event_type for event in repo.list_effective_order_events(account.id, order.id)] == [
        PaperOrderEventType.ACCEPTED.value,
        PaperOrderEventType.FILL.value,
        PaperOrderEventType.RELEASE.value,
    ]

    OrderDeleteService(repo, FakeMarketDataProvider()).rebuild_account_from(account.id, trade_date, [order.id])

    freeze = next(
        event for event in repo.list_cash_ledger(account.id) if event.event_type == CashEventType.FREEZE.value
    )
    trade = repo.list_trades(account.id)[0]
    assert freeze.amount == Decimal("-1005.0100")
    assert freeze.occurred_at.replace(tzinfo=timezone.utc) == accepted_at.replace(tzinfo=timezone.utc)
    assert freeze.occurred_at.replace(tzinfo=timezone.utc) < trade.trade_time.replace(tzinfo=timezone.utc)
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
    NavSeriesBuilder(repo).build(account.id)
    assert isinstance(AnalyticsService(repo).get_account_analytics(account.id), AnalyticsResponse)


def test_rebuild_locks_account_before_clearing_derived_state(session, monkeypatch):
    repo = PaperTradingRepository(session)
    account = repo.create_account("rebuild-lock", Decimal("100000"))
    calls: list[str] = []
    original_lock = repo.lock_account
    original_clear_from = repo.clear_account_rebuild_state_from

    def lock_account(account_id: int):
        calls.append("lock")
        return original_lock(account_id)

    def clear_account_rebuild_state_from(account_id: int, start_date: date):
        calls.append("clear")
        return original_clear_from(account_id, start_date)

    monkeypatch.setattr(repo, "lock_account", lock_account)
    monkeypatch.setattr(repo, "clear_account_rebuild_state_from", clear_account_rebuild_state_from)

    OrderDeleteService(repo, FakeMarketDataProvider()).rebuild_account_from(account.id, date(2026, 7, 17), [])

    assert calls[:2] == ["lock", "clear"]


def test_rebuild_from_preserves_deposit_and_resolves_readable_skipped_diagnostic(session):
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 7, 17)
    account = repo.create_account("rebuild-source-facts", Decimal("100000"))
    repo.add_cash_event(account.id, CashEventType.DEPOSIT, Decimal("1000"), trade_date=trade_date, note="manual")
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("200.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("20005.0000"),
    )
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "000001", "bfq", "missing_exact_date", [], resolved=False
    )

    rebuild = OrderDeleteService(repo, FakeMarketDataProvider()).rebuild_account_from(
        account.id, trade_date, [order.id]
    )

    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    assert any(event.note == "manual" for event in repo.list_cash_ledger(account.id))
    diagnostic = next(
        item
        for item in repo.list_daily_bar_diagnostics()
        if item.stock_id == "000001" and item.business_date == trade_date
    )
    assert diagnostic.resolved is True
    assert rebuild.regenerated_counts["trades"] == 0


def test_rebuild_from_rolls_back_derived_ledger_on_unexpected_error(session, monkeypatch):
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 7, 17)
    account = repo.create_account("rebuild-rollback", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    market_data = FakeMarketDataProvider()
    MatchingService(repo, market_data, SnapshotService(repo, market_data)).run(trade_date, account.id)
    before_trade_ids = [trade.id for trade in repo.list_trades(account.id)]

    def raise_unexpected(*args, **kwargs):
        raise RuntimeError("unexpected replay failure")

    monkeypatch.setattr(MatchingService, "match_order", raise_unexpected)

    with pytest.raises(RuntimeError, match="unexpected replay failure"):
        OrderDeleteService(repo, FakeMarketDataProvider()).rebuild_account_from(account.id, trade_date, [order.id])

    assert [trade.id for trade in repo.list_trades(account.id)] == before_trade_ids
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value


def test_repeated_rebuild_preserves_source_facts_and_current_derived_counts(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("rebuild-idempotent", Decimal("100000"))
    trade_date = date(2026, 7, 17)
    later_date = date(2026, 7, 18)
    repo.add_cash_event(account.id, CashEventType.DEPOSIT, Decimal("1000"), trade_date=trade_date, note="manual")
    buy = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
        comment="keep this comment",
    )
    sell = repo.create_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("11.00"),
        later_date,
        OrderStatus.ACCEPTED,
        frozen_quantity=100,
    )
    cancelled = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        later_date,
        OrderStatus.CANCELLED,
        comment="cancelled source order",
    )

    service = OrderDeleteService(repo, market_data)
    service.rebuild_account_from(account.id, trade_date, [buy.id, sell.id])
    first_counts = {
        "trades": len(repo.list_trades(account.id)),
        "lots": repo.count_position_lots(account.id),
        "round_trips": len(repo.list_round_trips(account.id)),
        "snapshots": len(repo.list_snapshots(account.id)),
        "cash_by_order": sorted(
            (event.order_id, event.event_type, event.amount)
            for event in repo.list_cash_ledger(account.id)
            if event.order_id
        ),
    }

    service.rebuild_account_from(account.id, trade_date, [buy.id, sell.id])
    second_counts = {
        "trades": len(repo.list_trades(account.id)),
        "lots": repo.count_position_lots(account.id),
        "round_trips": len(repo.list_round_trips(account.id)),
        "snapshots": len(repo.list_snapshots(account.id)),
        "cash_by_order": sorted(
            (event.order_id, event.event_type, event.amount)
            for event in repo.list_cash_ledger(account.id)
            if event.order_id
        ),
    }

    assert first_counts == second_counts
    assert repo.get_order(buy.id).comment == "keep this comment"
    assert repo.get_order(sell.id).status == OrderStatus.FILLED.value
    assert repo.get_order(cancelled.id).status == OrderStatus.CANCELLED.value
    assert [event.note for event in repo.list_cash_ledger(account.id)].count("manual") == 1


def _seed_partially_filled_buy(repo, account_id, trade_date):
    order = repo.create_order(
        account_id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0100"),
    )
    repo.append_order_event(
        account_id,
        order.id,
        Market.A_SHARE,
        order.symbol,
        PaperOrderEventType.FILL,
        datetime.now(timezone.utc),
        quantity_delta=Decimal("-40"),
        cash_delta=Decimal("405.0100"),
        idempotency_key=f"order:{order.id}:partial-fill",
    )
    order.status = OrderStatus.PARTIALLY_FILLED.value
    order.filled_quantity = 40
    repo.session.flush()
    return order


def test_rebuild_replays_only_partially_filled_buy_remainder(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("partial-rebuild-fill", Decimal("100000"))
    trade_date = date(2026, 7, 17)
    order = _seed_partially_filled_buy(repo, account.id, trade_date)

    OrderDeleteService(repo, market_data).rebuild_account_from(account.id, trade_date, [order.id])

    rebuilt = repo.get_order(order.id)
    trades = repo.list_trades(account.id)
    position = repo.get_position(account.id, Market.A_SHARE, order.symbol)
    assert rebuilt.status == OrderStatus.FILLED.value
    assert rebuilt.filled_quantity == 100
    assert [trade.quantity for trade in trades] == [60]
    assert position is not None
    assert position.total_quantity == 60
    assert sum(event.cash_delta for event in repo.list_effective_order_events(account.id, order.id)) == Decimal("0")


def test_rebuild_then_cancel_releases_only_partially_filled_buy_remainder(session):
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 7, 17)
    account = repo.create_account("partial-rebuild-cancel", Decimal("100000"))
    order = _seed_partially_filled_buy(repo, account.id, trade_date)
    market_data = FakeMarketDataProvider(
        {
            (order.symbol, trade_date): DailyBar(
                symbol=order.symbol,
                trade_date=trade_date,
                open=Decimal("10"),
                high=Decimal("9"),
                low=Decimal("1"),
                close=Decimal("5"),
            )
        }
    )

    OrderDeleteService(repo, market_data).rebuild_account_from(account.id, trade_date, [order.id])
    OrderService(repo, market_data).cancel_order(order.id)

    rebuilt = repo.get_order(order.id)
    events = repo.list_effective_order_events(account.id, order.id)
    assert rebuilt.status == OrderStatus.CANCELLED.value
    assert rebuilt.filled_quantity == 40
    assert sum(event.quantity_delta for event in events) == Decimal("0")
    assert sum(event.cash_delta for event in events) == Decimal("0")
    release = events[-1]
    assert release.event_type == PaperOrderEventType.RELEASE.value
    assert release.cash_delta == Decimal("600.000000000000")


def test_rebuild_then_reject_releases_only_partially_filled_buy_remainder(session):
    repo = PaperTradingRepository(session)
    trade_date = date(2026, 7, 17)
    account = repo.create_account("partial-rebuild-reject", Decimal("100000"))
    order = _seed_partially_filled_buy(repo, account.id, trade_date)
    market_data = FakeMarketDataProvider(
        {
            (order.symbol, trade_date): DailyBar(
                symbol=order.symbol,
                trade_date=trade_date,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                suspended=True,
            )
        }
    )

    OrderDeleteService(repo, market_data).rebuild_account_from(account.id, trade_date, [order.id])

    rebuilt = repo.get_order(order.id)
    events = repo.list_effective_order_events(account.id, order.id)
    assert rebuilt.status == OrderStatus.REJECTED.value
    assert rebuilt.filled_quantity == 40
    assert sum(event.quantity_delta for event in events) == Decimal("0")
    assert sum(event.cash_delta for event in events) == Decimal("0")
    release = events[-1]
    assert release.event_type == PaperOrderEventType.RELEASE.value
    assert release.cash_delta == Decimal("600.000000000000")


def test_repeated_partial_fill_rebuild_does_not_accumulate_regenerated_fills(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("repeated-partial-rebuild", Decimal("100000"))
    trade_date = date(2026, 7, 17)
    order = _seed_partially_filled_buy(repo, account.id, trade_date)

    rebuild_service = OrderDeleteService(repo, market_data)
    rebuild_service.rebuild_account_from(account.id, trade_date, [order.id])
    first_rebuild = repo.get_order(order.id)
    assert first_rebuild.filled_quantity == 100
    assert [trade.quantity for trade in repo.list_trades(account.id)] == [60]
    assert repo.cumulative_order_filled_quantity(account.id, order.id) == 40

    rebuild_service.rebuild_account_from(account.id, trade_date, [order.id])

    rebuilt = repo.get_order(order.id)
    assert repo.cumulative_order_filled_quantity(account.id, order.id) == 40
    assert rebuilt.filled_quantity == 100
    assert [trade.quantity for trade in repo.list_trades(account.id)] == [60]


@pytest.mark.parametrize("terminal_event", [PaperOrderEventType.CANCEL, PaperOrderEventType.REJECT])
def test_repeated_partial_fill_rebuild_then_terminal_keeps_original_fill_count(session, terminal_event):
    repo = PaperTradingRepository(session)
    account = repo.create_account("repeated-partial-terminal", Decimal("100000"))
    trade_date = date(2026, 7, 17)
    order = _seed_partially_filled_buy(repo, account.id, trade_date)
    market_data = FakeMarketDataProvider()
    rebuild_service = OrderDeleteService(repo, market_data)

    rebuild_service.rebuild_account_from(account.id, trade_date, [order.id])
    repo.reset_orders_for_replay(account.id)
    repo.start_order_replay_lifecycle(repo.get_order(order.id))
    order = repo.get_order(order.id)
    order.status = OrderStatus.ACCEPTED.value
    repo.session.flush()

    if terminal_event == PaperOrderEventType.CANCEL:
        OrderService(repo, market_data).cancel_order(order.id)
    else:
        MatchingService(repo, market_data, SnapshotService(repo, market_data))._reject_order(
            order, "SUSPENDED_SYMBOL", "Symbol is suspended"
        )

    terminal = repo.get_order(order.id)
    effective_events = repo.list_effective_order_events(account.id, order.id)
    assert terminal.filled_quantity == 40
    assert sum(event.quantity_delta for event in effective_events) == Decimal("0")
    assert sum(event.cash_delta for event in effective_events) == Decimal("0")
    assert [trade.quantity for trade in repo.list_trades(account.id)] == [60]
    fill_events = [
        event
        for event in repo.list_order_events(account.id, order.id)
        if event.event_type == PaperOrderEventType.FILL.value
    ]
    assert len(fill_events) == 2


def test_rebuild_isolates_missing_untouched_and_suspended_orders(session):
    repo = PaperTradingRepository(session)
    missing_date = date(2026, 7, 17)
    later_date = date(2026, 7, 18)
    account = repo.create_account("rebuild-outcomes", Decimal("100000"))
    orders = [
        repo.create_order(
            account.id,
            "000001",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            missing_date,
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("1005.0000"),
        ),
        repo.create_order(
            account.id,
            "000002",
            OrderSide.BUY,
            100,
            Decimal("20.00"),
            missing_date,
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("2005.0000"),
        ),
        repo.create_order(
            account.id,
            "000003",
            OrderSide.BUY,
            100,
            Decimal("30.00"),
            missing_date,
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("3005.0000"),
        ),
        repo.create_order(
            account.id,
            "000004",
            OrderSide.BUY,
            100,
            Decimal("40.00"),
            later_date,
            OrderStatus.ACCEPTED,
            frozen_cash=Decimal("4005.0000"),
        ),
    ]

    class IsolatedOutcomeMarketData(FakeMarketDataProvider):
        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            if symbol == "000001":
                raise KeyError("missing exact-date bar")
            if symbol == "000002":
                return DailyBar(symbol, trade_date, Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"))
            if symbol == "000003":
                return DailyBar(
                    symbol,
                    trade_date,
                    Decimal("10"),
                    Decimal("100"),
                    Decimal("1"),
                    Decimal("10"),
                    suspended=True,
                )
            return super().get_daily_bar(symbol, trade_date, market)

    OrderDeleteService(repo, IsolatedOutcomeMarketData()).rebuild_account_from(
        account.id, missing_date, [order.id for order in orders]
    )

    assert repo.get_order(orders[0].id).status == OrderStatus.ACCEPTED.value
    assert repo.get_order(orders[1].id).status == OrderStatus.ACCEPTED.value
    assert repo.get_order(orders[2].id).rejection_code == "SUSPENDED_SYMBOL"
    assert repo.get_order(orders[3].id).status == OrderStatus.FILLED.value
    diagnostic = next(item for item in repo.list_daily_bar_diagnostics() if item.stock_id == "000001")
    assert diagnostic.resolved is False
    assert repo.list_snapshots(account.id)
    assert repo.get_valuation_gap(account.id, later_date) is None
    assert len(repo.list_trades(account.id)) == 1


# ── Bug reproduction: cash freeze / position freeze / validity checks ──────────


def test_delete_surviving_buy_has_correct_cash_available(session):
    """Surviving filled BUY order replayed after sibling-delete must have
    cash_available = initial_cash − actual_cost_of_surviving_order.

    Without the fix the cash FREEZE ledger event is not recreated before
    the replay MatchringService.run, so cash_available stays at initial_cash
    (the freeze is missing and release = frozen_cash − actual_cost = 0).
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place two BUY orders via OrderService so real freeze events are created.
    order1 = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order2 = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )

    # Fill both through matching.
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)

    # Confirm both had freeze events before delete.
    ledger_before = repo.list_cash_ledger(account.id)
    freeze_before = [e for e in ledger_before if e.event_type == CashEventType.FREEZE.value]
    assert len(freeze_before) == 2

    # Delete the first order.
    deleted = OrderDeleteService(repo, market_data).delete_order(order1.id)
    assert deleted is True

    # Correct cash = 100000 − frozen_cash(order2) = 100000 − 2005.02
    expected_cash = Decimal("97994.9800")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash_available={expected_cash}, got {actual_cash}"

    # The cash ledger must contain a FREEZE event for the surviving order.
    ledger = repo.list_cash_ledger(account.id)
    freeze_events = [e for e in ledger if e.event_type == CashEventType.FREEZE.value]
    assert len(freeze_events) == 1
    assert freeze_events[0].order_id == order2.id


def test_delete_surviving_sell_replay_not_negative_frozen_quantity(session):
    """Surviving filled SELL order replayed after sibling-delete must not
    produce a negative frozen_quantity on the position.

    The replay resets the SELL order to ACCEPTED with frozen_quantity intact,
    but positions are rebuilt from imported lots with frozen_quantity=0.
    Without the fix _settle_sell computes  0 − frozen_quantity < 0.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    # Seed an imported lot (durable baseline) for the sell symbol.
    repo.upsert_position(
        account.id,
        Market.A_SHARE,
        "000001",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("2000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        Market.A_SHARE,
        "000001",
        date(2026, 7, 15),
        200,
        200,
        Decimal("10.00"),
        source="imported",
    )

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place a SELL that will fill and a BUY that will be deleted.
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    buy_order = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )

    # Fill both.
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)

    # Delete the BUY — replay must process the surviving SELL.
    deleted = OrderDeleteService(repo, market_data).delete_order(buy_order.id)
    assert deleted is True

    # The imported-position replay must keep frozen_quantity non-negative.
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None
    assert position.frozen_quantity >= 0, f"Negative frozen_quantity: {position.frozen_quantity}"
    assert int(position.frozen_quantity) == 0, f"Expected frozen_quantity=0 after fill, got {position.frozen_quantity}"
    # 200 imported − 100 sold = 100 remaining
    assert int(position.total_quantity) == 100, f"Expected total_quantity=100, got {position.total_quantity}"


def test_delete_regenerates_validity_checks_for_surviving_orders(session):
    """After order-delete clears all PaperTradeValidityCheck rows and replays,
    surviving orders must have validity checks regenerated.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    order1 = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order2 = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )

    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)

    # Delete the first order — second survives.
    deleted = OrderDeleteService(repo, market_data).delete_order(order1.id)
    assert deleted is True

    # Surviving order must have at least one validity check re-generated.
    checks = repo.list_trade_validity_checks(order2.id)
    assert len(checks) > 0, f"Surviving order should have regenerated validity checks, got {len(checks)}"


def test_delete_surviving_buy_then_sell_same_symbol_preserves_position(session):
    """When a surviving BUY on T1 and surviving SELL on T2 share the same
    symbol, and both are replayed after a sibling-delete, the position must
    have non-negative frozen_quantity and correct total_quantity.

    The previous approach restored *all* reservations upfront, but the SELL
    freeze restore failed because the BUY-derived position did not yet exist
    (it was wiped by clear_account_rebuild_state).  The fix restores
    reservations per trade date, so the BUY replay creates the position
    before the SELL freeze is applied.

    Note: the sell order is placed *after* the buy matching run, because
    OrderService._accept_sell_order requires a non-zero position at the
    time the order is placed (real-world: the position could come from
    a prior day's fill or imported lots).
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Order 1: BUY 000001 on 7/17.
    buy = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    # Fill the buy first to create the position, so the sell can be placed.
    matching_service.run(date(2026, 7, 17), account.id)

    # Order 2: SELL 000001 on 7/18 (position now exists, T+1 satisfied because
    # the lot was created on 7/17 < 7/18).
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    # Order 3: unrelated BUY that will be deleted.
    delete_me = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 19),
    )

    # Fill remaining.
    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)

    # Confirm we have 3 trades before delete.
    all_trades = repo.list_trades(account.id)
    assert len(all_trades) == 3

    # Delete the unrelated BUY — must replay the buy + sell for 000001.
    deleted = OrderDeleteService(repo, market_data).delete_order(delete_me.id)
    assert deleted is True

    # Position for the buy/sell symbol must be correct.
    assert repo.get_position(account.id, Market.A_SHARE, "000001") is None
    persisted_account = repo.get_account(account.id)
    assert persisted_account is not None
    assert persisted_account.realized_pnl == Decimal("494.2300")

    # Trades for the buy+sell must survive.
    trades = repo.list_trades(account.id)
    surviving_symbols = [t.symbol for t in trades]
    assert surviving_symbols == ["000001", "000001"], f"Expected two trades for 000001, got {surviving_symbols}"

    # Cash must reflect buy cost and sell proceeds.
    # initial 100000 − buy_cost(1005.01) + sell_net(1494.23) = 100489.22
    expected_cash = Decimal("100489.2200")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"

    # Both surviving orders must have validity checks regenerated.
    for surviving_order in (buy, sell):
        checks = repo.list_trade_validity_checks(surviving_order.id)
        assert len(checks) > 0, f"Order {surviving_order.id} missing regenerated validity checks"


def test_delete_inventory_buy_rejects_surviving_sell_without_naked_trade(session):
    """When the BUY that provided inventory for a later SELL is deleted, the
    surviving SELL must be rejected during replay and must NOT produce a
    naked trade or cash event (MatchingService._settle_sell creates the cash
    TRADE event before returning early if position is None).
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # BUY that creates inventory for the SELL.
    buy = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    matching_service.run(date(2026, 7, 17), account.id)

    # SELL that consumes the BUY inventory.
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    # Unrelated surviving order so the account is non-empty after delete.
    order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 19),
    )

    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)

    assert len(repo.list_trades(account.id)) == 3

    # DELETE THE INVENTORY BUY — the SELL should now be rejected on replay.
    deleted = OrderDeleteService(repo, market_data).delete_order(buy.id)
    assert deleted is True

    # The sell must be rejected, not filled or accepted.
    sell_order = repo.get_order(sell.id)
    assert sell_order.status == OrderStatus.REJECTED.value, f"Expected REJECTED, got {sell_order.status}"

    # No trades for the sell symbol (no naked sell).
    trades = repo.list_trades(account.id)
    sell_trades = [t for t in trades if t.symbol == "000001"]
    assert len(sell_trades) == 0, f"Expected 0 sell trades for 000001, got {len(sell_trades)}"

    # No position for the sold symbol.
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is None or int(position.total_quantity) == 0

    # Cash must not include sell proceeds.
    # Only the surviving BUY 000002 freeze remains: 100000 − 2005.02 = 97994.98
    expected_cash = Decimal("97994.9800")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"


def test_delete_preserves_validity_checks_for_canceled_order(session):
    """Surviving canceled orders must have validity checks regenerated after
    delete+replay clears all PaperTradeValidityCheck rows.

    OrderService.place_order creates a validity check for accepted orders,
    and cancel_order changes the status to CANCELLED but does not remove
    the check.  After clear+replay the check must be recreated.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place an order and cancel it.
    order = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order_service.cancel_order(order.id)

    # Place an unrelated order that will be deleted.
    other = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )

    # Delete the unrelated order.
    deleted = OrderDeleteService(repo, market_data).delete_order(other.id)
    assert deleted is True

    # Canceled order must have validity checks regenerated.
    checks = repo.list_trade_validity_checks(order.id)
    assert len(checks) > 0, f"Canceled order should have regenerated validity checks, got {len(checks)}"

    # Order remains canceled.
    assert repo.get_order(order.id).status == OrderStatus.CANCELLED.value


def test_delete_over_reserved_same_date_sells_rejects_unsupported(session):
    """When multiple surviving SELL orders share the same trade date and
    symbol, and a deleted order removed part of the backing inventory,
    _restore_date_reservations must check *available* quantity
    (total − already-restored frozen), not total alone — otherwise the
    second SELL over-reserves and matching drives total_quantity negative.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── Baseline: imported lot (60 shares) ────────────────────────────────
    repo.upsert_position(
        account.id,
        Market.A_SHARE,
        "000001",
        total_quantity=60,
        frozen_quantity=0,
        cost_amount=Decimal("600.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        Market.A_SHARE,
        "000001",
        date(2026, 7, 14),
        60,
        60,
        Decimal("10.00"),
        source="imported",
    )

    # ── BUY-A (will be deleted): 100 shares @ 10, trade_date=7/15 ────────
    buy_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 15),
    )
    matching_service.run(date(2026, 7, 15), account.id)

    # ── BUY-B (survives): 100 shares @ 10, trade_date=7/16 ───────────────
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)

    # Position: 60 (imported) + 100 (BUY-A) + 100 (BUY-B) = 260
    pos = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert pos is not None
    assert int(pos.total_quantity) == 260

    # ── Two SELL orders, same date & symbol (100 each = 200, fits 260) ───
    sell_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    sell_b = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )

    matching_service.run(date(2026, 7, 18), account.id)

    # Both filled: position = 260 − 100 − 100 = 60
    pos = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert pos is not None
    assert int(pos.total_quantity) == 60
    assert len(repo.list_trades(account.id)) == 4  # 2 buys + 2 sells

    # ── DELETE BUY-A (removes 100 shares of inventory) ───────────────────
    deleted = OrderDeleteService(repo, market_data).delete_order(buy_a.id)
    assert deleted is True

    # After clear: imported lot (60) survives.  BUY-A and BUY-B lots
    # (source="trade") are deleted.  Position rebuilt: total=60, frozen=0.
    # Orders: BUY-B (ACCEPTED, 100@10), SELL A (100), SELL B (100).
    # Dates: [7/16, 7/18]

    # Verify final position is non-negative and correct.
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None
    assert int(position.frozen_quantity) >= 0, f"Negative frozen_quantity: {position.frozen_quantity}"
    # Position = 60 (imported) + 100 (BUY-B replay) − 100 (one sell) = 60
    expected_qty = 60
    assert int(position.total_quantity) == expected_qty, (
        f"Expected total_quantity={expected_qty}, got {position.total_quantity}"
    )

    # Only one sell should have been filled (insufficient inventory for both).
    sell_a_reloaded = repo.get_order(sell_a.id)
    sell_b_reloaded = repo.get_order(sell_b.id)
    sell_filled_ids = {o.id for o in (sell_a_reloaded, sell_b_reloaded) if o.status == OrderStatus.FILLED.value}
    sell_rejected_ids = {o.id for o in (sell_a_reloaded, sell_b_reloaded) if o.status == OrderStatus.REJECTED.value}
    assert len(sell_filled_ids) == 1, f"Expected exactly 1 sell FILLED, got {len(sell_filled_ids)}"
    assert len(sell_rejected_ids) == 1, f"Expected exactly 1 sell REJECTED, got {len(sell_rejected_ids)}"

    # Trades: only BUY-B fill + the one supported sell = 2 trades.
    trades = repo.list_trades(account.id)
    assert len(trades) == 2, f"Expected 2 trades (BUY-B + 1 sell), got {len(trades)}"

    # Cash must not include the unsupported sell proceeds.
    # initial 100000 − BUY-B frozen(1005.01) + supported sell net(1494.23)
    expected_cash = Decimal("100489.2200")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"


def test_delete_sell_funded_buy_rejects_when_cash_insufficient(session):
    """When a SELL that funded a later BUY is deleted, the BUY must be
    rejected during replay if the remaining cash cannot support its freeze.
    Otherwise the unconditional freeze drives cash_available negative.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Imported lot to back the sell.
    repo.upsert_position(
        account.id,
        Market.A_SHARE,
        "000001",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        Market.A_SHARE,
        "000001",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )

    # SELL that fills and creates proceeds (net = 1494.23).
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 17),
    )
    matching_service.run(date(2026, 7, 17), account.id)
    # Cash: 100000 + 1494.23 = 101494.23

    # BUY affordable only with sell proceeds (frozen_cash = 100031.00 > 100000).
    buy = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        1000,
        Decimal("100.00"),
        date(2026, 7, 18),
    )
    matching_service.run(date(2026, 7, 18), account.id)
    assert len(repo.list_trades(account.id)) == 2

    # Delete the SELL → BUY becomes unsupportable.
    deleted = OrderDeleteService(repo, market_data).delete_order(sell.id)
    assert deleted is True

    # BUY must be rejected, not filled.
    buy_order = repo.get_order(buy.id)
    assert buy_order.status == OrderStatus.REJECTED.value, f"Expected REJECTED, got {buy_order.status}"

    # Cash must not be negative.
    cash = repo.get_cash_available(account.id)
    assert cash >= 0, f"Negative cash: {cash}"
    assert cash == Decimal("100000.0000"), f"Expected cash=100000, got {cash}"

    # No trades at all (sell deleted, buy rejected).
    trades = repo.list_trades(account.id)
    assert len(trades) == 0, f"Expected 0 trades after sell delete+replay, got {len(trades)}"

    # No position for the buy symbol (never created).
    pos = repo.get_position(account.id, Market.A_SHARE, "000002")
    assert pos is None


def test_delete_same_date_sell_fills_before_buy_cash_check(session):
    """When a surviving lower-id SELL and higher-id BUY share the same trade
    date, the SELL must be restored/matched *before* the BUY's cash check,
    so the SELL's proceeds make the BUY affordable.

    Per-date reservation restore fails here because it checks cash for ALL
    same-date orders before any matching, so the BUY sees only initial cash
    (without SELL proceeds).  Per-order (trade_date, id) fixes this.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── Two imported lots ────────────────────────────────────────────────
    # 000001 (back the surviving sell)
    repo.upsert_position(
        account.id,
        Market.A_SHARE,
        "000001",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        Market.A_SHARE,
        "000001",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )
    # 999999 (back the prior sell that will be deleted)
    repo.upsert_position(
        account.id,
        Market.A_SHARE,
        "999999",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        Market.A_SHARE,
        "999999",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )

    # ── Prior SELL (provides cash for BUY, will be deleted) ──────────────
    prior_sell = order_service.place_order(
        account.id,
        "999999",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)
    # Cash: 100000 + 1494.23 = 101494.23

    # ── Surviving same-date orders ───────────────────────────────────────
    # SELL (lower ID): 000001, 100 @ 15, trade_date=7/18
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    # BUY (higher ID): 000002, 1000 @ 100, trade_date=7/18
    buy = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        1000,
        Decimal("100.00"),
        date(2026, 7, 18),
    )
    matching_service.run(date(2026, 7, 18), account.id)
    assert len(repo.list_trades(account.id)) == 3  # prior sell + same-date sell + buy

    # ── Delete the prior SELL → cash drops to 100000 ─────────────────────
    deleted = OrderDeleteService(repo, market_data).delete_order(prior_sell.id)
    assert deleted is True

    # Both surviving same-date orders must fill (SELL proceeds fund the BUY).
    sell_order = repo.get_order(sell.id)
    buy_order = repo.get_order(buy.id)
    assert sell_order.status == OrderStatus.FILLED.value, f"Expected SELL FILLED, got {sell_order.status}"
    assert buy_order.status == OrderStatus.FILLED.value, f"Expected BUY FILLED, got {buy_order.status}"

    # Cash = 100000 + 1494.23 - 100031.00 = 1463.23
    expected_cash = Decimal("1463.2300")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"

    # 2 trades (sell + buy), no trades for the deleted symbol.
    trades = repo.list_trades(account.id)
    assert len(trades) == 2, f"Expected 2 trades, got {len(trades)}"
    for t in trades:
        assert t.symbol in ("000001", "000002"), f"Unexpected trade symbol: {t.symbol}"

    # Position 000001 = 0 (sold), 000002 = 1000 (bought).
    pos1 = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert pos1 is None
    pos2 = repo.get_position(account.id, Market.A_SHARE, "000002")
    assert pos2 is not None and int(pos2.total_quantity) == 1000


def test_delete_snapshot_per_date_not_final_state(session):
    """Snapshots after delete+replay must reflect state at each trade date,
    not the final state after all dates have been replayed.

    Without per-date snapshot generation, an earlier-date snapshot would
    include positions/trades created by a later date's replay.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Order A (survives): BUY 000001 on 7/17 → position 000001 created.
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    # Order B (survives): BUY 000002 on 7/18 → position 000002 created.
    order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )
    # Order C (will be deleted): BUY 000003 on 7/19.
    order_c = order_service.place_order(
        account.id,
        "000003",
        OrderSide.BUY,
        100,
        Decimal("30.00"),
        date(2026, 7, 19),
    )

    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)
    assert len(repo.list_trades(account.id)) == 3

    # Delete order C → replay re-processes 7/17 and 7/18.
    deleted = OrderDeleteService(repo, market_data).delete_order(order_c.id)
    assert deleted is True

    snapshots = repo.list_snapshots(account.id)
    assert len(snapshots) == 3
    assert sum(snapshot.point_type == SnapshotPointType.INITIAL.value for snapshot in snapshots) == 1
    trading_snapshots = [
        snapshot for snapshot in snapshots if snapshot.point_type == SnapshotPointType.TRADING.value
    ]
    assert len(trading_snapshots) == 2
    assert {snapshot.trade_date for snapshot in trading_snapshots} == {
        date(2026, 7, 17),
        date(2026, 7, 18),
    }

    snap_17 = next(s for s in snapshots if s.trade_date == date(2026, 7, 17))
    snap_18 = next(s for s in snapshots if s.trade_date == date(2026, 7, 18))

    # 7/17 snapshot: only position 000001 exists (just bought this day).
    assert snap_17.position_count == 1, f"7/17 snapshot should have 1 position, got {snap_17.position_count}"
    # 7/18 snapshot: both positions exist (000001 from 7/17 + 000002 bought this day).
    assert snap_18.position_count == 2, f"7/18 snapshot should have 2 positions, got {snap_18.position_count}"


def test_delete_regenerates_matching_runs(session):
    """After delete+replay, PaperMatchingRun records must be recreated for
    all replayed trade dates with COMPLETED status.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Two surviving orders on different dates.
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )
    # One order to delete so replay is triggered.
    order_c = order_service.place_order(
        account.id,
        "000003",
        OrderSide.BUY,
        100,
        Decimal("30.00"),
        date(2026, 7, 19),
    )
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)
    assert len(repo.list_matching_runs()) == 3

    deleted = OrderDeleteService(repo, market_data).delete_order(order_c.id)
    assert deleted is True

    runs = repo.list_matching_runs()
    # Original runs deleted + 2 new ones (7/17 and 7/18).
    assert len(runs) == 2, f"Expected 2 matching runs, got {len(runs)}"
    for run in runs:
        assert run.status == MatchingRunStatus.COMPLETED.value, f"Expected COMPLETED, got {run.status}"


def test_match_order_unavailable_data_warns_not_rejects(session):
    """When an exact-date bar is unavailable, matching records a warning
    diagnostic and leaves the order accepted.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place an order via the normal provider.
    order = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )

    # Create a provider that raises KeyError.
    class UnavailableMarketData(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError(f"No data for {symbol}")

    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, UnavailableMarketData(), snapshot_service)

    outcome = matching_service.match_order(order)

    assert outcome == "warning", f"Expected 'warning', got {outcome!r}"
    # Order stays ACCEPTED, not rejected.
    assert order.status == OrderStatus.ACCEPTED.value, f"Expected ACCEPTED, got {order.status}"
    diagnostic = next(
        item
        for item in repo.list_daily_bar_diagnostics()
        if item.stock_id == "000001" and item.classification == "missing_exact_date"
    )
    assert diagnostic.classification == "missing_exact_date"
    assert diagnostic.resolved is False


def test_delete_replay_missing_bar_records_warning_run(session):
    repo = PaperTradingRepository(session)
    account = repo.create_account("replay-warning", Decimal("100000"))
    trade_date = date(2026, 7, 17)
    surviving = repo.create_order(
        account.id,
        "000004",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    deleted = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )

    class MissingSurvivingBar(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            if symbol == "000004":
                raise KeyError(f"No daily bar for {symbol}")
            return super().get_daily_bar(symbol, trade_date, market)

    assert OrderDeleteService(repo, MissingSurvivingBar()).delete_order(deleted.id) is True

    run = repo.list_matching_runs()[0]
    assert run.processed_count == 1
    assert run.warning_count == 1
    assert run.failed_count == 0
    assert run.status == MatchingRunStatus.COMPLETED_WITH_WARNINGS.value
    assert repo.get_order(surviving.id).status == OrderStatus.ACCEPTED.value
    diagnostic = next(item for item in repo.list_daily_bar_diagnostics() if item.stock_id == "000004")
    assert diagnostic.classification == "missing_exact_date"
    assert diagnostic.resolved is False


def test_delete_same_date_buy_then_sell_t1_rejects_if_no_matured_lot(session):
    """When a prior-day BUY (matured inventory) is deleted, a surviving
    same-date lower-id BUY and higher-id SELL must not let the SELL consume
    the same-day lot (A-share T+1).  Replay must check matured lots only
    (buy_trade_date < trade_date), not aggregate total_quantity.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── BUY A (will be deleted): creates matured inventory on 7/16 ──────
    buy_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)
    # Position: 100 shares, lot buy_trade_date=7/16 (matured by 7/18)

    # ── Same-date surviving orders on 7/18 ──────────────────────────────
    # BUY B (lower ID, same symbol): creates a lot on 7/18
    buy_b = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 18),
    )
    # SELL (higher ID, same symbol): tries to sell 100 shares
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )

    matching_service.run(date(2026, 7, 18), account.id)
    # Both fill: position = 200 (100 from 7/16 + 100 from 7/18) − 100 = 100
    assert len(repo.list_trades(account.id)) == 3

    # ── Delete BUY A (removes the matured lot) ──────────────────────────
    deleted = OrderDeleteService(repo, market_data).delete_order(buy_a.id)
    assert deleted is True

    # After replay:
    # - BUY B fills: creates lot on 7/18, position 000001: total=100
    # - SELL checks matured lots: only lot is buy_trade_date=7/18,
    #   which is NOT < 7/18 → matured=0 → SELL must be REJECTED.

    sell_order = repo.get_order(sell.id)
    assert sell_order.status == OrderStatus.REJECTED.value, f"Expected SELL REJECTED (T+1), got {sell_order.status}"
    assert sell_order.rejection_code == "A_SHARE_T1_VIOLATION", (
        f"Expected A_SHARE_T1_VIOLATION, got {sell_order.rejection_code}"
    )

    buy_b_order = repo.get_order(buy_b.id)
    assert buy_b_order.status == OrderStatus.FILLED.value, f"Expected BUY FILLED, got {buy_b_order.status}"

    # Position: only the 100 from BUY B remain (sell did not go through).
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None
    assert int(position.total_quantity) == 100, f"Expected total_quantity=100, got {position.total_quantity}"
    assert int(position.frozen_quantity) == 0, f"Expected frozen_quantity=0, got {position.frozen_quantity}"

    # Cash = 100000 − BUY B freeze(1005.01) = 98994.99 (no sell proceeds).
    expected_cash = Decimal("98994.9900")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"

    # Only the buy trade survives (no sell trade).
    trades = repo.list_trades(account.id)
    assert len(trades) == 1, f"Expected 1 trade, got {len(trades)}"
    assert trades[0].side == OrderSide.BUY.value


def test_etf_replay_same_day_sell_uses_etf_t1_policy():
    position = type("Position", (), {"total_quantity": 100, "frozen_quantity": 0})()
    lots = [type("Lot", (), {"remaining_quantity": 100, "buy_trade_date": date(2026, 7, 21)})()]

    ok, code, reason = OrderDeleteService._check_sell_reservation(
        position,
        lots,
        date(2026, 7, 21),
        100,
        market=Market.ETF.value,
    )

    assert ok is False
    assert code == "ETF_T1_VIOLATION"
    assert reason is not None
    assert "ETF T+1" in reason


def test_replay_rejected_order_reconsidered_on_later_delete(session):
    """A replay-induced rejection must not be sticky across subsequent deletes.
    If delete #1 rejects a BUY due to removed funding, and delete #2 removes
    a cash-consuming order making the BUY affordable, the BUY should be
    reconsidered and fill.  Original (non-replay) rejections must persist.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── Imported lots for the prior SELL symbol ─────────────────────────
    repo.upsert_position(
        account.id,
        Market.A_SHARE,
        "999999",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        Market.A_SHARE,
        "999999",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )

    # ── Prior SELL (deleted in delete #1): provides cash for BUY B ──────
    prior_sell = order_service.place_order(
        account.id,
        "999999",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)

    # ── BUY A (deleted in delete #2): consumes cash ─────────────────────
    buy_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        400,
        Decimal("100.00"),
        date(2026, 7, 17),
    )
    matching_service.run(date(2026, 7, 17), account.id)

    # ── BUY B (reconsidered after delete #2): needs SELL cash ───────────
    buy_b = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        600,
        Decimal("100.00"),
        date(2026, 7, 18),
    )

    # ── Original rejection (must persist across deletes) ─────────────────
    orig_rejected = order_service.place_order(
        account.id,
        "000003",
        OrderSide.BUY,
        250,
        Decimal("10.00"),
        date(2026, 7, 19),
    )

    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)
    assert orig_rejected.status == OrderStatus.REJECTED.value
    assert len(repo.list_trades(account.id)) == 3  # SELL + BUY A + BUY B

    # ── DELETE #1: remove the prior SELL → BUY B becomes unaffordable ───
    delete_svc = OrderDeleteService(repo, market_data)
    deleted1 = delete_svc.delete_order(prior_sell.id)
    assert deleted1 is True

    buy_b_after_d1 = repo.get_order(buy_b.id)
    assert buy_b_after_d1.status == OrderStatus.REJECTED.value, (
        f"After delete #1, BUY B should be REJECTED, got {buy_b_after_d1.status}"
    )
    # Must carry the replay marker.
    assert buy_b_after_d1.rejection_reason is not None
    assert buy_b_after_d1.rejection_reason.startswith(REPLAY_REJECTION_MARKER), (
        f"Expected replay marker, got: {buy_b_after_d1.rejection_reason}"
    )

    # Original rejection persists and is NOT marked.
    orig_after_d1 = repo.get_order(orig_rejected.id)
    assert orig_after_d1.status == OrderStatus.REJECTED.value
    assert orig_after_d1.rejection_reason is None or not orig_after_d1.rejection_reason.startswith(
        REPLAY_REJECTION_MARKER
    ), "Original rejection should not have replay marker"

    # ── DELETE #2: remove BUY A → BUY B should become affordable ────────
    delete_svc2 = OrderDeleteService(repo, market_data)
    deleted2 = delete_svc2.delete_order(buy_a.id)
    assert deleted2 is True

    # BUY B must be reconsidered and fill.
    buy_b_after_d2 = repo.get_order(buy_b.id)
    assert buy_b_after_d2.status == OrderStatus.FILLED.value, (
        f"After delete #2, BUY B should be FILLED, got {buy_b_after_d2.status}"
    )

    # Original rejection still persists.
    orig_after_d2 = repo.get_order(orig_rejected.id)
    assert orig_after_d2.status == OrderStatus.REJECTED.value

    # Cash: 100000 − BUY B frozen(60018.60) = 39981.40
    expected_cash = Decimal("39981.4000")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"


# ── HK Connect delete+replay wiring ────────────────────────────────────


def test_delete_replay_with_hk_order_uses_hk_validity(sqlite_session):
    """Surviving HK orders must get HK-specific validity checks after delete+
    replay. This proves OrderDeleteService wires hk_metadata through to
    TradeValidityService.
    """
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    session = sqlite_session
    session.add(
        GeneralInfoGGT(股票代码="00700", 股票名称="Tencent"),
    )
    session.flush()
    # Custom bars covering both HK and A-share prices.
    hk_bar = DailyBar(
        symbol="00700",
        trade_date=date(2026, 7, 21),
        open=Decimal("400"),
        high=Decimal("410"),
        low=Decimal("395"),
        close=Decimal("405"),
    )
    a_bar = DailyBar(
        symbol="000001.SZ",
        trade_date=date(2026, 7, 22),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        up_limit=Decimal("11.5"),
        down_limit=Decimal("8.5"),
    )
    bars = {
        ("00700", date(2026, 7, 21)): hk_bar,
        ("000001.SZ", date(2026, 7, 22)): a_bar,
    }
    market_data = FakeMarketDataProvider(bars)
    hk_meta = HkConnectMetadataProvider(session)

    validity_service = TradeValidityService(repo, market_data, hk_metadata=hk_meta)
    order_service = OrderService(repo, market_data, validity_service, hk_metadata=hk_meta)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    account = repo.create_account("hk-del", Decimal("500000.00"))

    # HK order (survives delete).
    hk_order = order_service.place_order(
        account.id,
        "00700",
        OrderSide.BUY,
        100,
        Decimal("400.00"),
        date(2026, 7, 21),
        market=Market.HK_CONNECT,
    )

    # Unrelated A-share order (will be deleted to trigger replay).
    delete_me = order_service.place_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 22),
    )

    # Fill both.
    matching_service.run(date(2026, 7, 21), account.id)
    matching_service.run(date(2026, 7, 22), account.id)
    assert len(repo.list_trades(account.id)) == 2

    # Delete using OrderDeleteService wired with hk_metadata.
    delete_svc = OrderDeleteService(repo, market_data, hk_metadata=hk_meta)
    deleted = delete_svc.delete_order(delete_me.id)
    assert deleted is True

    # Surviving HK order must have a validity check with HK-specific fields.
    checks = repo.list_trade_validity_checks(hk_order.id)
    assert len(checks) > 0, "HK order should have regenerated validity checks"
    last_check = checks[-1]
    # HK path sets both touched_limit fields to None.
    assert last_check.touched_limit_up is None, f"Expected None for HK limit-up, got {last_check.touched_limit_up}"
    assert last_check.touched_limit_down is None, (
        f"Expected None for HK limit-down, got {last_check.touched_limit_down}"
    )


def test_delete_replay_preserves_same_symbol_other_market_position(session):
    repo = PaperTradingRepository(session)
    account = repo.create_account("market-replay", Decimal("100000"))
    trade_date = date(2026, 7, 18)
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000.00"), source="imported")
    repo.create_position_lot(
        account.id, Market.A_SHARE, "000001", date(2026, 7, 14), 100, 100, Decimal("10.00"), source="imported"
    )
    repo.upsert_position(account.id, Market.HK_CONNECT, "000001", 200, 0, Decimal("1600.00"), source="imported")
    repo.create_position_lot(
        account.id, Market.HK_CONNECT, "000001", date(2026, 7, 14), 200, 200, Decimal("8.00"), source="imported"
    )
    sell = repo.create_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_quantity=100,
        market=Market.A_SHARE.value,
    )
    deleted = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        trade_date,
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.00"),
        market=Market.A_SHARE.value,
    )

    assert OrderDeleteService(repo, FakeMarketDataProvider()).delete_order(deleted.id) is True
    assert repo.get_order(sell.id).status == OrderStatus.FILLED.value
    assert repo.get_position(account.id, Market.A_SHARE, "000001") is None
    hk_position = repo.get_position(account.id, Market.HK_CONNECT, "000001")
    assert hk_position is not None
    assert hk_position.total_quantity == 200
    assert repo.get_lots(account.id, Market.HK_CONNECT, "000001")[0].remaining_quantity == 200
