import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import OrderSide, OrderStatus, PositionSource
from paper_trading.services.nav_series import NavSeriesBuilder
from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.enum_migration import migrate_paper_trading_enums
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import (
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperCorporateAction,
    PaperOrder,
    PaperPendingSettlement,
    PaperPosition,
    PaperPositionLot,
    PaperTrade,
    PaperValuationGap,
)
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeMarketDataProvider, MarketDataProviderCompatibility


def _sqlite_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'recalculation.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_recalculation_selects_only_bounded_repository_dates_and_is_idempotent(tmp_path):
    factory = _sqlite_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("recalculation", Decimal("100000"))
        snapshot_service = SnapshotService(repo, FakeMarketDataProvider())
        for trade_date in (date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 27)):
            snapshot_service.generate_snapshot(account.id, trade_date)
        repo.upsert_valuation_gap(account.id, date(2026, 8, 26), ["000001"], [])
        repo.upsert_valuation_gap(account.id, date(2026, 8, 28), ["000001"], [])
        account_id = account.id
        session.commit()
    finally:
        session.close()

    session = factory()
    try:
        out_of_range_gap = (
            session.query(PaperValuationGap).filter_by(account_id=account_id, trade_date=date(2026, 8, 28)).one()
        )
        assert out_of_range_gap.resolved is False
    finally:
        session.close()

    service = SnapshotRecalculationService(factory, FakeMarketDataProvider())
    result = service.recalculate(account_id, date(2026, 8, 25), date(2026, 8, 27))

    assert result.updated_dates == [date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)]
    assert result.unavailable_dates == []
    assert result.failed_dates == []

    session = factory()
    try:
        rows = PaperTradingRepository(session).list_snapshots(account_id)
        trading_rows = [row for row in rows if row.point_type == "trading"]
        ids_by_date = {row.trade_date: row.id for row in trading_rows}
        count = len(trading_rows)
    finally:
        session.close()

    repeated = service.recalculate(account_id, date(2026, 8, 25), date(2026, 8, 27))
    assert repeated.updated_dates == result.updated_dates

    session = factory()
    try:
        rows = [
            row for row in PaperTradingRepository(session).list_snapshots(account_id) if row.point_type == "trading"
        ]
        assert len(rows) == count
        assert {row.trade_date: row.id for row in rows} == ids_by_date
    finally:
        session.close()


def test_recalculation_includes_event_date_and_later_snapshot_and_gap(tmp_path):
    factory = _sqlite_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("event-date-recalculation", Decimal("100000"))
        repo.upsert_position(account.id, "a_share", "000001", 100, 0, Decimal("1000"))
        repo.create_position_lot(account.id, "a_share", "000001", date(2026, 8, 1), 100, 100, Decimal("10"))
        SnapshotService(repo, FakeMarketDataProvider()).generate_snapshot(account.id, date(2026, 8, 28))
        repo.upsert_valuation_gap(account.id, date(2026, 8, 29), ["000001"], [{"reason": "missing"}])
        account_id = account.id
        session.commit()
    finally:
        session.close()

    result = SnapshotRecalculationService(factory, FakeMarketDataProvider()).recalculate(
        account_id, date(2026, 8, 27), date(2026, 8, 29)
    )

    assert result.updated_dates == [date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 29)]
    assert result.unavailable_dates == []
    assert result.failed_dates == []
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        trading_dates = sorted(row.trade_date for row in repo.list_snapshots(account_id) if row.point_type == "trading")
        assert trading_dates == [date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 29)]
        gap = repo.get_valuation_gap(account_id, date(2026, 8, 29))
        assert gap is not None and gap.resolved is True
    finally:
        session.close()


def test_recalculation_classifies_unavailable_and_failed_dates():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = object()
    factory = MagicMock(return_value=session)

    with (
        patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo),
    ):
        service = SnapshotRecalculationService(factory, MagicMock())
        with patch.object(
            service,
            "_dates_with_valuation_state",
            return_value=[date(2026, 8, 25), date(2026, 8, 26)],
        ):
            with pytest.raises(ValueError, match="baseline"):
                service.recalculate(1, date(2026, 8, 25), date(2026, 8, 26))

    session.rollback.assert_called_once()


