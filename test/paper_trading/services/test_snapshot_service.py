from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import DailyBar, InMemoryMarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_generate_snapshot_values_positions_at_close(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, "000001.SZ", 100, 0, Decimal("900.00"))
    market_data = InMemoryMarketDataProvider(
        bars={
            ("000001.SZ", date(2026, 6, 16)): DailyBar(
                "000001.SZ",
                date(2026, 6, 16),
                Decimal("9"),
                Decimal("11"),
                Decimal("8"),
                Decimal("10"),
            )
        },
        trade_dates=[date(2026, 6, 16)],
    )

    snapshot = SnapshotService(repo, market_data).generate_snapshot(
        account.id, date(2026, 6, 16)
    )
    session.commit()

    assert snapshot.cash_available == Decimal("100000.0000")
    assert snapshot.cash_frozen == Decimal("0.0000")
    assert snapshot.market_value == Decimal("1000.0000")
    assert snapshot.total_assets == Decimal("101000.0000")
    assert snapshot.unrealized_pnl == Decimal("100.0000")
    assert snapshot.position_count == 1
    engine.dispose()
