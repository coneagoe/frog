import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from paper_trading.domain.enums import NavBaselineEligibility, NavReplayEventType, OrderSide, SnapshotQualityStatus
from paper_trading.domain.nav_replay import ReplayEvent
from paper_trading.services.nav_series import NavSeriesBuilder
from paper_trading.storage.enum_migration import migrate_paper_trading_enums
from paper_trading.storage.models import PaperAccount, PaperAccountSnapshot, PaperCashLedger
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base


def test_baseline_requires_provable_creation_ledger_or_history_source():
    builder = NavSeriesBuilder()

    source = {"opening_cash": Decimal("100"), "opening_shares": Decimal("100")}
    assert builder.baseline_eligibility({"creation": source}) is NavBaselineEligibility.ELIGIBLE
    assert builder.baseline_eligibility({"ledger": source}) is NavBaselineEligibility.ELIGIBLE
    assert builder.baseline_eligibility({"history": source}) is NavBaselineEligibility.ELIGIBLE
    assert builder.baseline_eligibility({"creation": {}}) is NavBaselineEligibility.INELIGIBLE
    assert builder.baseline_eligibility({"ledger": []}) is NavBaselineEligibility.INELIGIBLE
    assert builder.baseline_eligibility({"share_count": Decimal("999")}) is NavBaselineEligibility.INELIGIBLE


def test_builder_filters_events_by_requested_date_without_using_account_share_count():
    events = [
        ReplayEvent(
            event_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
            trade_date=date(2026, 8, 24),
            event_type=NavReplayEventType.INITIAL,
            source_id="initial",
            source_kind="creation",
            payload={"opening_cash": Decimal("100"), "opening_shares": Decimal("100")},
            quality_status=SnapshotQualityStatus.VALID,
        ),
        ReplayEvent(
            event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            trade_date=date(2026, 8, 25),
            event_type=NavReplayEventType.MARKET_VALUATION,
            source_id="valuation",
            source_kind="history",
            payload={"total_assets": Decimal("120")},
            quality_status=SnapshotQualityStatus.VALID,
        ),
    ]
    builder = NavSeriesBuilder(event_loader=lambda account_id: events)

    result = builder.build(1, start_date=date(2026, 8, 25), end_date=date(2026, 8, 25))

    assert [point.trade_date for point in result.points] == [date(2026, 8, 25)]
    assert result.points[0].nav == Decimal("1.2")


def test_builder_rejects_legacy_baseline_from_current_account_share_count():
    builder = NavSeriesBuilder(event_loader=lambda account_id: [])

    with pytest.raises(ValueError, match="baseline"):
        builder.build(1)


def test_builder_constructs_baseline_state_from_provable_source():
    events = [
        ReplayEvent(
            event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            trade_date=date(2026, 8, 25),
            event_type=NavReplayEventType.INITIAL,
            source_id="creation-1",
            source_kind="creation",
            payload={"opening_cash": Decimal("250"), "opening_shares": Decimal("100")},
            quality_status=SnapshotQualityStatus.VALID,
        )
    ]

    result = NavSeriesBuilder(event_loader=lambda account_id: events).build(1)

    assert result.points[0].total_assets == Decimal("250")
    assert result.points[0].share_count == Decimal("100")
    assert result.points[0].nav == Decimal("2.5")


def test_builder_rejects_invalid_quality_initial_as_baseline():
    events = [
        ReplayEvent(
            event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            trade_date=date(2026, 8, 25),
            event_type=NavReplayEventType.INITIAL,
            source_id="creation-invalid",
            source_kind="creation",
            payload={"opening_cash": Decimal("250"), "opening_shares": Decimal("100")},
            quality_status=SnapshotQualityStatus.INVALID,
        )
    ]

    with pytest.raises(ValueError, match="baseline"):
        NavSeriesBuilder(event_loader=lambda account_id: events).build(1)


