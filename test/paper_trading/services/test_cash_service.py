from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
