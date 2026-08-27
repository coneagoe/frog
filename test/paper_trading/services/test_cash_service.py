from datetime import date, datetime, timezone, tzinfo
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import SnapshotPointType, SnapshotQualityStatus
from paper_trading.schemas.accounts import CashFlowRequest
from paper_trading.services.cash_service import CashService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cash_service.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session, PaperTradingRepository(session)


def test_deposit_adds_cash_and_mints_shares_without_changing_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    result = CashService(repo).deposit(account.id, Decimal("25000.00"), date(2026, 7, 20), "add cash")
    session.commit()

    assert result.ledger.amount == Decimal("25000.0000")
    assert result.ledger.share_delta == Decimal("25000.000000")
    assert result.account.share_count == Decimal("125000.000000")
    assert result.account.net_asset_value == Decimal("1.000000")
    assert result.cash_available == Decimal("125000.0000")
    engine.dispose()


def test_withdraw_reduces_cash_and_redeems_shares_without_changing_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    result = CashService(repo).withdraw(account.id, Decimal("5000.00"), date(2026, 7, 20), "take cash")
    session.commit()

    assert result.ledger.amount == Decimal("-5000.0000")
    assert result.ledger.share_delta == Decimal("-5000.000000")
    assert result.account.share_count == Decimal("95000.000000")
    assert result.cash_available == Decimal("95000.0000")
    engine.dispose()


def test_withdraw_rejects_more_than_available_cash(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))

    with pytest.raises(ValueError, match="withdrawal amount 100001.0000 exceeds available cash 100000.0000"):
        CashService(repo).withdraw(account.id, Decimal("100001.00"), date(2026, 7, 20), None)

    assert len(repo.list_cash_ledger(account.id)) == 1
    engine.dispose()


def test_cash_flow_before_valuation_uses_initial_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    account.net_asset_value = Decimal("1.500000")
    occurred_at = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)

    result = CashService(repo).deposit(account.id, Decimal("25000.00"), date(2026, 7, 20), occurred_at=occurred_at)

    assert result.ledger.net_asset_value == Decimal("1.000000")
    assert result.ledger.share_delta == Decimal("25000.000000")
    engine.dispose()


def test_cash_flow_after_valid_snapshot_uses_preceding_snapshot_nav(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    snapshot_at = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)
    repo.save_trading_snapshot(
        account_id=account.id,
        trade_date=snapshot_at.date(),
        event_at=snapshot_at,
        point_type=SnapshotPointType.TRADING.value,
        quality_status=SnapshotQualityStatus.VALID.value,
        cash_available=Decimal("100000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("0"),
        total_assets=Decimal("125000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=0,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1.250000"),
    )
    account.net_asset_value = Decimal("1.500000")

    result = CashService(repo).deposit(
        account.id,
        Decimal("25000.00"),
        date(2026, 7, 20),
        occurred_at=datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
    )

    assert result.ledger.net_asset_value == Decimal("1.250000")
    assert result.ledger.share_delta == Decimal("20000.000000")
    engine.dispose()


def test_cash_flow_request_rejects_naive_occurred_at():
    with pytest.raises(ValueError, match="offset"):
        CashFlowRequest(amount=Decimal("1"), trade_date=date(2026, 7, 20), occurred_at=datetime(2026, 7, 20))


class _NoOffsetTz(tzinfo):
    def utcoffset(self, _value):
        return None

    def dst(self, _value):
        return None

    def tzname(self, _value):
        return "no-offset"


def test_cash_flow_request_rejects_tzinfo_without_offset():
    with pytest.raises(ValueError, match="offset"):
        CashFlowRequest(
            amount=Decimal("1"),
            trade_date=date(2026, 7, 20),
            occurred_at=datetime(2026, 7, 20, tzinfo=_NoOffsetTz()),
        )


def test_cash_service_rejects_tzinfo_without_offset(tmp_path):
    engine, session, repo = _repo(tmp_path)
    account = repo.create_account("no-offset-service", Decimal("100000.00"))

    with pytest.raises(ValueError, match="offset"):
        CashService(repo).deposit(
            account.id,
            Decimal("1"),
            date(2026, 7, 20),
            occurred_at=datetime(2026, 7, 20, tzinfo=_NoOffsetTz()),
        )

    engine.dispose()
