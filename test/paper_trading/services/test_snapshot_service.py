from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

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
from paper_trading.domain.enums import Market
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import DailyBar, StorageMarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeHistoryStorage, FakeMarketDataProvider, FakeTradeCalendar


def test_generate_snapshot_values_positions_at_close(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 100, 0, Decimal("900.00"))
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


def test_generate_snapshot_uses_account_realized_pnl_after_position_is_closed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_realized_pnl.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("closed-position-pnl", Decimal("100000.00"))
    account.realized_pnl = Decimal("75.5000")

    snapshot = SnapshotService(repo, FakeMarketDataProvider()).generate_snapshot(account.id, date(2026, 6, 16))

    assert snapshot.realized_pnl == Decimal("75.5000")
    assert snapshot.position_count == 0
    engine.dispose()


def test_generate_snapshot_persists_nav_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_nav.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 100, 0, Decimal("900.00"))
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

    assert snapshot.total_assets == Decimal("101000.0000")
    assert snapshot.share_count == Decimal("100000.000000")
    assert snapshot.net_asset_value == Decimal("1.010000")
    assert snapshot.cumulative_deposit == Decimal("100000.0000")
    assert snapshot.cumulative_withdrawal == Decimal("0.0000")
    assert snapshot.net_cash_flow == Decimal("100000.0000")
    assert account.net_asset_value == Decimal("1.010000")
    engine.dispose()


def test_generate_snapshot_updates_existing_account_date_snapshot(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_upsert.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("demo", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 100, 0, Decimal("900.00"))
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
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 200, 0, Decimal("1800.00"))
    snapshot = snapshot_service.generate_snapshot(account.id, date(2026, 6, 16))
    session.commit()

    assert session.query(PaperAccountSnapshot).filter_by(account_id=account.id).count() == 1
    assert snapshot.market_value == Decimal("2000.0000")
    assert snapshot.total_assets == Decimal("102000.0000")
    assert snapshot.unrealized_pnl == Decimal("200.0000")
    engine.dispose()


def test_snapshot_includes_pending_settlement(sqlite_session):
    """Snapshot total_assets must include pending settlement amount."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("pending-snap", Decimal("100000.00"))
    repo.create_pending_settlement(
        account_id=account.id,
        amount=Decimal("50000.00"),
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    md = FakeMarketDataProvider()
    snapshot_service = SnapshotService(repo, md)
    snapshot = snapshot_service.generate_snapshot(account.id, date(2026, 7, 21))

    assert snapshot.pending_settlement == Decimal("50000.0000")
    # total_assets includes cash_available + cash_frozen + market_value + pending_settlement
    assert snapshot.total_assets == Decimal("150000.0000")  # 100000 + 50000


def test_snapshot_passes_position_market_to_get_daily_bar(sqlite_session):
    """Snapshot must pass each position's market to get_daily_bar."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("snap-mkt", Decimal("100000.00"))
    # Create an imported HK position and rebuild it from its lot.
    repo.create_position_lot(
        account.id,
        Market.HK_CONNECT,
        "00700",
        date(2026, 7, 1),
        original_quantity=100,
        remaining_quantity=100,
        cost_price=Decimal("400.00"),
        source="imported",
    )
    repo.upsert_position(
        account.id,
        Market.HK_CONNECT,
        "00700",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("40000.00"),
        source="imported",
    )
    repo.clear_account_rebuild_state(account.id)
    # Create an A-share position
    repo.upsert_position(
        account.id, Market.A_SHARE, "000001.SZ", total_quantity=100, frozen_quantity=0, cost_amount=Decimal("1000.00")
    )

    class MarketCaptureProvider(FakeMarketDataProvider):
        def __init__(self):
            super().__init__()
            self.captured: list[tuple[str, str | None]] = []

        def get_daily_bar(self, symbol, trade_date, market=None):
            self.captured.append((symbol, market))
            return DailyBar(
                symbol=symbol,
                trade_date=trade_date,
                open=Decimal("10"),
                high=Decimal("100"),
                low=Decimal("1"),
                close=Decimal("50"),
            )

    md = MarketCaptureProvider()
    snapshot_service = SnapshotService(repo, md)
    snapshot_service.generate_snapshot(account.id, date(2026, 7, 21))

    assert ("00700", "hk_connect") in md.captured, f"HK position should pass market='hk_connect', got {md.captured}"
    # A-share position — position.market defaults to 'a_share'
    assert ("000001.SZ", "a_share") in md.captured or ("000001.SZ", None) in md.captured, (
        f"A-share position market not found, got {md.captured}"
    )


def test_missing_exact_date_position_bar_records_valuation_gap(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("valuation-gap", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class MissingBarProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError(f"No daily bar for {symbol} on {trade_date}")

    outcome = SnapshotService(repo, MissingBarProvider()).generate_snapshot_or_gap(account.id, date(2026, 7, 28))

    assert outcome.status == "valuation_gap"
    assert repo.list_snapshots(account.id) == []
    gap = repo.get_valuation_gap(account.id, date(2026, 7, 28))
    assert gap is not None
    assert gap.missing_symbols == ["300996"]
    assert repo.list_trades(account.id) == []
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")


def test_missing_bar_details_support_legacy_position_without_market():
    trade_date = date(2026, 7, 28)

    class MissingBarProvider:
        def get_daily_bar(self, symbol, trade_date, market=None):
            assert market is None
            raise KeyError(f"No daily bar for {symbol} on {trade_date}")

    class LegacyPosition:
        symbol = "300996"
        total_quantity = 100

    class Repository:
        def get_positions(self, account_id):
            return [LegacyPosition()]

        def upsert_valuation_gap(self, account_id, requested_date, missing_symbols, details):
            return SimpleNamespace(
                account_id=account_id,
                trade_date=requested_date,
                missing_symbols=missing_symbols,
                details=details,
            )

    outcome = SnapshotService(cast(Any, Repository()), cast(Any, MissingBarProvider())).generate_snapshot_or_gap(
        1, trade_date
    )

    assert outcome.status == "valuation_gap"
    assert outcome.valuation_gap is not None
    assert outcome.valuation_gap.details == [
        {"symbol": "300996", "market": None, "error": "'No daily bar for 300996 on 2026-07-28'"}
    ]


def test_missing_same_symbol_bars_are_market_qualified_and_deterministic(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("two-market-gap", Decimal("100000.00"))
    trade_date = date(2026, 7, 28)
    repo.upsert_position(account.id, Market.HK_CONNECT, "000001", 200, 0, Decimal("1600.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("900.00"))

    class MissingBarProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError(f"No daily bar for {market}:{symbol} on {trade_date}")

    outcome = SnapshotService(repo, MissingBarProvider()).generate_snapshot_or_gap(account.id, trade_date)

    assert outcome.status == "valuation_gap"
    assert outcome.valuation_gap is not None
    assert outcome.valuation_gap.missing_symbols == ["000001", "000001"]
    assert outcome.valuation_gap.details == [
        {
            "symbol": "000001",
            "market": "a_share",
            "error": "'No daily bar for a_share:000001 on 2026-07-28'",
        },
        {
            "symbol": "000001",
            "market": "hk_connect",
            "error": "'No daily bar for hk_connect:000001 on 2026-07-28'",
        },
    ]
