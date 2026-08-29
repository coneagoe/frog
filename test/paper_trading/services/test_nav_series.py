from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from paper_trading.domain.enums import NavBaselineEligibility, NavReplayEventType, SnapshotQualityStatus
from paper_trading.domain.nav_replay import ReplayEvent
from paper_trading.services.nav_series import NavSeriesBuilder


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
