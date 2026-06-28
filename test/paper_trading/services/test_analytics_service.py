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


def test_analytics_zero_initial_cash_returns_invalid_initial_cash(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("zero-cash-demo", Decimal("0"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 16),
        cash_available=Decimal("0"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("100.0000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
    )

    analytics = AnalyticsService(repo).get_account_analytics(account.id)

    assert analytics.overview.total_return.reason == "invalid_initial_cash"
    assert analytics.overview.total_return.value is None
    engine.dispose()
