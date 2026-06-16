from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.services.account_service import AccountService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


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
