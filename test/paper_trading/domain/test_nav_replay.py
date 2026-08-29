from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from paper_trading.domain.enums import NavReplayEventType, SnapshotQualityStatus
from paper_trading.domain.nav_replay import NavSeriesReplay, ReplayEvent


def _event(event_type, source_id, payload, *, event_at=datetime(2026, 8, 25, tzinfo=timezone.utc)):
    return ReplayEvent(
        event_at=event_at,
        trade_date=date(2026, 8, 25),
        event_type=event_type,
        source_id=source_id,
        source_kind="test",
        payload=payload,
        quality_status=SnapshotQualityStatus.VALID,
    )


def test_replay_orders_same_timestamp_by_fixed_precedence_then_source_id():
    events = [
        _event(NavReplayEventType.MARKET_VALUATION, "valuation", {"total_assets": Decimal("220")}),
        _event(NavReplayEventType.CASH_FLOW, "deposit", {"amount": Decimal("100")}),
        _event(NavReplayEventType.INITIAL, "initial", {"total_assets": Decimal("100"), "share_count": Decimal("100")}),
    ]

    result = NavSeriesReplay().replay(events, initial_state={})

    assert [point.source_id for point in result.points] == ["initial", "deposit", "valuation"]
    assert result.points[1].nav == Decimal("1")
    assert result.points[-1].nav == Decimal("1.1")


def test_replay_rejects_events_with_identical_complete_ordering_key():
    events = [
        _event(NavReplayEventType.CASH_FLOW, "same", {"amount": Decimal("100")}),
        _event(NavReplayEventType.CASH_FLOW, "same", {"amount": Decimal("50")}),
    ]

    with pytest.raises(ValueError, match="ambiguous"):
        NavSeriesReplay().replay(events, initial_state={})


def test_replay_normalizes_non_utc_event_timestamp_before_sorting():
    event = _event(
        NavReplayEventType.INITIAL,
        "initial",
        {"total_assets": Decimal("100"), "share_count": Decimal("100")},
        event_at=datetime(2026, 8, 26, 8, tzinfo=timezone(timedelta(hours=8))),
    )

    result = NavSeriesReplay().replay([event], initial_state={})

    assert result.points[0].event_at == datetime(2026, 8, 26, tzinfo=timezone.utc)


def test_cash_flow_uses_previous_valid_nav_or_one_and_does_not_create_return():
    events = [
        _event(NavReplayEventType.CASH_FLOW, "first", {"amount": Decimal("100")}),
        _event(
            NavReplayEventType.MARKET_VALUATION,
            "value",
            {"total_assets": Decimal("150")},
            event_at=datetime(2026, 8, 25, 0, 1, tzinfo=timezone.utc),
        ),
        _event(
            NavReplayEventType.CASH_FLOW,
            "second",
            {"amount": Decimal("30")},
            event_at=datetime(2026, 8, 25, 0, 2, tzinfo=timezone.utc),
        ),
    ]

    result = NavSeriesReplay().replay(events, initial_state={})

    assert [point.nav for point in result.points] == [Decimal("1"), Decimal("1.5"), Decimal("1.5")]
    assert result.points[0].share_count == Decimal("100")
    assert result.points[-1].share_count == Decimal("120")


def test_cash_flow_rejects_conflicting_pre_and_post_asset_payload():
    event = _event(
        NavReplayEventType.CASH_FLOW,
        "deposit",
        {
            "amount": Decimal("100"),
            "pre_total_assets": Decimal("100"),
            "post_total_assets": Decimal("200"),
        },
    )

    with pytest.raises(ValueError, match="post total_assets"):
        NavSeriesReplay().replay([event], initial_state={})


def test_cash_flow_rejects_total_assets_that_could_be_double_counted():
    event = _event(
        NavReplayEventType.CASH_FLOW,
        "deposit",
        {"amount": Decimal("100"), "total_assets": Decimal("200")},
    )

    with pytest.raises(ValueError, match="post total_assets"):
        NavSeriesReplay().replay([event], initial_state={})


@pytest.mark.parametrize("value", [None, Decimal("NaN"), Decimal("Infinity"), Decimal("0"), Decimal("-1")])
def test_invalid_nav_values_produce_invalid_points(value):
    result = NavSeriesReplay().replay(
        [_event(NavReplayEventType.MARKET_VALUATION, "valuation", {"nav": value})],
        initial_state={"share_count": Decimal("100")},
    )

    point = result.points[0]
    assert point.nav is None
    assert point.quality_status is SnapshotQualityStatus.INVALID
