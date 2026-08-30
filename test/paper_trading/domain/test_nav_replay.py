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


def test_backdated_cash_flow_reprices_later_valuation_without_using_stale_snapshot_nav():
    events = [
        _event(
            NavReplayEventType.INITIAL,
            "initial",
            {"opening_cash": Decimal("100"), "opening_shares": Decimal("100")},
        ),
        _event(
            NavReplayEventType.CASH_FLOW,
            "backdated-deposit",
            {"amount": Decimal("100")},
            event_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        ),
        _event(
            NavReplayEventType.MARKET_VALUATION,
            "close",
            {"total_assets": Decimal("240")},
            event_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        ),
    ]

    result = NavSeriesReplay().replay(events, initial_state={})

    assert result.points[-1].share_count == Decimal("200")
    assert result.points[-1].nav == Decimal("1.2")


def test_missing_market_valuation_is_a_gap_not_a_carried_forward_nav():
    events = [
        _event(
            NavReplayEventType.INITIAL,
            "initial",
            {"opening_cash": Decimal("100"), "opening_shares": Decimal("100")},
        ),
        _event(
            NavReplayEventType.MARKET_VALUATION,
            "missing-close",
            {},
            event_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        ),
    ]

    result = NavSeriesReplay().replay(events, initial_state={})

    assert result.points[-1].nav is None
    assert result.points[-1].quality_status is SnapshotQualityStatus.INVALID


def test_gap_preserves_state_for_later_cash_flow_and_cumulative_cash_flow():
    events = [
        _event(
            NavReplayEventType.INITIAL, "initial", {"opening_cash": Decimal("100"), "opening_shares": Decimal("100")}
        ),
        _event(NavReplayEventType.MARKET_VALUATION, "gap", {}, event_at=datetime(2026, 8, 26, tzinfo=timezone.utc)),
        _event(
            NavReplayEventType.CASH_FLOW,
            "withdraw",
            {"amount": Decimal("-20")},
            event_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        ),
    ]

    result = NavSeriesReplay().replay(events, initial_state={})

    assert result.points[-1].cash == Decimal("80")
    assert result.points[-1].share_count == Decimal("80")
    assert result.points[-1].cumulative_deposit == Decimal("100")
    assert result.points[-1].cumulative_withdrawal == Decimal("20")
    assert result.points[-1].net_cash_flow == Decimal("80")


def test_trade_replay_uses_average_cost_with_fees_and_market_symbol_key():
    events = [
        _event(
            NavReplayEventType.INITIAL, "initial", {"opening_cash": Decimal("1000"), "opening_shares": Decimal("1000")}
        ),
        _event(
            NavReplayEventType.TRADE_SETTLEMENT,
            "buy-a",
            {
                "side": "buy",
                "market": "a_share",
                "symbol": "000001",
                "quantity": 10,
                "price": Decimal("10"),
                "amount": Decimal("100"),
                "fees": Decimal("5"),
            },
        ),
        _event(
            NavReplayEventType.TRADE_SETTLEMENT,
            "buy-hk",
            {
                "side": "buy",
                "market": "hk_connect",
                "symbol": "000001",
                "quantity": 10,
                "price": Decimal("20"),
                "amount": Decimal("200"),
                "fees": Decimal("2"),
            },
            event_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        ),
        _event(
            NavReplayEventType.TRADE_SETTLEMENT,
            "sell-a",
            {
                "side": "sell",
                "market": "a_share",
                "symbol": "000001",
                "quantity": 4,
                "price": Decimal("30"),
                "amount": Decimal("120"),
                "fees": Decimal("1"),
            },
            event_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        ),
    ]

    point = NavSeriesReplay().replay(events, initial_state={}).points[-1]

    assert point.holdings == {"a_share:000001": Decimal("6"), "hk_connect:000001": Decimal("10")}
    assert point.costs == {"a_share:000001": Decimal("63"), "hk_connect:000001": Decimal("202")}


def test_corporate_action_updates_market_symbol_quantity_cost_and_cash():
    events = [
        _event(
            NavReplayEventType.INITIAL, "initial", {"opening_cash": Decimal("100"), "opening_shares": Decimal("100")}
        ),
        _event(
            NavReplayEventType.CORPORATE_ACTION,
            "split",
            {
                "market": "a_share",
                "symbol": "000001",
                "quantity_delta": Decimal("20"),
                "cash_delta": Decimal("5"),
                "after_cost_amount": Decimal("80"),
            },
        ),
    ]

    point = (
        NavSeriesReplay()
        .replay(events, {"holdings": {"a_share:000001": Decimal("10")}, "costs": {"a_share:000001": Decimal("100")}})
        .points[-1]
    )

    assert point.holdings == {"a_share:000001": Decimal("30")}
    assert point.costs == {"a_share:000001": Decimal("80")}
    assert point.cash == Decimal("105")


def test_trade_replay_rejects_unknown_side():
    with pytest.raises(ValueError, match="unsupported trade side"):
        NavSeriesReplay().replay(
            [_event(NavReplayEventType.TRADE_SETTLEMENT, "bad", {"side": "hold", "quantity": 1, "price": 1})],
            initial_state={"total_assets": Decimal("100"), "share_count": Decimal("100")},
        )


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


def test_cash_flow_rejects_conflicting_share_count_payload():
    event = _event(
        NavReplayEventType.CASH_FLOW,
        "deposit",
        {"amount": Decimal("100"), "share_count": Decimal("999")},
    )

    with pytest.raises(ValueError, match="share_count"):
        NavSeriesReplay().replay([event], initial_state={"share_count": Decimal("100")})


def test_cash_flow_rejects_pre_share_count_without_replay_share_state():
    event = _event(
        NavReplayEventType.CASH_FLOW,
        "deposit",
        {"amount": Decimal("100"), "pre_share_count": Decimal("100")},
    )

    with pytest.raises(ValueError, match="pre_share_count"):
        NavSeriesReplay().replay([event], initial_state={})


def test_cash_flow_rejects_payload_nav_instead_of_overriding_replay_nav():
    event = _event(
        NavReplayEventType.CASH_FLOW,
        "deposit",
        {"amount": Decimal("100"), "nav": Decimal("99")},
    )

    with pytest.raises(ValueError, match="nav"):
        NavSeriesReplay().replay([event], initial_state={"nav": Decimal("1")})


@pytest.mark.parametrize("value", [None, Decimal("NaN"), Decimal("Infinity"), Decimal("0"), Decimal("-1")])
def test_invalid_nav_values_produce_invalid_points(value):
    result = NavSeriesReplay().replay(
        [_event(NavReplayEventType.MARKET_VALUATION, "valuation", {"nav": value})],
        initial_state={"share_count": Decimal("100")},
    )

    point = result.points[0]
    assert point.nav is None
    assert point.quality_status is SnapshotQualityStatus.INVALID
