from datetime import date
from decimal import Decimal

from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_process_settlements_releases_due_cash(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-proc", Decimal("0.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    from paper_trading.services.hk_settlement_service import HkSettlementService

    service = HkSettlementService(repo)
    count = service.process_settlements(date(2026, 7, 23))
    assert count == 1
    assert pending.settled is True
    # Cash should now be available
    assert repo.get_cash_available(account.id) == Decimal("50000.0000")


def test_process_settlements_skips_future_dates(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-skip", Decimal("0.00"))
    repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    from paper_trading.services.hk_settlement_service import HkSettlementService

    service = HkSettlementService(repo)
    count = service.process_settlements(date(2026, 7, 22))
    assert count == 0


def test_settle_pending_is_idempotent(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("settle-idem", Decimal("0.00"))
    pending = repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )

    repo.settle_pending(pending.id)
    repo.settle_pending(pending.id)

    assert pending.settled is True
    assert repo.get_cash_available(account.id) == Decimal("50000.0000")