def test_historical_recalculation_preserves_live_nav_and_event_order(tmp_path):
    factory = _sqlite_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("historical-recalculation", Decimal("100000"))
        snapshot_service = SnapshotService(repo, FakeMarketDataProvider())
        older = snapshot_service.generate_snapshot(account.id, date(2026, 8, 25))
        newer = snapshot_service.generate_snapshot(account.id, date(2026, 8, 26))
        old_event_at = older.event_at
        newer_event_at = newer.event_at
        account.share_count = Decimal("120000.000000")
        account.net_asset_value = Decimal("1.250000")
        account_id = account.id
        session.commit()
    finally:
        session.close()

    result = SnapshotRecalculationService(factory, FakeMarketDataProvider()).recalculate(
        account_id, date(2026, 8, 25), date(2026, 8, 25)
    )
    assert result.updated_dates == [date(2026, 8, 25)]

    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account_optional = repo.get_account(account_id)
        assert account_optional is not None
        account = account_optional
        assert account.share_count == Decimal("120000.000000")
        assert account.net_asset_value == Decimal("1.250000")
        trading = [row for row in repo.list_snapshots(account_id) if row.point_type == "trading"]
        assert [row.trade_date for row in trading] == [date(2026, 8, 25), date(2026, 8, 26)]
        assert [row.event_at.replace(tzinfo=timezone.utc) for row in trading] == [old_event_at, newer_event_at]
    finally:
        session.close()


@pytest.mark.parametrize(
    "close", [None, "not-a-number", Decimal("NaN"), Decimal("Infinity"), Decimal("0"), Decimal("-1")]
)
def test_invalid_close_creates_deterministic_valuation_gap(sqlite_session, close):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("invalid-close", Decimal("100000"))
    repo.upsert_position(account.id, "a_share", "000001", 100, 0, Decimal("900"))

    class InvalidCloseProvider(MarketDataProviderCompatibility):
        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
            return DailyBar(
                symbol,
                trade_date,
                Decimal("10"),
                Decimal("10"),
                Decimal("10"),
                cast(Decimal, close),
            )

    outcome = SnapshotService(repo, InvalidCloseProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert outcome.status == "valuation_gap"
    assert outcome.valuation_gap is not None
    assert outcome.valuation_gap.details == [
        {
            "symbol": "000001",
            "market": "a_share",
            "requested_date": "2026-08-25",
            "source_date": None,
            "reason": "invalid_close",
        }
    ]


def test_market_data_exception_creates_deterministic_valuation_gap(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("provider-error", Decimal("100000"))
    repo.upsert_position(account.id, "a_share", "000001", 100, 0, Decimal("900"))

    class FailingProvider(MarketDataProviderCompatibility):
        def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None):
            raise RuntimeError("provider unavailable")

    outcome = SnapshotService(repo, FailingProvider()).generate_snapshot_or_gap(account.id, date(2026, 8, 25))

    assert outcome.status == "valuation_gap"
    assert outcome.valuation_gap is not None
    assert outcome.valuation_gap.details[0]["reason"] == "market_data_error"


def test_recalculation_does_not_invoke_matching_order_ledger_or_settlement():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = object()
    forbidden = {
        name: MagicMock()
        for name in ("MatchingService", "OrderDeleteService", "LedgerRebuildService", "HkSettlementService")
    }

    with (
        patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo),
        patch("paper_trading.services.matching_service.MatchingService", forbidden["MatchingService"]),
        patch("paper_trading.services.order_delete_service.OrderDeleteService", forbidden["OrderDeleteService"]),
        patch("paper_trading.services.ledger_rebuild_service.LedgerRebuildService", forbidden["LedgerRebuildService"]),
        patch("paper_trading.services.hk_settlement_service.HkSettlementService", forbidden["HkSettlementService"]),
    ):
        service = SnapshotRecalculationService(MagicMock(return_value=session), MagicMock())
        with patch.object(service, "_dates_with_valuation_state", return_value=[date(2026, 8, 25)]):
            with pytest.raises(ValueError, match="baseline"):
                service.recalculate(1, date(2026, 8, 25), date(2026, 8, 25))

    for constructor in forbidden.values():
        constructor.assert_not_called()


def test_recalculation_rejects_inverted_range():
    with pytest.raises(ValueError, match="start_date"):
        SnapshotRecalculationService(MagicMock(), MagicMock()).recalculate(1, date(2026, 8, 26), date(2026, 8, 25))


