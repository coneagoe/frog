from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import SnapshotPointType
from paper_trading.schemas.repairs import TradingSnapshotTimestampRepairRequest
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.services.trading_snapshot_timestamp_repair_service import (
    MAX_REPAIR_CANDIDATES,
    TradingSnapshotTimestampRepairService,
)
from paper_trading.storage.models import PaperAccountSnapshot
from paper_trading.storage.repository import PaperTradingRepository, canonical_trading_snapshot_event_at
from storage.model.base import Base
from test.paper_trading.fakes import FakeMarketDataProvider


def _session_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'timestamp_repair.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_trading_snapshot(repo: PaperTradingRepository, account_id: int, trade_date: date) -> PaperAccountSnapshot:
    return SnapshotService(repo, FakeMarketDataProvider()).generate_snapshot(account_id, trade_date)


def test_request_defaults_end_date_and_rejects_inverted_range():
    request = TradingSnapshotTimestampRepairRequest(account_id=1, start_date=date(2026, 8, 25))

    assert request.end_date is None
    assert request.effective_end_date == date(2026, 8, 25)

    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        TradingSnapshotTimestampRepairRequest(
            account_id=1,
            start_date=date(2026, 8, 26),
            end_date=date(2026, 8, 25),
        )


def test_unknown_account_raises_key_error(tmp_path):
    service = TradingSnapshotTimestampRepairService(_session_factory(tmp_path))

    with pytest.raises(KeyError, match="paper account not found: 999"):
        service.run(999, date(2026, 8, 25))


def test_dry_run_leaves_noncanonical_snapshot_unchanged_and_reports_candidate(tmp_path):
    factory = _session_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repair-dry-run", Decimal("100000"))
        account_id = account.id
        trade_date = date(2026, 8, 25)
        snapshot = _seed_trading_snapshot(repo, account.id, trade_date)
        batch_time = datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc)
        snapshot.event_at = batch_time
        session.commit()
        snapshot_id = snapshot.id
    finally:
        session.close()

    result = TradingSnapshotTimestampRepairService(factory).run(account_id, trade_date)

    assert result.dry_run is True
    assert result.account_id == account_id
    assert result.start_date == trade_date
    assert result.end_date == trade_date
    assert result.matched_count == 1
    assert result.updated_count == 0
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.snapshot_id == snapshot_id
    assert candidate.trade_date == trade_date
    assert candidate.event_at == batch_time
    assert candidate.canonical_event_at == canonical_trading_snapshot_event_at(trade_date)

    session = factory()
    try:
        refreshed = session.get(PaperAccountSnapshot, snapshot_id)
        assert refreshed is not None
        assert refreshed.event_at.replace(tzinfo=timezone.utc) == batch_time
    finally:
        session.close()


