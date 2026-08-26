from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationService
from paper_trading.services.snapshot_service import SnapshotOutcome, SnapshotService
from paper_trading.storage.models import PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from test.paper_trading.fakes import FakeMarketDataProvider


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


def test_recalculation_classifies_unavailable_and_failed_dates():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = object()
    snapshot_service = MagicMock()
    snapshot_service.generate_snapshot_or_gap.side_effect = [
        SnapshotOutcome(status="valuation_gap"),
        RuntimeError("market data failed"),
    ]
    factory = MagicMock(return_value=session)

    with (
        patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo),
        patch("paper_trading.services.snapshot_recalculation_service.SnapshotService", return_value=snapshot_service),
    ):
        service = SnapshotRecalculationService(factory, MagicMock())
        with patch.object(
            service,
            "_dates_with_valuation_state",
            return_value=[date(2026, 8, 25), date(2026, 8, 26)],
        ):
            result = service.recalculate(1, date(2026, 8, 25), date(2026, 8, 26))

    assert result.unavailable_dates == [date(2026, 8, 25)]
    assert result.failed_dates == [date(2026, 8, 26)]
    assert result.errors == ["2026-08-26: market data failed"]


def test_recalculation_does_not_invoke_matching_order_ledger_or_settlement():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = object()
    snapshot_service = MagicMock()
    snapshot_service.generate_snapshot_or_gap.return_value = SnapshotOutcome(status="complete")
    forbidden = {
        name: MagicMock()
        for name in ("MatchingService", "OrderDeleteService", "LedgerRebuildService", "HkSettlementService")
    }

    with (
        patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo),
        patch("paper_trading.services.snapshot_recalculation_service.SnapshotService", return_value=snapshot_service),
        patch("paper_trading.services.matching_service.MatchingService", forbidden["MatchingService"]),
        patch("paper_trading.services.order_delete_service.OrderDeleteService", forbidden["OrderDeleteService"]),
        patch("paper_trading.services.ledger_rebuild_service.LedgerRebuildService", forbidden["LedgerRebuildService"]),
        patch("paper_trading.services.hk_settlement_service.HkSettlementService", forbidden["HkSettlementService"]),
    ):
        service = SnapshotRecalculationService(MagicMock(return_value=session), MagicMock())
        with patch.object(service, "_dates_with_valuation_state", return_value=[date(2026, 8, 25)]):
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
