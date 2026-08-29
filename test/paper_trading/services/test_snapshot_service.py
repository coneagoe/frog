from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest
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
from paper_trading.domain.enums import CashEventType, Market, SnapshotPointType, SnapshotQualityStatus
from paper_trading.services.snapshot_service import SnapshotService, _validated_trading_nav
from paper_trading.storage.market_data import DailyBar, StorageMarketDataProvider
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


def test_generate_snapshot_preserves_high_precision_cash_after_reload(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_precision.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    cash = Decimal("123456.789012345678")
    account = repo.create_account("precise-cash", cash)

    snapshot = SnapshotService(repo, FakeMarketDataProvider()).generate_snapshot(account.id, date(2026, 8, 25))
    session.commit()
    snapshot_id = snapshot.id
    session.close()

    reloaded_session = sessionmaker(bind=engine)()
    reloaded = reloaded_session.get(type(snapshot), snapshot_id)
    assert reloaded is not None
    assert reloaded.cash_available == Decimal("123456.789012345995")
    assert reloaded.total_assets == Decimal("123456.789012345995")
    assert reloaded.cumulative_deposit == Decimal("123456.789012345675")
    assert reloaded.net_cash_flow == Decimal("123456.789012345675")
    reloaded_session.close()
    engine.dispose()


def test_snapshot_values_etf_position_from_etf_daily_bar(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshot_etf.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repo = PaperTradingRepository(session)
    account = repo.create_account("etf-demo", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.ETF, "510300", 100, 0, Decimal("300.00"))
    storage = FakeHistoryStorage(
        {},
        etf_daily_data={
            "510300": pd.DataFrame(
                {
                    COL_STOCK_ID: ["510300"],
                    COL_DATE: ["2026-08-10"],
                    COL_OPEN: [3.0],
                    COL_HIGH: [3.2],
                    COL_LOW: [2.9],
                    COL_CLOSE: [3.1],
                }
            )
        },
    )
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 8, 10)]))

    snapshot = SnapshotService(repo, market_data).generate_snapshot(account.id, date(2026, 8, 10))

    assert snapshot.market_value == Decimal("310.0000")
    assert storage.etf_daily_calls == [("510300", "2026-08-10", "2026-08-10")]
    assert storage.etf_calls == []
    assert storage.calls == []
    assert storage.hk_calls == []
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

    assert snapshot.point_type == SnapshotPointType.TRADING.value
    assert snapshot.quality_status == SnapshotQualityStatus.VALID.value
    assert snapshot.invalid_reason is None
    assert snapshot.event_at.tzinfo == timezone.utc
    assert snapshot.total_assets == Decimal("101000.0000")
    assert snapshot.share_count == Decimal("100000.000000")
    assert snapshot.net_asset_value == Decimal("1.010000")
    assert snapshot.cumulative_deposit == Decimal("100000.0000")
    assert snapshot.cumulative_withdrawal == Decimal("0.0000")
    assert snapshot.net_cash_flow == Decimal("100000.0000")
    assert account.net_asset_value == Decimal("1.010000")
    engine.dispose()


def test_generate_snapshot_updates_trading_point_for_same_account_date(tmp_path):
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

    first = snapshot_service.generate_snapshot(account.id, date(2026, 6, 16))
    repo.upsert_position(account.id, Market.A_SHARE, "000001.SZ", 200, 0, Decimal("1800.00"))
    snapshot = snapshot_service.generate_snapshot(account.id, date(2026, 6, 16))
    session.commit()

    snapshots = repo.list_snapshots(account.id)
    assert [row.point_type for row in snapshots] == [
        SnapshotPointType.INITIAL.value,
        SnapshotPointType.TRADING.value,
    ]
    assert first.id == snapshot.id
    assert snapshot.market_value == Decimal("2000.0000")
    assert snapshot.total_assets == Decimal("102000.0000")
    assert snapshot.unrealized_pnl == Decimal("200.0000")
    assert snapshot.point_type == SnapshotPointType.TRADING.value
    assert snapshot.quality_status == SnapshotQualityStatus.VALID.value
    assert snapshot.invalid_reason is None
    engine.dispose()


