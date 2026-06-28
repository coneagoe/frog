from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


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


def test_analytics_computes_total_return_and_drawdown(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("risk-demo", Decimal("100000.00"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 16),
        cash_available=Decimal("100000.0000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000.0000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
    )
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 17),
        cash_available=Decimal("110000.0000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("110000.0000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
    )
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 18),
        cash_available=Decimal("99000.0000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("99000.0000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
    )

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


def test_analytics_zero_initial_cash_preserves_snapshot_fields(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("zero-cash-demo", Decimal("0"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 16),
        cash_available=Decimal("50000.0000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("30000.0000"),
        total_assets=Decimal("80000.0000"),
        realized_pnl=Decimal("2000.0000"),
        unrealized_pnl=Decimal("-1000.0000"),
        position_count=0,
        order_count=0,
        trade_count=0,
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.reason == "invalid_initial_cash"
    assert analytics.overview.total_return.value is None
    assert analytics.overview.total_assets == Decimal("80000.0000")
    assert analytics.overview.cash_available == Decimal("50000.0000")
    assert analytics.overview.market_value == Decimal("30000.0000")
    assert analytics.overview.realized_pnl == Decimal("2000.0000")
    assert analytics.overview.unrealized_pnl == Decimal("-1000.0000")
    engine.dispose()


def test_analytics_streak_uses_close_date_ordering(tmp_path):
    """Streak calculation must order closed round trips by close date, not open date."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("streak-demo", Decimal("100000.00"))

    # Round trips: first opened, third closed (loser), second closed (winner)
    # When ordered by close date: loser then winner → max consecutive win = 1 (not 2)
    rt1 = repo.create_round_trip(
        account.id,
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
    """Early return with zero closed trips still applies the 20-row recent limit."""
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("open-only-demo", Decimal("100000.00"))

    # 30 open-only round trips (no close date)
    for i in range(30):
        repo.create_round_trip(
            account.id,
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
    engine.dispose()


def test_analytics_zero_first_snapshot_assets_returns_invalid_initial_assets_for_calmar(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("calmar-demo", Decimal("100000.00"))
    # First snapshot has total_assets = 0 (invalid denominator)
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 16),
        cash_available=Decimal("0"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("0"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
    )
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 17),
        cash_available=Decimal("100000.0000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100000.0000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.risk.calmar.reason == "invalid_initial_assets"
    assert analytics.risk.calmar.value is None
    engine.dispose()
