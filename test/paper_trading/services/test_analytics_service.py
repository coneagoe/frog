from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import Market, OrderSide, OrderStatus, SnapshotPointType, SnapshotQualityStatus
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.models import PaperAccountSnapshot
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def seed_initial_point(repo, account):
    snapshots = repo.list_snapshots(account.id)
    assert snapshots
    initial = snapshots[0]
    assert initial.point_type == SnapshotPointType.INITIAL.value
    assert initial.quality_status == SnapshotQualityStatus.VALID.value
    assert initial.net_asset_value == Decimal("1.000000")
    return initial


def seed_trading_point(
    repo,
    account,
    nav: Decimal | None,
    trade_date: date | None = None,
    *,
    total_assets: Decimal = Decimal("100000.0000"),
    quality_status: str = SnapshotQualityStatus.VALID.value,
    event_at: datetime | None = None,
    invalid_reason: str | None = None,
    cash_available: Decimal | None = None,
    market_value: Decimal = Decimal("0"),
    realized_pnl: Decimal = Decimal("0"),
    unrealized_pnl: Decimal = Decimal("0"),
) -> PaperAccountSnapshot:
    if event_at is None:
        last = repo.list_snapshots(account.id)[-1]
        event_at = last.event_at + timedelta(days=1)
    if trade_date is None:
        trade_date = event_at.date()
    return repo.save_snapshot(
        account_id=account.id,
        trade_date=trade_date,
        event_at=event_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=quality_status,
        invalid_reason=invalid_reason,
        cash_available=total_assets if cash_available is None else cash_available,
        cash_frozen=Decimal("0"),
        market_value=market_value,
        total_assets=total_assets,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=nav,
    )


def _nav_snapshot(
    *,
    nav: Decimal | None,
    quality_status: str = SnapshotQualityStatus.VALID.value,
    total_assets: Decimal = Decimal("200000.0000"),
    point_type: str = SnapshotPointType.TRADING.value,
) -> PaperAccountSnapshot:
    snapshot = PaperAccountSnapshot()
    snapshot.point_type = point_type
    snapshot.quality_status = quality_status
    snapshot.net_asset_value = nav
    snapshot.total_assets = total_assets
    return snapshot


def test_analytics_computes_execution_and_trade_quality(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("analytics-demo", Decimal("100000.00"))
    repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.FILLED,
    )
    repo.create_order(
        account.id,
        "000002.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.REJECTED,
        rejection_code="INSUFFICIENT_CASH",
        rejection_reason="Insufficient cash",
    )
    win = repo.create_round_trip(
        account.id,
        Market.A_SHARE,
        "000001.SZ",
        1,
        date(2026, 6, 16),
        Decimal("1000.0000"),
        Decimal("5.0000"),
    )
    repo.update_round_trip(
        win,
        close_trade_id=2,
        close_trade_date=date(2026, 6, 20),
        exit_amount=Decimal("1100.0000"),
        fees=Decimal("11.0000"),
        realized_pnl=Decimal("89.0000"),
        return_pct=Decimal("0.089000"),
        holding_days=4,
        status="closed",
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.execution.fill_rate.value == Decimal("0.500000")
    assert analytics.execution.rejection_rate.value == Decimal("0.500000")
    assert analytics.execution.reject_reasons[0].reason == "INSUFFICIENT_CASH"
    assert analytics.trade_quality.win_rate.value == Decimal("1.000000")
    assert analytics.trade_quality.profit_factor.reason == "no_losses"
    engine.dispose()


def test_analytics_activity_counts_order_statuses(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("activity-demo", Decimal("100000.00"))
    for index, status in enumerate(
        (OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.ACCEPTED, OrderStatus.CANCELLED, OrderStatus.NEW)
    ):
        repo.create_order(
            account.id,
            f"00000{index + 1}.SZ",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            date(2026, 8, 1),
            status,
        )

    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 8, 1)).get_account_analytics(account.id)

    assert analytics.activity is not None
    assert analytics.activity.daily.total_orders == Decimal("5.000000")
    assert analytics.activity.daily.successful_orders == Decimal("1.000000")
    assert analytics.activity.daily.failed_orders == Decimal("1.000000")
    engine.dispose()


