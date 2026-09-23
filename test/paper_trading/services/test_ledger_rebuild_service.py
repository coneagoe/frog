from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import OrderSide, OrderStatus, TradeValidityReason, TradeValidityStatus
from paper_trading.services.ledger_rebuild_service import LedgerRebuildService
from paper_trading.storage.models import PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository
from test.paper_trading.fakes import FakeMarketDataProvider


def _validity_check(repo, order, reason_code: TradeValidityReason) -> PaperTradeValidityCheck:
    return repo.create_trade_validity_check(
        order_id=order.id,
        account_id=order.account_id,
        symbol=order.symbol,
        trade_date=order.trade_date,
        side=order.side,
        input_price=Decimal(order.limit_price),
        data_granularity="daily",
        daily_low=None,
        daily_high=None,
        limit_up_price=None,
        limit_down_price=None,
        touched_limit_up=None,
        touched_limit_down=None,
        price_in_range=None,
        status=TradeValidityStatus.UNCHECKED.value,
        reason_code=reason_code,
        reason_detail="old check",
        market=order.market,
    )


def test_rebuild_regenerates_validity_checks_only_from_start_date(session):
    repo = PaperTradingRepository(session)
    account = repo.create_account("validity-rebuild", Decimal("100000"))
    before_scope = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 16),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005"),
    )
    in_scope = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005"),
    )
    old_before = _validity_check(repo, before_scope, TradeValidityReason.VALID)
    _validity_check(repo, in_scope, TradeValidityReason.VALID)
    session.flush()

    rebuild = LedgerRebuildService(repo, FakeMarketDataProvider()).rebuild_account_from(
        account.id,
        date(2026, 7, 17),
    )

    before_checks = repo.list_trade_validity_checks(before_scope.id)
    in_scope_checks = repo.list_trade_validity_checks(in_scope.id)
    assert rebuild.status == "completed"
    assert [check.id for check in before_checks] == [old_before.id]
    assert len(in_scope_checks) == 1
    assert in_scope_checks[0].reason_code == TradeValidityReason.LIMIT_PRICE_UNAVAILABLE.value
    assert in_scope_checks[0].reason_detail != "old check"
