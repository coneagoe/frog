from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import Market
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from tools.cleanup_zero_paper_positions import CleanupBlockedError, cleanup_zero_paper_positions


def test_cleanup_backfills_account_pnl_and_removes_closed_positions():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("cleanup", Decimal("1000"))
    repo.upsert_position(account.id, Market.A_SHARE, "CLOSED", 0, 0, Decimal("0"), realized_pnl=Decimal("75"))
    repo.upsert_position(account.id, Market.A_SHARE, "OPEN", 100, 0, Decimal("1000"), realized_pnl=Decimal("20"))

    result = cleanup_zero_paper_positions(session)

    assert result == {"accounts": 1, "positions": 1}
    persisted_account = repo.get_account(account.id)
    assert persisted_account is not None
    assert persisted_account.realized_pnl == Decimal("95.0000")
    assert repo.get_position(account.id, Market.A_SHARE, "CLOSED") is None
    assert repo.get_position(account.id, Market.A_SHARE, "OPEN") is not None


def test_cleanup_rejects_frozen_closed_position_without_writes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("frozen", Decimal("1000"))
    repo.upsert_position(account.id, Market.A_SHARE, "FROZEN", 0, 1, Decimal("0"), realized_pnl=Decimal("75"))

    with pytest.raises(CleanupBlockedError):
        cleanup_zero_paper_positions(session)

    persisted_account = repo.get_account(account.id)
    assert persisted_account is not None
    assert persisted_account.realized_pnl == Decimal("0.0000")
    assert repo.get_position(account.id, Market.A_SHARE, "FROZEN") is not None


def test_cleanup_dry_run_reports_candidates_without_writes():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("dry-run", Decimal("1000"))
    repo.upsert_position(account.id, Market.A_SHARE, "CLOSED", 0, 0, Decimal("0"), realized_pnl=Decimal("75"))

    result = cleanup_zero_paper_positions(session, dry_run=True)

    assert result == {"accounts": 1, "positions": 1}
    persisted_account = repo.get_account(account.id)
    assert persisted_account is not None
    assert persisted_account.realized_pnl == Decimal("0.0000")
    assert repo.get_position(account.id, Market.A_SHARE, "CLOSED") is not None


def test_cleanup_rejects_overwriting_existing_account_realized_pnl():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("already-migrated", Decimal("1000"))
    account.realized_pnl = Decimal("75")
    repo.upsert_position(account.id, Market.A_SHARE, "CLOSED", 0, 0, Decimal("0"), realized_pnl=Decimal("75"))

    with pytest.raises(CleanupBlockedError, match="non-zero realized PnL"):
        cleanup_zero_paper_positions(session)

    persisted_account = repo.get_account(account.id)
    assert persisted_account is not None
    assert persisted_account.realized_pnl == Decimal("75.0000")
    assert repo.get_position(account.id, Market.A_SHARE, "CLOSED") is not None