def test_suspended_position_uses_prior_close_and_marks_snapshot_stale(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("suspended-stale", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class SuspendedProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError("no bar")

        def is_symbol_suspended(self, symbol, trade_date, market=None):
            return True

        def get_latest_daily_close_with_date(self, symbol, trade_date, market=None):
            return Decimal("10.25"), date(2026, 8, 22)

    result = SnapshotService(repo, SuspendedProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert result.status == "complete"
    assert result.snapshot is not None
    assert result.snapshot.valuation_quality == "stale_suspended"
    assert result.snapshot.valuation_details == [
        {
            "symbol": "300996",
            "market": "a_share",
            "requested_date": "2026-08-25",
            "source_date": "2026-08-22",
            "reason": "suspended_prior_close",
        }
    ]


@pytest.mark.parametrize("prior_close", ["10.25", 10.25])
def test_suspended_position_normalizes_prior_close_to_decimal(sqlite_session, prior_close):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("suspended-normalized", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class SuspendedProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError("no bar")

        def is_symbol_suspended(self, symbol, trade_date, market=None):
            return True

        def get_latest_daily_close_with_date(self, symbol, trade_date, market=None):
            return prior_close, date(2026, 8, 22)

    result = SnapshotService(repo, SuspendedProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert result.status == "complete"
    assert result.snapshot is not None
    assert result.snapshot.market_value == Decimal("1025.0000")


@pytest.mark.parametrize("prior_close", [None, "not-a-number", Decimal("NaN"), Decimal("Infinity"), 0, -1])
def test_invalid_suspended_prior_close_creates_deterministic_gap(sqlite_session, prior_close):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("suspended-invalid", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class SuspendedProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError("no bar")

        def is_symbol_suspended(self, symbol, trade_date, market=None):
            return True

        def get_latest_daily_close_with_date(self, symbol, trade_date, market=None):
            return prior_close, date(2026, 8, 22)

    result = SnapshotService(repo, SuspendedProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert result.status == "valuation_gap"
    assert result.valuation_gap is not None
    assert result.valuation_gap.details[0]["reason"] == "market_data_error"


@pytest.mark.parametrize(
    "source_date",
    [None, "2026-08-22", datetime(2026, 8, 22), date(2026, 8, 26)],
)
def test_invalid_suspended_prior_close_source_date_creates_deterministic_gap(sqlite_session, source_date):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("suspended-invalid-source-date", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class SuspendedProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError("no bar")

        def is_symbol_suspended(self, symbol, trade_date, market=None):
            return True

        def get_latest_daily_close_with_date(self, symbol, trade_date, market=None):
            return Decimal("10.25"), source_date

    trade_date = date(2026, 8, 25)
    result = SnapshotService(repo, SuspendedProvider()).generate_snapshot_or_gap(account.id, trade_date)

    assert result.status == "valuation_gap"
    assert result.snapshot is None
    assert result.valuation_gap is not None
    assert result.valuation_gap.details == [
        {
            "symbol": "300996",
            "market": "a_share",
            "requested_date": "2026-08-25",
            "source_date": None,
            "reason": "invalid_source_date",
        }
    ]
    assert [snapshot.point_type for snapshot in repo.list_snapshots(account.id)] == [SnapshotPointType.INITIAL.value]


@pytest.mark.parametrize("method", ["is_symbol_suspended", "get_latest_daily_close_with_date"])
def test_suspended_prior_close_provider_exceptions_create_deterministic_gap(sqlite_session, method):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("suspended-error", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class FailingProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError("no bar")

        def is_symbol_suspended(self, symbol, trade_date, market=None):
            if method == "is_symbol_suspended":
                raise RuntimeError("suspension lookup failed")
            return True

        def get_latest_daily_close_with_date(self, symbol, trade_date, market=None):
            if method == "get_latest_daily_close_with_date":
                raise RuntimeError("prior close lookup failed")
            return Decimal("10.25"), date(2026, 8, 22)

    result = SnapshotService(repo, FailingProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert result.status == "valuation_gap"
    assert result.valuation_gap is not None
    assert result.valuation_gap.details[0]["reason"] == "market_data_error"


def test_unmarked_missing_bar_creates_gap_even_with_prior_close(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("missing-gap", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class MissingProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError("no bar")

        def is_symbol_suspended(self, symbol, trade_date, market=None):
            return False

        def get_latest_daily_close_with_date(self, symbol, trade_date, market=None):
            return Decimal("10.25"), date(2026, 8, 22)

    result = SnapshotService(repo, MissingProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert result.status == "valuation_gap"
    assert result.snapshot is None
    snapshots = repo.list_snapshots(account.id)
    assert [snapshot.point_type for snapshot in snapshots] == [SnapshotPointType.INITIAL.value]


def test_truthy_non_boolean_suspension_does_not_permit_prior_close(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("truthy-suspension", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))

    class TruthySuspensionProvider(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise KeyError("no bar")

        def is_symbol_suspended(self, symbol, trade_date, market=None):
            return "yes"

        def get_latest_daily_close_with_date(self, symbol, trade_date, market=None):
            pytest.fail("prior close must not be requested without boolean True")

    result = SnapshotService(repo, TruthySuspensionProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert result.status == "valuation_gap"
    assert result.snapshot is None
    assert result.valuation_gap is not None
    assert result.valuation_gap.details[0]["reason"] == "missing_exact_bar"


def test_revised_close_updates_existing_snapshot_in_place(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("revised-close", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.A_SHARE, "300996", 100, 0, Decimal("900.00"))
    market_data = FakeMarketDataProvider(
        {
            ("300996", date(2026, 8, 25)): DailyBar(
                "300996", date(2026, 8, 25), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10")
            )
        }
    )
    service = SnapshotService(repo, market_data)

    first = service.generate_snapshot_or_gap(account.id, date(2026, 8, 25)).snapshot
    assert first is not None
    first_market_value = first.market_value
    market_data._bars[("300996", date(2026, 8, 25))] = DailyBar(
        "300996", date(2026, 8, 25), Decimal("11"), Decimal("11"), Decimal("11"), Decimal("11")
    )
    second = service.generate_snapshot_or_gap(account.id, date(2026, 8, 25)).snapshot

    assert second is not None
    assert second.id == first.id
    assert second.market_value > first_market_value


def test_snapshot_includes_pending_settlement(sqlite_session):
    """Snapshot total_assets must include pending settlement amount."""
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("pending-snap", Decimal("100000.00"))
    amount = Decimal("123456.789012345678")
    persisted_amount = Decimal("123456.789012346000")
    repo.create_pending_settlement(
        account_id=account.id,
        amount=amount,
        expected_settle_date=date(2026, 7, 23),
        trade_id=1,
        source="hk_sell",
    )
    md = FakeMarketDataProvider()
    snapshot_service = SnapshotService(repo, md)
    snapshot = snapshot_service.generate_snapshot(account.id, date(2026, 7, 21))

    assert repo.get_pending_settlement_total_internal(account.id) == persisted_amount
    assert snapshot.pending_settlement == persisted_amount
    # total_assets includes cash_available + cash_frozen + market_value + pending_settlement
    assert snapshot.total_assets == persisted_amount + Decimal("100000.00")


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
    snapshots = repo.list_snapshots(account.id)
    assert [row.point_type for row in snapshots] == [SnapshotPointType.INITIAL.value]
    gap = repo.get_valuation_gap(account.id, date(2026, 7, 28))
    assert gap is not None
    assert gap.missing_symbols == ["300996"]
    assert repo.list_trades(account.id) == []
    assert repo.get_cash_available(account.id) == Decimal("100000.0000")


def test_missing_etf_snapshot_bar_creates_etf_qualified_valuation_gap(sqlite_session):
    Base.metadata.create_all(sqlite_session.get_bind())
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("missing-etf", Decimal("100000.00"))
    repo.upsert_position(account.id, Market.ETF, "510300", 100, 0, Decimal("300.00"))

    class MissingETFBarProvider(FakeMarketDataProvider):
        def __init__(self):
            super().__init__()
            self.calls: list[tuple[str, str | None]] = []

        def get_daily_bar(self, symbol, trade_date, market=None):
            self.calls.append((symbol, market))
            raise KeyError(f"No ETF daily bar for {symbol} on {trade_date}")

    market_data = MissingETFBarProvider()
    outcome = SnapshotService(repo, market_data).generate_snapshot_or_gap(account.id, date(2026, 8, 10))

    assert outcome.status == "valuation_gap"
    assert outcome.valuation_gap is not None
    assert market_data.calls == [("510300", "etf")]
    assert outcome.valuation_gap.details == [
        {
            "symbol": "510300",
            "market": "etf",
            "requested_date": "2026-08-10",
            "source_date": None,
            "reason": "missing_exact_bar",
        }
    ]


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
        {
            "symbol": "300996",
            "market": None,
            "requested_date": "2026-07-28",
            "source_date": None,
            "reason": "missing_exact_bar",
        }
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
            "requested_date": "2026-07-28",
            "source_date": None,
            "reason": "missing_exact_bar",
        },
        {
            "symbol": "000001",
            "market": "hk_connect",
            "requested_date": "2026-07-28",
            "source_date": None,
            "reason": "missing_exact_bar",
        },
    ]


def test_generate_snapshot_sets_explicit_utc_trading_metadata(sqlite_session, monkeypatch):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("utc-meta", Decimal("100000.00"))
    frozen = datetime(2026, 8, 25, 15, 30, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr("paper_trading.services.snapshot_service.datetime", FrozenDateTime)

    snapshot = SnapshotService(repo, FakeMarketDataProvider()).generate_snapshot(account.id, date(2026, 8, 25))

    assert snapshot.event_at == frozen
    assert snapshot.event_at.tzinfo == timezone.utc
    assert snapshot.point_type == SnapshotPointType.TRADING.value
    assert snapshot.quality_status == SnapshotQualityStatus.VALID.value
    assert snapshot.invalid_reason is None
    assert snapshot.net_asset_value == Decimal("1.000000")


def test_snapshot_with_non_positive_or_non_finite_nav_is_invalid(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("missing-shares", Decimal("100000.00"))
    previous_nav = account.net_asset_value
    account.share_count = Decimal("0")

    snapshot = SnapshotService(repo, FakeMarketDataProvider()).generate_snapshot(account.id, date(2026, 8, 25))

    assert snapshot.quality_status == SnapshotQualityStatus.INVALID.value
    assert snapshot.point_type == SnapshotPointType.TRADING.value
    assert snapshot.net_asset_value is None
    assert snapshot.invalid_reason == "missing_share_state"
    assert snapshot.total_assets == Decimal("100000.0000")
    assert snapshot.net_asset_value != snapshot.total_assets
    assert account.net_asset_value == previous_nav


@pytest.mark.parametrize(
    ("cash_adjustment", "expected_assets"),
    [
        (Decimal("-100000.00"), Decimal("0.0000")),
        (Decimal("-150000.00"), Decimal("-50000.0000")),
    ],
)
def test_snapshot_with_zero_or_negative_nav_is_invalid(sqlite_session, cash_adjustment, expected_assets):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("non-positive-nav", Decimal("100000.00"))
    previous_nav = account.net_asset_value
    repo.add_cash_event(account.id, CashEventType.FEE, cash_adjustment)

    snapshot = SnapshotService(repo, FakeMarketDataProvider()).generate_snapshot(account.id, date(2026, 8, 25))

    assert snapshot.quality_status == SnapshotQualityStatus.INVALID.value
    assert snapshot.net_asset_value is None
    assert snapshot.invalid_reason == "non_positive_nav"
    assert snapshot.total_assets == expected_assets
    assert snapshot.net_asset_value != snapshot.total_assets
    assert account.net_asset_value == previous_nav


def _fake_snapshot_repo(account: SimpleNamespace, *, cash_available: Decimal = Decimal("100000")):
    saved: dict[str, Any] = {}

    class Repository:
        updated = False

        def get_cash_available_internal(self, account_id):
            return cash_available

        def get_cash_frozen_internal(self, account_id):
            return Decimal("0")

        def get_pending_settlement_total_internal(self, account_id):
            return Decimal("0")

        def get_positions(self, account_id):
            return []

        def get_account(self, account_id):
            return account

        def count_orders(self, account_id, trade_date):
            return 0

        def count_trades(self, account_id, trade_date):
            return 0

        def update_account_nav_state(self, *args, **kwargs):
            self.updated = True

        def save_snapshot(self, **values):
            saved.update(values)
            return SimpleNamespace(**values)

        save_trading_snapshot = save_snapshot

    return Repository(), saved


def _trading_account(**overrides: Any) -> SimpleNamespace:
    values = {
        "id": 1,
        "share_count": Decimal("100000"),
        "net_asset_value": Decimal("1.000000"),
        "realized_pnl": Decimal("0"),
        "cumulative_deposit": Decimal("100000"),
        "cumulative_withdrawal": Decimal("0"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("cash", [Decimal("NaN"), Decimal("Infinity")])
def test_snapshot_with_non_finite_nav_is_invalid(cash):
    repo, saved = _fake_snapshot_repo(_trading_account(), cash_available=cash)
    snapshot = SnapshotService(cast(Any, repo), FakeMarketDataProvider()).generate_snapshot(1, date(2026, 8, 25))

    assert snapshot.quality_status == SnapshotQualityStatus.INVALID.value
    assert snapshot.net_asset_value is None
    assert snapshot.invalid_reason == "non_finite_nav"
    assert snapshot.net_asset_value != snapshot.total_assets
    assert repo.updated is False
    assert saved["net_asset_value"] is None


@pytest.mark.parametrize("share_count", [None, Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_snapshot_with_invalid_share_count_persists_missing_share_state(share_count):
    account = _trading_account(share_count=share_count)
    repo, saved = _fake_snapshot_repo(account)
    snapshot = SnapshotService(cast(Any, repo), FakeMarketDataProvider()).generate_snapshot(1, date(2026, 8, 25))

    assert snapshot.quality_status == SnapshotQualityStatus.INVALID.value
    assert snapshot.point_type == SnapshotPointType.TRADING.value
    assert snapshot.event_at.tzinfo == timezone.utc
    assert snapshot.net_asset_value is None
    assert snapshot.invalid_reason == "missing_share_state"
    assert snapshot.total_assets == Decimal("100000.0000")
    assert snapshot.net_asset_value != snapshot.total_assets
    assert repo.updated is False
    assert saved["net_asset_value"] is None
    assert saved["invalid_reason"] == "missing_share_state"


def test_validated_trading_nav_maps_invalid_conditions():
    assert _validated_trading_nav(None, Decimal("1")) == (None, "missing_share_state")
    assert _validated_trading_nav(Decimal("0"), Decimal("1")) == (None, "missing_share_state")
    assert _validated_trading_nav(Decimal("NaN"), Decimal("1")) == (None, "missing_share_state")
    assert _validated_trading_nav(Decimal("Infinity"), Decimal("1")) == (None, "missing_share_state")
    assert _validated_trading_nav(Decimal("100"), None) == (None, "missing_nav")
    assert _validated_trading_nav(Decimal("100"), Decimal("NaN")) == (None, "non_finite_nav")
    assert _validated_trading_nav(Decimal("100"), Decimal("Infinity")) == (None, "non_finite_nav")
    assert _validated_trading_nav(Decimal("100"), Decimal("0")) == (None, "non_positive_nav")
    assert _validated_trading_nav(Decimal("100"), Decimal("-1")) == (None, "non_positive_nav")
    assert _validated_trading_nav(Decimal("100"), Decimal("1.25")) == (Decimal("1.25"), None)