def test_recalculation_rejects_unknown_account():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = None
    factory = MagicMock(return_value=session)

    with patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo):
        with pytest.raises(KeyError, match="not found"):
            SnapshotRecalculationService(factory, MagicMock()).recalculate(1, date(2026, 8, 25), date(2026, 8, 25))


def test_recalculation_rolls_back_external_session_on_replay_failure():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = object()
    repo.list_replay_events.return_value = []

    with patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo):
        with pytest.raises(ValueError, match="baseline"):
            SnapshotRecalculationService(MagicMock(), MagicMock()).recalculate(
                1, date(2026, 8, 25), date(2026, 8, 25), session=session
            )

    session.rollback.assert_called_once()


def test_recalculation_classifies_provider_failure_as_failed_not_unavailable(tmp_path):
    factory = _sqlite_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("provider-failure-recalc", Decimal("100"))
        repo.create_trade(
            1,
            account.id,
            "000001",
            OrderSide.BUY,
            10,
            Decimal("10"),
            Decimal("100"),
            Decimal("0"),
            date(2026, 8, 25),
            trade_time=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        account_id = account.id
        session.commit()
    finally:
        session.close()

    class ProviderFailure(MarketDataProviderCompatibility):
        def get_daily_bar(self, symbol, trade_date, market=None):
            raise RuntimeError("provider down")

    with pytest.raises(RuntimeError, match="failed"):
        SnapshotRecalculationService(factory, ProviderFailure()).recalculate(
            account_id, date(2026, 8, 25), date(2026, 8, 25)
        )


def test_recalculation_uses_pending_settlement_business_date_after_settlement(tmp_path):
    factory = _sqlite_factory(tmp_path)
    session = factory()
    trade_date = date.today() - timedelta(days=3)
    settle_date = date.today() + timedelta(days=2)
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("settlement-business-date", Decimal("1000"))
        buy = repo.create_trade(
            1,
            account.id,
            "000001",
            OrderSide.BUY,
            10,
            Decimal("10"),
            Decimal("100"),
            Decimal("5"),
            trade_date,
            market="hk_connect",
            trade_time=datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc),
        )
        sell = repo.create_trade(
            1,
            account.id,
            "000001",
            OrderSide.SELL,
            10,
            Decimal("12"),
            Decimal("120"),
            Decimal("1"),
            trade_date,
            market="hk_connect",
            trade_time=datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc).replace(minute=1),
        )
        repo.add_cash_event(
            account.id,
            "freeze",
            Decimal("-105"),
            trade_id=buy.id,
            trade_date=trade_date,
            occurred_at=datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc),
        )
        pending = repo.create_pending_settlement(account.id, Decimal("119"), settle_date, trade_id=sell.id)
        repo.settle_pending(pending.id)
        account_id = account.id
        session.commit()
    finally:
        session.close()

    result = SnapshotRecalculationService(factory, FakeMarketDataProvider()).recalculate(
        account_id, trade_date, settle_date
    )

    assert result.updated_dates == [trade_date + timedelta(days=offset) for offset in range(6)]
    session = factory()
    try:
        replay_events = NavSeriesBuilder(repo=PaperTradingRepository(session)).prepare(account_id)[0]
        settlement = next(
            event
            for event in replay_events
            if event.source_id.startswith("paper_cash_ledger:") and event.payload.get("ledger_event_type") == "trade"
        )
        assert settlement.trade_date == settle_date
        assert settlement.event_at.date() == settle_date
        snapshots = {
            row.trade_date: row
            for row in PaperTradingRepository(session).list_snapshots(account_id)
            if row.point_type == "trading"
        }
        assert snapshots[settle_date].cash_available == Decimal("1014")
        assert snapshots[settle_date].pending_settlement == Decimal("0")
    finally:
        session.close()


