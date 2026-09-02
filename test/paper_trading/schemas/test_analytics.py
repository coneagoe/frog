from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paper_trading.schemas.analytics import SnapshotAnalyticsEvent


def _snapshot_event(**overrides: object) -> dict[str, object]:
    return {
        "id": 1,
        "event_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
        "trade_date": date(2026, 8, 25),
        "point_type": "initial",
        "quality": "valid",
        "timezone": "UTC",
        "quality_status": "valid",
        "shares": Decimal("100.000000"),
        "share": Decimal("100.000000"),
        **overrides,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"shares": None, "share": Decimal("100.000000")},
        {"shares": Decimal("100.000000"), "share": None},
        {"shares": Decimal("100.000000"), "share": Decimal("99.000000")},
    ],
)
def test_snapshot_analytics_event_rejects_mismatched_share_aliases(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="shares and share must both be null or equal"):
        SnapshotAnalyticsEvent(**_snapshot_event(**overrides))


def test_snapshot_analytics_event_accepts_matching_share_aliases() -> None:
    event = SnapshotAnalyticsEvent(**_snapshot_event(shares=None, share=None))

    assert event.shares is None
    assert event.share is None


def test_snapshot_analytics_event_requires_trade_date() -> None:
    event = _snapshot_event()
    del event["trade_date"]

    with pytest.raises(ValidationError, match="trade_date"):
        SnapshotAnalyticsEvent(**event)
