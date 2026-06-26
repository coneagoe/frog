from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    AdjustType,
    PeriodType,
)
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import StorageMarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


def test_generate_snapshot_values_positions_at_close(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, "000001.SZ", 100, 0, Decimal("900.00"))
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.0],
                    COL_HIGH: [11.0],
                    COL_LOW: [8.0],
                    COL_CLOSE: [10.0],
                }
            ),
        }
    )
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    snapshot = SnapshotService(repo, market_data).generate_snapshot(account.id, date(2026, 6, 16))
    session.commit()

    assert snapshot.cash_available == Decimal("100000.0000")
    assert snapshot.cash_frozen == Decimal("0.0000")
    assert snapshot.market_value == Decimal("1000.0000")
    assert snapshot.total_assets == Decimal("101000.0000")
    assert snapshot.unrealized_pnl == Decimal("100.0000")
    assert snapshot.position_count == 1
    assert storage.calls == [("000001", PeriodType.DAILY, AdjustType.BFQ, "2026-06-16", "2026-06-16")]
    engine.dispose()


def test_generate_snapshot_updates_existing_account_date_snapshot(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_upsert.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, "000001.SZ", 100, 0, Decimal("900.00"))
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.0],
                    COL_HIGH: [11.0],
                    COL_LOW: [8.0],
                    COL_CLOSE: [10.0],
                }
            ),
        }
    )
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))
    snapshot_service = SnapshotService(repo, market_data)

    snapshot_service.generate_snapshot(account.id, date(2026, 6, 16))
    repo.upsert_position(account.id, "000001.SZ", 200, 0, Decimal("1800.00"))
    snapshot = snapshot_service.generate_snapshot(account.id, date(2026, 6, 16))
    session.commit()

    assert session.query(PaperAccountSnapshot).filter_by(account_id=account.id).count() == 1
    assert snapshot.market_value == Decimal("2000.0000")
    assert snapshot.total_assets == Decimal("102000.0000")
    assert snapshot.unrealized_pnl == Decimal("200.0000")
    engine.dispose()