def test_recalculation_preserves_initial_cash_components_and_identity(tmp_path):
    factory = _sqlite_factory(tmp_path)
    session = factory()
    trade_date = date.today() + timedelta(days=1)
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("initial-component-recalc", Decimal("100"))
        initial = next(row for row in repo.list_snapshots(account.id) if row.point_type == "initial")
        initial.cash_available = Decimal("70")
        initial.cash_frozen = Decimal("10")
        initial.pending_settlement = Decimal("20")
        initial.total_assets = Decimal("100")
        initial.cumulative_deposit = Decimal("0")
        initial.cumulative_withdrawal = Decimal("0")
        account_id = account.id
        session.commit()
    finally:
        session.close()

    result = SnapshotRecalculationService(factory, FakeMarketDataProvider()).recalculate(
        account_id, trade_date, trade_date
    )

    assert result.updated_dates == [trade_date]
    session = factory()
    try:
        snapshot = next(
            row
            for row in PaperTradingRepository(session).list_snapshots(account_id)
            if row.point_type == "trading" and row.trade_date == trade_date
        )
        assert snapshot.cash_available == Decimal("70")
        assert snapshot.cash_frozen == Decimal("10")
        assert snapshot.pending_settlement == Decimal("20")
        assert snapshot.total_assets == Decimal("100")
        assert snapshot.cash_available + snapshot.cash_frozen + snapshot.pending_settlement + snapshot.market_value == (
            snapshot.total_assets
        )
        assert snapshot.cumulative_deposit == Decimal("0")
        assert snapshot.cumulative_withdrawal == Decimal("0")
    finally:
        session.close()


def test_recalculation_restores_initial_position_holdings_and_cost(tmp_path):
    factory = _sqlite_factory(tmp_path)
    session = factory()
    trade_date = date.today() + timedelta(days=1)
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("initial-position-recalc", Decimal("100"))
        initial = next(row for row in repo.list_snapshots(account.id) if row.point_type == "initial")
        initial.cash_available = Decimal("90")
        initial.total_assets = Decimal("100")
        repo.upsert_position(
            account.id,
            "a_share",
            "000001",
            3,
            0,
            Decimal("18"),
            source=PositionSource.IMPORTED.value,
        )
        repo.create_position_lot(
            account.id,
            "a_share",
            "000001",
            date.today(),
            2,
            2,
            Decimal("4"),
            source=PositionSource.IMPORTED.value,
        )
        repo.create_trade(
            1,
            account.id,
            "000001",
            OrderSide.BUY,
            1,
            Decimal("10"),
            Decimal("10"),
            Decimal("0"),
            trade_date,
            trade_time=datetime.combine(trade_date, datetime.min.time(), tzinfo=timezone.utc),
        )
        account_id = account.id
        session.commit()
    finally:
        session.close()

    result = SnapshotRecalculationService(factory, FakeMarketDataProvider()).recalculate(
        account_id, trade_date, trade_date
    )

    assert result.updated_dates == [trade_date]
    session = factory()
    try:
        snapshot = next(
            row
            for row in PaperTradingRepository(session).list_snapshots(account_id)
            if row.point_type == "trading" and row.trade_date == trade_date
        )
        assert snapshot.market_value == Decimal("150")
        assert snapshot.total_assets == Decimal("230")
        replay_point = NavSeriesBuilder(repo=PaperTradingRepository(session)).build(account_id).points[-1]
        assert replay_point.holdings == {"a_share:000001": Decimal("3")}
        assert replay_point.costs == {"a_share:000001": Decimal("18")}
    finally:
        session.close()


def test_postgresql_recalculation_persists_snapshots_and_gaps():
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    schema_name = f"task3_recalc_{uuid.uuid4().hex}"
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema_name}"})
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        migrate_paper_trading_enums(connection)
    Base.metadata.create_all(
        engine,
        tables=[
            PaperAccount.__table__,
            PaperCashLedger.__table__,
            PaperAccountSnapshot.__table__,
            PaperValuationGap.__table__,
            PaperCorporateAction.__table__,
            PaperOrder.__table__,
            PaperTrade.__table__,
            PaperPendingSettlement.__table__,
            PaperPosition.__table__,
            PaperPositionLot.__table__,
        ],
    )
    factory = sessionmaker(bind=engine)
    session = factory()
    start_date = date(2026, 8, 25)
    end_date = date(2026, 8, 26)
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("postgres-recalculation", Decimal("100"))
        account_id = account.id
        session.commit()
        result = SnapshotRecalculationService(factory, FakeMarketDataProvider()).recalculate(
            account_id, start_date, end_date
        )
        assert result.updated_dates == [start_date, end_date]
        assert result.unavailable_dates == []
        assert result.failed_dates == []
        rows = [row for row in repo.list_snapshots(account_id) if row.point_type == "trading"]
        assert [row.trade_date for row in rows] == [start_date, end_date]
        assert all(row.total_assets == Decimal("100") for row in rows)
    finally:
        session.close()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        engine.dispose()