def test_builder_default_repository_loader_replays_persisted_events(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'builder.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repository-builder", Decimal("100"))
        occurred_at = datetime.now(timezone.utc) + timedelta(days=1)
        repo.add_cash_event(
            account.id,
            "deposit",
            Decimal("50"),
            trade_date=occurred_at.date(),
            occurred_at=occurred_at,
        )

        result = NavSeriesBuilder(repo=repo).build(account.id)

        assert result.points[-1].share_count == Decimal("150")
        assert result.points[-1].nav == Decimal("1")
    finally:
        session.close()
        engine.dispose()


def test_builder_keeps_positional_event_loader_compatibility():
    events = [
        ReplayEvent(
            event_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            trade_date=date(2026, 8, 25),
            event_type=NavReplayEventType.INITIAL,
            source_id="initial",
            source_kind="creation",
            payload={"opening_cash": Decimal("10"), "opening_shares": Decimal("10")},
            quality_status=SnapshotQualityStatus.VALID,
        )
    ]

    assert NavSeriesBuilder(lambda _account_id: events).build(1).points[0].nav == Decimal("1")


def test_repository_builder_preserves_initial_cumulative_cash_flow_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'builder_cumulative.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repository-builder-cumulative", Decimal("100"))
        initial = next(row for row in repo.list_snapshots(account.id) if row.point_type == "initial")
        initial.cumulative_deposit = Decimal("125")
        initial.cumulative_withdrawal = Decimal("25")
        result = NavSeriesBuilder(repo=repo).build(account.id)

        assert result.points[0].cumulative_deposit == Decimal("125")
        assert result.points[0].cumulative_withdrawal == Decimal("25")
        assert result.points[0].net_cash_flow == Decimal("100")
    finally:
        session.close()
        engine.dispose()


def test_repository_replay_does_not_double_debit_freeze_trade_release(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'builder_freeze.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repository-builder-freeze", Decimal("100"))
        occurred_at = datetime.now(timezone.utc) + timedelta(days=1)
        trade = repo.create_trade(
            1,
            account.id,
            "000001",
            OrderSide.BUY,
            10,
            Decimal("8"),
            Decimal("80"),
            Decimal("0"),
            occurred_at.date(),
            trade_time=occurred_at,
        )
        repo.add_cash_event(
            account.id,
            "freeze",
            Decimal("-100"),
            trade_id=trade.id,
            trade_date=occurred_at.date(),
            occurred_at=occurred_at - timedelta(minutes=2),
        )
        repo.add_cash_event(
            account.id,
            "release",
            Decimal("20"),
            trade_id=trade.id,
            trade_date=occurred_at.date(),
            occurred_at=occurred_at + timedelta(minutes=2),
        )

        point = NavSeriesBuilder(repo=repo).build(account.id).points[-1]

        assert point.cash == Decimal("20")
        assert point.cash_frozen == Decimal("0")
        assert point.total_assets == Decimal("100")
    finally:
        session.close()
        engine.dispose()


def test_repository_builder_preserves_explicit_zero_initial_cash_flow_fields(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'builder_zero.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repository-builder-zero", Decimal("100"))
        initial = next(row for row in repo.list_snapshots(account.id) if row.point_type == "initial")
        initial.cumulative_deposit = Decimal("0")
        initial.cumulative_withdrawal = Decimal("0")
        initial.pending_settlement = Decimal("0")

        events, baseline = NavSeriesBuilder(repo=repo).prepare(account.id)

        assert baseline["cumulative_deposit"] == Decimal("0")
        assert baseline["cumulative_withdrawal"] == Decimal("0")
        assert baseline["pending_settlement"] == Decimal("0")
        assert NavSeriesBuilder(repo=repo).build(account.id).points[0].net_cash_flow == Decimal("0")
        assert events[0].payload["cumulative_deposit"] == Decimal("0")
    finally:
        session.close()
        engine.dispose()


def test_repository_builder_does_not_replay_creation_cash_again_after_initial_snapshot_edit(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'builder_edited_initial.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("repository-builder-edited-initial", Decimal("100"))
        initial = next(row for row in repo.list_snapshots(account.id) if row.point_type == "initial")
        initial.cash_available = Decimal("70")
        initial.cash_frozen = Decimal("10")
        initial.pending_settlement = Decimal("20")
        initial.total_assets = Decimal("100")

        point = NavSeriesBuilder(repo=repo).build(account.id).points[0]

        assert point.cash == Decimal("70")
        assert point.cash_frozen == Decimal("10")
        assert point.pending_settlement == Decimal("20")
        assert point.total_assets == Decimal("100")
    finally:
        session.close()
        engine.dispose()


def test_postgresql_repository_builder_replays_persisted_cash_flow():
    url = cast(str, os.getenv("TEST_POSTGRESQL_URL"))
    if not url:
        pytest.skip("TEST_POSTGRESQL_URL is unavailable")
    schema_name = f"task3_nav_{uuid.uuid4().hex}"
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema_name}"})
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    with engine.begin() as connection:
        migrate_paper_trading_enums(connection)
    Base.metadata.create_all(
        engine, tables=[PaperAccount.__table__, PaperCashLedger.__table__, PaperAccountSnapshot.__table__]
    )
    session = sessionmaker(bind=engine)()
    try:
        repo = PaperTradingRepository(session)
        account = repo.create_account("postgres-builder", Decimal("100"))
        occurred_at = datetime.now(timezone.utc) + timedelta(days=1)
        repo.add_cash_event(
            account.id, "deposit", Decimal("25"), trade_date=occurred_at.date(), occurred_at=occurred_at
        )
        session.commit()

        point = NavSeriesBuilder(repo=repo).build(account.id).points[-1]

        assert point.share_count == Decimal("125")
        assert point.net_cash_flow == Decimal("125")
    finally:
        session.close()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        engine.dispose()
