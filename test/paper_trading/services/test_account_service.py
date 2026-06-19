from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus
from paper_trading.services.account_service import AccountService
from paper_trading.storage.models import (
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperMatchingRun,
    PaperOrder,
    PaperPosition,
    PaperPositionLot,
    PaperTrade,
)
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def _repo_and_service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    return engine, session, repo, AccountService(repo)


def test_create_account_returns_active_account_with_initial_cash(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'account.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)

    account = AccountService(repo).create_account("demo", Decimal("100000.00"))
    session.commit()

    assert account.name == "demo"
    assert account.status == "active"
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")
    engine.dispose()


def test_delete_account_removes_account_owned_rows(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("demo", Decimal("100000.00"))
    order = repo.create_order(
        account.id,
        "000001.SZ",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 6, 16),
        OrderStatus.ACCEPTED,
    )
    trade = PaperTrade(
        order_id=order.id,
        account_id=account.id,
        symbol="000001.SZ",
        side=OrderSide.BUY.value,
        quantity=100,
        price=Decimal("10.00"),
        amount=Decimal("1000.00"),
        fees=Decimal("5.00"),
        trade_date=date(2026, 6, 16),
    )
    session.add(trade)
    repo.upsert_position(account.id, "000001.SZ", 100, 0, Decimal("1000.00"))
    repo.create_position_lot(account.id, "000001.SZ", date(2026, 6, 16), 100, 100, Decimal("10.00"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 6, 16),
        cash_available=Decimal("98995.00"),
        cash_frozen=Decimal("0.00"),
        market_value=Decimal("1000.00"),
        total_assets=Decimal("99995.00"),
        realized_pnl=Decimal("0.00"),
        unrealized_pnl=Decimal("0.00"),
        position_count=1,
        order_count=1,
        trade_count=1,
    )
    session.add(PaperMatchingRun(trade_date=date(2026, 6, 16), account_id=account.id, status="completed"))
    session.commit()

    deleted = service.delete_account(account.id)
    session.commit()

    assert deleted is True
    assert repo.get_account(account.id) is None
    assert session.query(PaperCashLedger).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperTrade).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperOrder).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperPosition).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperPositionLot).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperAccountSnapshot).filter_by(account_id=account.id).count() == 0
    assert session.query(PaperMatchingRun).filter_by(account_id=account.id).count() == 0
    engine.dispose()