def test_analytics_activity_is_none_for_empty_account(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("empty-activity-demo", Decimal("100000.00"))

    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 8, 20)).get_account_analytics(account.id)

    assert analytics.activity is None
    engine.dispose()


def test_analytics_activity_is_none_for_only_future_orders(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("future-activity-demo", Decimal("100000.00"))
    repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 8, 21),
        OrderStatus.FILLED,
    )

    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 8, 20)).get_account_analytics(account.id)

    assert analytics.activity is None
    engine.dispose()


def test_analytics_activity_excludes_future_orders(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("mixed-date-activity-demo", Decimal("100000.00"))
    repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 8, 20),
        OrderStatus.FILLED,
    )
    repo.create_order(
        account.id,
        "000002.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 8, 21),
        OrderStatus.REJECTED,
    )

    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 8, 20)).get_account_analytics(account.id)

    assert analytics.activity is not None
    assert analytics.activity.coverage_start == date(2026, 8, 20)
    assert analytics.activity.coverage_end == date(2026, 8, 20)
    assert analytics.activity.daily.total_orders == Decimal("1.000000")
    assert analytics.activity.daily.successful_orders == Decimal("1.000000")
    assert analytics.activity.daily.failed_orders == Decimal("0.000000")
    engine.dispose()


def test_analytics_activity_uses_inclusive_calendar_denominators(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("activity-boundary-demo", Decimal("100000.00"))
    for index, (trade_date, status) in enumerate(
        (
            (date(2026, 8, 28), OrderStatus.FILLED),
            (date(2026, 8, 31), OrderStatus.FILLED),
            (date(2026, 9, 1), OrderStatus.REJECTED),
            (date(2026, 9, 10), OrderStatus.ACCEPTED),
        )
    ):
        repo.create_order(
            account.id,
            f"00000{index + 1}.SZ",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            trade_date,
            status,
        )

    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 9, 10)).get_account_analytics(account.id)

    assert analytics.activity is not None
    activity = analytics.activity
    assert activity.coverage_start == date(2026, 8, 28)
    assert activity.coverage_end == date(2026, 9, 10)
    assert activity.daily.total_orders == Decimal("0.285714")
    assert activity.weekly.total_orders == Decimal("1.333333")
    assert activity.monthly.total_orders == Decimal("2.000000")
    assert activity.daily.successful_orders == Decimal("0.142857")
    assert activity.weekly.failed_orders == Decimal("0.333333")
    assert activity.monthly.failed_orders == Decimal("0.500000")
    engine.dispose()


def test_analytics_activity_counts_weekend_and_holiday_natural_days(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("calendar-zero-period-demo", Decimal("100000.00"))
    repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 10, 1),
        OrderStatus.FILLED,
    )

    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 10, 5)).get_account_analytics(account.id)

    assert analytics.activity is not None
    assert analytics.activity.coverage_start == date(2026, 10, 1)
    assert analytics.activity.coverage_end == date(2026, 10, 5)
    assert analytics.activity.daily.total_orders == Decimal("0.200000")
    assert analytics.activity.weekly.total_orders == Decimal("0.500000")
    assert analytics.activity.monthly.total_orders == Decimal("1.000000")
    engine.dispose()