def test_apply_repairs_only_requested_account_and_preserves_snapshot_ids(tmp_path):
    factory = _session_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repair-apply", Decimal("100000"))
        account_id = account.id
        other_account = repo.create_account("repair-apply-other", Decimal("100000"))
        other_account_id = other_account.id

        initial_snapshot = next(
            row for row in repo.list_snapshots(account.id) if row.point_type == SnapshotPointType.INITIAL.value
        )
        first = _seed_trading_snapshot(repo, account.id, date(2026, 8, 25))
        second = _seed_trading_snapshot(repo, account.id, date(2026, 8, 26))
        outside_range = _seed_trading_snapshot(repo, account.id, date(2026, 8, 28))
        foreign_snapshot = _seed_trading_snapshot(repo, other_account.id, date(2026, 8, 25))

        first.event_at = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
        second.event_at = datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc)
        outside_range.event_at = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        foreign_snapshot.event_at = datetime(2026, 9, 2, 13, 0, tzinfo=timezone.utc)
        session.commit()
        ids = {
            "initial": initial_snapshot.id,
            "first": first.id,
            "second": second.id,
            "outside": outside_range.id,
            "foreign": foreign_snapshot.id,
        }
        initial_event_at = initial_snapshot.event_at
    finally:
        session.close()

    service = TradingSnapshotTimestampRepairService(factory)
    result = service.run(account_id, date(2026, 8, 25), date(2026, 8, 26), apply=True)

    assert result.dry_run is False
    assert result.matched_count == 2
    assert result.updated_count == 2
    assert [candidate.snapshot_id for candidate in result.candidates] == [ids["first"], ids["second"]]

    session = factory()
    try:
        repo = PaperTradingRepository(session)
        refreshed = {row.id: row for row in repo.list_snapshots(account_id)}
        assert refreshed[ids["initial"]].event_at == initial_event_at
        assert refreshed[ids["first"]].event_at.replace(tzinfo=timezone.utc) == canonical_trading_snapshot_event_at(
            date(2026, 8, 25)
        )
        assert refreshed[ids["second"]].event_at.replace(tzinfo=timezone.utc) == canonical_trading_snapshot_event_at(
            date(2026, 8, 26)
        )
        assert refreshed[ids["outside"]].event_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 9, 2, 12, 0, tzinfo=timezone.utc
        )
        foreign = session.get(PaperAccountSnapshot, ids["foreign"])
        assert foreign is not None
        assert foreign.event_at.replace(tzinfo=timezone.utc) == datetime(2026, 9, 2, 13, 0, tzinfo=timezone.utc)
        assert [
            row.id
            for row in repo.list_trading_snapshots_in_date_range(account_id, date(2026, 8, 25), date(2026, 8, 28))
        ] == [
            ids["first"],
            ids["second"],
            ids["outside"],
        ]
        assert [
            row.id
            for row in repo.list_trading_snapshots_in_date_range(other_account_id, date(2026, 8, 25), date(2026, 8, 25))
        ] == [ids["foreign"]]
        assert refreshed[ids["first"]].id == ids["first"]
        assert refreshed[ids["second"]].id == ids["second"]
        assert refreshed[ids["initial"]].id == ids["initial"]
    finally:
        session.close()

    repeated = service.run(account_id, date(2026, 8, 25), date(2026, 8, 26), apply=True)
    assert repeated.matched_count == 0
    assert repeated.updated_count == 0
    assert repeated.candidates == []


def test_apply_rolls_back_all_changes_on_flush_failure(tmp_path, monkeypatch):
    factory = _session_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repair-rollback", Decimal("100000"))
        account_id = account.id
        first = _seed_trading_snapshot(repo, account.id, date(2026, 8, 25))
        second = _seed_trading_snapshot(repo, account.id, date(2026, 8, 26))
        first.event_at = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
        second.event_at = datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc)
        session.commit()
        snapshot_ids = [first.id, second.id]
    finally:
        session.close()

    failing_session = factory()

    def fail_flush():
        raise RuntimeError("flush failed")

    monkeypatch.setattr(failing_session, "flush", fail_flush)

    service = TradingSnapshotTimestampRepairService(lambda: failing_session)
    with pytest.raises(RuntimeError, match="flush failed"):
        service.run(account_id, date(2026, 8, 25), date(2026, 8, 26), apply=True)

    verifier = factory()
    try:
        repo = PaperTradingRepository(verifier)
        rows = {
            row.id: row
            for row in repo.list_trading_snapshots_in_date_range(account_id, date(2026, 8, 25), date(2026, 8, 26))
        }
        assert rows[snapshot_ids[0]].event_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 9, 3, 10, 0, tzinfo=timezone.utc
        )
        assert rows[snapshot_ids[1]].event_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 9, 3, 11, 0, tzinfo=timezone.utc
        )
    finally:
        verifier.close()


def test_matching_count_is_full_but_candidate_details_are_limited_and_sorted(tmp_path):
    factory = _session_factory(tmp_path)
    session = factory()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repair-many", Decimal("100000"))
        account_id = account.id
        start = date(2026, 1, 1)
        for index in range(105):
            trade_date = start + timedelta(days=index)
            snapshot = _seed_trading_snapshot(repo, account.id, trade_date)
            snapshot.event_at = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
        session.commit()
    finally:
        session.close()

    result = TradingSnapshotTimestampRepairService(factory).run(account_id, start, start + timedelta(days=104))

    assert result.matched_count == 105
    assert len(result.candidates) == MAX_REPAIR_CANDIDATES
    assert [candidate.trade_date for candidate in result.candidates] == [
        start + timedelta(days=index) for index in range(100)
    ]
    assert [candidate.snapshot_id for candidate in result.candidates] == sorted(
        candidate.snapshot_id for candidate in result.candidates
    )