def test_postgresql_recalculation_preserves_initial_components_and_imported_holdings():
    url = os.getenv("TEST_POSTGRESQL_URL")
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    schema_name = f"task3_recalc_baseline_{uuid.uuid4().hex}"
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema_name}"})
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        migrate_paper_trading_enums(connection)
    Base.metadata.create_all(
        engine,
        tables=[
            PaperAccount.__table__,
            PaperCashLedger.__table__,
            PaperAccountSnapshot.__table__,
            PaperValuationGap.__table__,
            PaperCorporateAction.__table__,
            PaperOrder.__table__,
            PaperTrade.__table__,
            PaperPendingSettlement.__table__,
            PaperPosition.__table__,
            PaperPositionLot.__table__,
        ],
    )
    factory = sessionmaker(bind=engine)
    start_date = date(2026, 8, 25)
    try:
        session = factory()
        try:
            repo = PaperTradingRepository(session)
            account = repo.create_account("postgres-recalculation-baseline", Decimal("100"))
            initial = next(row for row in repo.list_snapshots(account.id) if row.point_type == "initial")
            initial.cash_available = Decimal("70")
            initial.cash_frozen = Decimal("10")
            initial.pending_settlement = Decimal("20")
            initial.total_assets = Decimal("100")
            initial.cumulative_deposit = Decimal("0")
            initial.cumulative_withdrawal = Decimal("0")
            repo.upsert_position(
                account.id,
                "a_share",
                "000001",
                3,
                0,
                Decimal("18"),
                source=PositionSource.IMPORTED.value,
            )
            repo.create_position_lot(
                account.id,
                "a_share",
                "000001",
                start_date,
                2,
                2,
                Decimal("4"),
                source=PositionSource.IMPORTED.value,
            )
            order = repo.create_order(
                account.id,
                "000001",
                OrderSide.BUY,
                1,
                Decimal("10"),
                start_date,
                OrderStatus.FILLED,
            )
            repo.create_trade(
                order.id,
                account.id,
                "000001",
                OrderSide.BUY,
                1,
                Decimal("10"),
                Decimal("10"),
                Decimal("0"),
                start_date,
                trade_time=datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
            )
            account_id = account.id
            session.commit()
        finally:
            session.close()

        service = SnapshotRecalculationService(factory, FakeMarketDataProvider())
        result = service.recalculate(account_id, start_date, start_date)
        assert result.updated_dates == [start_date]
        assert result.unavailable_dates == []
        assert result.failed_dates == []

        session = factory()
        try:
            repo = PaperTradingRepository(session)
            snapshot = next(
                row
                for row in repo.list_snapshots(account_id)
                if row.point_type == "trading" and row.trade_date == start_date
            )
            assert snapshot.cash_available == Decimal("70")
            assert snapshot.cash_frozen == Decimal("0")
            assert snapshot.pending_settlement == Decimal("20")
            assert snapshot.market_value == Decimal("150")
            assert snapshot.total_assets == Decimal("240")
            assert (
                snapshot.cash_available + snapshot.cash_frozen + snapshot.pending_settlement + snapshot.market_value
                == (snapshot.total_assets)
            )
            assert snapshot.share_count == Decimal("100")
            assert snapshot.cumulative_deposit == Decimal("0")
            assert snapshot.cumulative_withdrawal == Decimal("0")
            point = NavSeriesBuilder(repo=repo).build(account_id).points[-1]
            assert point.holdings == {"a_share:000001": Decimal("3")}
            assert point.costs == {"a_share:000001": Decimal("18")}
        finally:
            session.close()

        repeated = service.recalculate(account_id, start_date, start_date)
        assert repeated.updated_dates == [start_date]
        session = factory()
        try:
            snapshot = next(
                row
                for row in PaperTradingRepository(session).list_snapshots(account_id)
                if row.point_type == "trading" and row.trade_date == start_date
            )
            assert snapshot.cash_available == Decimal("70")
            assert snapshot.cash_frozen == Decimal("0")
            assert snapshot.pending_settlement == Decimal("20")
            assert snapshot.market_value == Decimal("150")
            assert snapshot.total_assets == Decimal("240")
        finally:
            session.close()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        engine.dispose()