def test_analytics_activity_separates_cross_year_iso_week_and_calendar_months(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("cross-year-boundary-demo", Decimal("100000.00"))
    for index, trade_date in enumerate((date(2025, 12, 29), date(2026, 1, 4))):
        repo.create_order(
            account.id,
            f"00000{index + 1}.SZ",
            OrderSide.BUY,
            100,
            Decimal("10.00"),
            trade_date,
            OrderStatus.FILLED,
        )

    analytics = AnalyticsService(repo, today_provider=lambda: date(2026, 1, 4)).get_account_analytics(account.id)

    assert analytics.activity is not None
    assert analytics.activity.coverage_start == date(2025, 12, 29)
    assert analytics.activity.coverage_end == date(2026, 1, 4)
    assert analytics.activity.daily.total_orders == Decimal("0.285714")
    assert analytics.activity.weekly.total_orders == Decimal("2.000000")
    assert analytics.activity.monthly.total_orders == Decimal("1.000000")
    engine.dispose()


def test_analytics_computes_total_return_and_drawdown(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("risk-demo", Decimal("100000.00"))
    seed_initial_point(repo, account)
    seed_trading_point(repo, account, nav=Decimal("1.100000"), trade_date=date(2026, 6, 17))
    seed_trading_point(repo, account, nav=Decimal("0.990000"), trade_date=date(2026, 6, 18))

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value == Decimal("-0.010000")
    assert analytics.risk.max_drawdown.value == Decimal("-0.100000")
    assert analytics.risk.current_drawdown.value == Decimal("-0.100000")
    assert analytics.risk.sharpe.reason == "insufficient_data"
    engine.dispose()


def test_analytics_no_orders_returns_insufficient_data_for_rates(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("no-orders-demo", Decimal("100000.00"))

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.execution.fill_rate.reason == "insufficient_data"
    assert analytics.execution.fill_rate.value is None
    assert analytics.execution.rejection_rate.reason == "insufficient_data"
    assert analytics.execution.rejection_rate.value is None
    engine.dispose()


@pytest.mark.parametrize("initial_cash", [Decimal("0"), Decimal("-1")])
def test_analytics_zero_initial_cash_is_rejected(tmp_path, initial_cash):
    engine, session, repo = _repo(tmp_path)

    with pytest.raises(ValueError, match="initial_cash"):
        repo.create_account("zero-cash-demo", initial_cash)

    engine.dispose()


def test_analytics_streak_uses_close_date_ordering(tmp_path):
    """Streak calculation must order closed round trips by close date, not open date."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("streak-demo", Decimal("100000.00"))

    # Round trips: first opened, third closed (loser), second closed (winner)
    # When ordered by close date: loser then winner → max consecutive win = 1 (not 2)
    rt1 = repo.create_round_trip(
        account.id,
        Market.A_SHARE,
        "A",
        1,
        date(2026, 6, 1),
        Decimal("1000.0000"),
        Decimal("5.0000"),
    )
    repo.update_round_trip(
        rt1,
        close_trade_id=2,
        close_trade_date=date(2026, 6, 20),
        exit_amount=Decimal("1100.0000"),
        fees=Decimal("11.0000"),
        realized_pnl=Decimal("89.0000"),
        return_pct=Decimal("0.089000"),
        holding_days=19,
        status="closed",
    )
    rt2 = repo.create_round_trip(
        account.id,
        Market.A_SHARE,
        "B",
        3,
        date(2026, 6, 5),
        Decimal("1000.0000"),
        Decimal("5.0000"),
    )
    repo.update_round_trip(
        rt2,
        close_trade_id=4,
        close_trade_date=date(2026, 6, 15),
        exit_amount=Decimal("900.0000"),
        fees=Decimal("5.0000"),
        realized_pnl=Decimal("-105.0000"),
        return_pct=Decimal("-0.105000"),
        holding_days=10,
        status="closed",
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    # Ordered by close date: B (loser, 6/15) → A (winner, 6/20)
    # Streaks: loss(1) → win(1) → consecutive_wins=1, consecutive_losses=1
    assert analytics.trade_quality.consecutive_wins == 1
    assert analytics.trade_quality.consecutive_losses == 1
    engine.dispose()


def test_analytics_recent_round_trips_limit_and_ordering(tmp_path):
    """Only the most recent 20 round trips should be returned; closed rows come before open rows."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("limit-demo", Decimal("100000.00"))

    # 20 closed trips (newest close dates near the end)
    for i in range(20):
        rt = repo.create_round_trip(
            account.id,
            Market.A_SHARE,
            f"S{i}",
            i + 1,
            date(2026, 6, 1),
            Decimal("1000.0000"),
            Decimal("5.0000"),
        )
        repo.update_round_trip(
            rt,
            close_trade_id=i + 2,
            close_trade_date=date(2026, 6, 1 + i),
            exit_amount=Decimal("1100.0000"),
            fees=Decimal("11.0000"),
            realized_pnl=Decimal("89.0000"),
            return_pct=Decimal("0.089000"),
            holding_days=1,
            status="closed",
        )

    # 10 open trips (no close date)
    for i in range(20, 30):
        repo.create_round_trip(
            account.id,
            Market.A_SHARE,
            f"O{i}",
            i + 1,
            date(2026, 6, 1 + i),
            Decimal("1000.0000"),
            Decimal("5.0000"),
        )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    # Aggregate metrics should reflect all 20 closed round trips
    assert analytics.trade_quality.closed_count == 20
    assert analytics.trade_quality.win_rate.value == Decimal("1.000000")

    # Returned rows: 20 (capped), all 20 closed come first, open rows excluded
    assert len(analytics.trade_quality.round_trips) == 20
    for r in analytics.trade_quality.round_trips:
        assert r.status == "closed"
    engine.dispose()


def test_analytics_recent_round_trips_limit_open_only(tmp_path):
    """Early return with zero closed trips: 20 most recent open rows by open date."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("open-only-demo", Decimal("100000.00"))

    # 30 open-only round trips, oldest-first (id=1 → 2026-06-01, id=30 → 2026-06-30)
    for i in range(30):
        repo.create_round_trip(
            account.id,
            Market.A_SHARE,
            f"O{i}",
            i + 1,
            date(2026, 6, 1 + i),
            Decimal("1000.0000"),
            Decimal("5.0000"),
        )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.trade_quality.closed_count == 0
    assert len(analytics.trade_quality.round_trips) == 20
    for r in analytics.trade_quality.round_trips:
        assert r.status == "open"
    # Newest 20 by open date: dates 2026-06-30 (id=30) down to 2026-06-11 (id=11)
    assert analytics.trade_quality.round_trips[0].id == 30
    assert analytics.trade_quality.round_trips[19].id == 11
    engine.dispose()


def test_analytics_insufficient_valid_points_keep_established_metric_reasons(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("calmar-demo", Decimal("100000.00"))
    seed_initial_point(repo, account)
    seed_trading_point(
        repo,
        account,
        nav=None,
        trade_date=date(2026, 6, 16),
        total_assets=Decimal("0"),
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="missing_nav",
    )
    seed_trading_point(
        repo,
        account,
        nav=None,
        trade_date=date(2026, 6, 17),
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="missing_nav",
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value == Decimal("0.000000")
    assert analytics.risk.max_drawdown.reason == "insufficient_data"
    assert analytics.risk.current_drawdown.reason == "insufficient_data"
    assert analytics.risk.sharpe.reason == "insufficient_data"
    assert analytics.risk.sortino.reason == "insufficient_data"
    assert analytics.risk.calmar.reason == "insufficient_data"
    assert analytics.risk.calmar.value is None
    engine.dispose()


def test_analytics_uses_nav_return_not_total_assets_after_deposit(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("nav-return-demo", Decimal("100000.00"))
    seed_initial_point(repo, account)
    seed_trading_point(
        repo,
        account,
        nav=Decimal("1.000000"),
        trade_date=date(2026, 6, 17),
        total_assets=Decimal("150000.0000"),
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value == Decimal("0.000000")
    simple_asset_return = analytics.overview.simple_asset_return
    assert simple_asset_return is not None
    assert simple_asset_return.value == Decimal("0.500000")
    assert analytics.risk.max_drawdown.value == Decimal("0.000000")
    engine.dispose()


def test_total_return_uses_persisted_initial_nav_not_assets(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("persisted-nav-demo", Decimal("100000.00"))
    seed_initial_point(repo, account)
    seed_trading_point(
        repo,
        account,
        nav=Decimal("1.100000"),
        trade_date=date(2026, 6, 17),
        total_assets=Decimal("250000.0000"),
    )

    response = AnalyticsService(repo).get_account_analytics(account.id)

    assert response.overview.total_return.value == Decimal("0.100000")
    assert response.overview.simple_asset_return is not None
    assert response.overview.simple_asset_return.value == Decimal("1.500000")
    engine.dispose()


def test_total_return_and_risk_preserve_same_day_repository_order(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("same-day-nav-demo", Decimal("100000.00"))
    seed_initial_point(repo, account)
    created_at = account.created_at
    later = created_at + timedelta(hours=2)
    earlier = created_at + timedelta(hours=1)
    seed_trading_point(
        repo,
        account,
        nav=Decimal("1.200000"),
        trade_date=later.date(),
        event_at=later,
    )
    seed_trading_point(
        repo,
        account,
        nav=Decimal("0.900000"),
        trade_date=earlier.date(),
        event_at=earlier,
    )

    snapshots = repo.list_snapshots(account.id)
    navs = AnalyticsService._nav_series(snapshots)
    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert [snapshot.event_at for snapshot in snapshots[1:]] == [earlier, later]
    assert navs == [Decimal("1.000000"), Decimal("0.900000"), Decimal("1.200000")]
    assert analytics.overview.total_return.value == Decimal("0.200000")
    assert analytics.risk.max_drawdown.value == Decimal("-0.100000")
    engine.dispose()


def test_invalid_nav_points_are_ignored_by_total_return_and_risk(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("ignore-invalid-nav", Decimal("100000.00"))
    seed_initial_point(repo, account)
    seed_trading_point(
        repo,
        account,
        nav=None,
        trade_date=date(2026, 6, 17),
        total_assets=Decimal("50000.0000"),
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="missing_nav",
    )
    seed_trading_point(repo, account, nav=Decimal("1.100000"), trade_date=date(2026, 6, 18))
    seed_trading_point(
        repo,
        account,
        nav=Decimal("0"),
        trade_date=date(2026, 6, 19),
        total_assets=Decimal("0"),
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="non_positive_nav",
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value == Decimal("0.100000")
    assert analytics.risk.max_drawdown.value == Decimal("0.000000")
    assert analytics.overview.simple_asset_return is not None
    assert analytics.overview.simple_asset_return.value == Decimal("-1.000000")
    engine.dispose()


def test_overview_keeps_latest_persisted_fields_when_latest_nav_is_invalid(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("latest-invalid-overview", Decimal("100000.00"))
    seed_initial_point(repo, account)
    seed_trading_point(
        repo,
        account,
        nav=Decimal("1.100000"),
        trade_date=date(2026, 6, 17),
        total_assets=Decimal("110000.0000"),
    )
    seed_trading_point(
        repo,
        account,
        nav=None,
        trade_date=date(2026, 6, 18),
        total_assets=Decimal("80000.0000"),
        cash_available=Decimal("50000.0000"),
        market_value=Decimal("30000.0000"),
        realized_pnl=Decimal("2000.0000"),
        unrealized_pnl=Decimal("-1000.0000"),
        quality_status=SnapshotQualityStatus.INVALID.value,
        invalid_reason="missing_nav",
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value == Decimal("0.100000")
    assert analytics.overview.net_asset_value is None
    assert analytics.overview.total_assets == Decimal("80000.0000")
    assert analytics.overview.cash_available == Decimal("50000.0000")
    assert analytics.overview.market_value == Decimal("30000.0000")
    assert analytics.overview.realized_pnl == Decimal("2000.0000")
    assert analytics.overview.unrealized_pnl == Decimal("-1000.0000")
    assert analytics.overview.simple_asset_return is not None
    assert analytics.overview.simple_asset_return.value == Decimal("-0.200000")
    assert analytics.risk.max_drawdown.value == Decimal("0.000000")
    engine.dispose()


def test_invalid_initial_nav_does_not_anchor_total_return_or_risk_on_later_trading_point(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("invalid-initial-nav", Decimal("100000.00"))
    initial = seed_initial_point(repo, account)
    initial.quality_status = SnapshotQualityStatus.INVALID.value
    initial.net_asset_value = None
    initial.invalid_reason = "missing_nav"
    session.flush()
    seed_trading_point(repo, account, nav=Decimal("1.100000"), trade_date=date(2026, 6, 17))

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.value is None
    assert analytics.overview.total_return.reason == "invalid_nav"
    assert analytics.risk.max_drawdown.value is None
    assert analytics.risk.max_drawdown.reason == "insufficient_data"
    assert analytics.risk.current_drawdown.reason == "insufficient_data"
    assert analytics.risk.sharpe.reason == "insufficient_data"
    assert analytics.risk.sortino.reason == "insufficient_data"
    assert analytics.risk.calmar.reason == "insufficient_data"
    assert analytics.overview.simple_asset_return is not None
    assert analytics.overview.simple_asset_return.value == Decimal("0.000000")
    engine.dispose()


@pytest.mark.parametrize(
    ("nav", "quality_status"),
    [
        (None, SnapshotQualityStatus.INVALID.value),
        (None, SnapshotQualityStatus.VALID.value),
        (Decimal("0"), SnapshotQualityStatus.VALID.value),
        (Decimal("-1.000000"), SnapshotQualityStatus.VALID.value),
        (Decimal("NaN"), SnapshotQualityStatus.VALID.value),
        (Decimal("Infinity"), SnapshotQualityStatus.VALID.value),
        (Decimal("1.250000"), SnapshotQualityStatus.INVALID.value),
        (Decimal("1.250000"), SnapshotQualityStatus.VALID.value),
    ],
)
def test_snapshot_nav_never_derives_fallback_from_total_assets(nav, quality_status):
    snapshot = _nav_snapshot(nav=nav, quality_status=quality_status, total_assets=Decimal("250000.0000"))

    result = AnalyticsService._snapshot_nav(snapshot)

    if quality_status == SnapshotQualityStatus.VALID.value and nav == Decimal("1.250000"):
        assert result == Decimal("1.250000")
    else:
        assert result is None


def test_nav_series_preserves_input_order_and_excludes_invalid_points():
    snapshots = [
        _nav_snapshot(nav=Decimal("1.000000"), point_type=SnapshotPointType.INITIAL.value),
        _nav_snapshot(nav=None, quality_status=SnapshotQualityStatus.INVALID.value),
        _nav_snapshot(nav=Decimal("1.050000")),
        _nav_snapshot(nav=Decimal("0"), quality_status=SnapshotQualityStatus.INVALID.value),
        _nav_snapshot(nav=Decimal("1.020000")),
    ]

    assert AnalyticsService._nav_series(snapshots) == [
        Decimal("1.000000"),
        Decimal("1.050000"),
        Decimal("1.020000"),
    ]


def test_nav_series_is_empty_when_first_point_is_not_valid_initial():
    invalid_initial = [
        _nav_snapshot(
            nav=None,
            quality_status=SnapshotQualityStatus.INVALID.value,
            point_type=SnapshotPointType.INITIAL.value,
        ),
        _nav_snapshot(nav=Decimal("1.100000")),
    ]
    trading_first = [
        _nav_snapshot(nav=Decimal("1.000000")),
        _nav_snapshot(nav=Decimal("1.100000")),
    ]

    assert AnalyticsService._nav_series(invalid_initial) == []
    assert AnalyticsService._nav_series(trading_first) == []
