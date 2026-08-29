from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from paper_trading.domain.enums import NavReplayEventType, SnapshotQualityStatus

_EVENT_PRECEDENCE = {
    NavReplayEventType.INITIAL: 0,
    NavReplayEventType.CASH_FLOW: 1,
    NavReplayEventType.TRADE_SETTLEMENT: 2,
    NavReplayEventType.CORPORATE_ACTION: 3,
    NavReplayEventType.MARKET_VALUATION: 4,
}


@dataclass(frozen=True)
class ReplayEvent:
    event_at: datetime
    trade_date: date
    event_type: NavReplayEventType
    source_id: str
    source_kind: str
    payload: Mapping[str, Any]
    quality_status: SnapshotQualityStatus

    def __post_init__(self) -> None:
        if self.event_at.tzinfo is None or self.event_at.utcoffset() is None:
            raise ValueError("event_at must include a timezone offset")
        object.__setattr__(self, "event_at", self.event_at.astimezone(timezone.utc))


@dataclass(frozen=True)
class NavPoint:
    event_at: datetime
    trade_date: date
    source_id: str
    event_type: NavReplayEventType
    total_assets: Decimal | None
    share_count: Decimal | None
    nav: Decimal | None
    quality_status: SnapshotQualityStatus


@dataclass(frozen=True)
class ReplayResult:
    points: tuple[NavPoint, ...]


class NavSeriesReplay:
    def replay(self, events: list[ReplayEvent], initial_state: Mapping[str, Any]) -> ReplayResult:
        state = dict(initial_state)
        points: list[NavPoint] = []
        ordered_events = sorted(events, key=self._sort_key)
        for previous, event in zip(ordered_events, ordered_events[1:]):
            if self._sort_key(previous) == self._sort_key(event):
                raise ValueError("ambiguous replay events have identical ordering keys")
        for event in ordered_events:
            point = self._apply_event(event, state)
            points.append(point)
            if point.quality_status is SnapshotQualityStatus.VALID:
                state["total_assets"] = point.total_assets
                state["share_count"] = point.share_count
                state["nav"] = point.nav
        return ReplayResult(points=tuple(points))

    @staticmethod
    def _sort_key(event: ReplayEvent) -> tuple[datetime, int, str]:
        return event.event_at, _EVENT_PRECEDENCE[event.event_type], event.source_id

    def _apply_event(self, event: ReplayEvent, state: dict[str, Any]) -> NavPoint:
        total_assets = self._decimal(event.payload.get("total_assets", state.get("total_assets")))
        share_count = self._decimal(event.payload.get("share_count", state.get("share_count")))
        nav = self._decimal(event.payload.get("nav", state.get("nav")))

        if event.event_type is NavReplayEventType.CASH_FLOW:
            if "total_assets" in event.payload or "post_total_assets" in event.payload:
                raise ValueError("cash-flow payload uses pre-event state and cannot contain post total_assets")
            if "share_count" in event.payload:
                raise ValueError("cash-flow payload cannot contain state-bearing share_count")
            if "pre_share_count" in event.payload:
                pre_share_count = self._decimal(event.payload["pre_share_count"])
                if state.get("share_count") is not None and pre_share_count != self._decimal(state["share_count"]):
                    raise ValueError("cash-flow pre_share_count conflicts with replay state")
            pre_total_assets = self._decimal(event.payload.get("pre_total_assets", state.get("total_assets")))
            if state.get("total_assets") is not None and pre_total_assets != self._decimal(state["total_assets"]):
                raise ValueError("cash-flow pre_total_assets conflicts with replay state")
            amount = self._decimal(event.payload.get("amount"))
            pricing_nav = nav if nav is not None and self._valid_nav(nav) else Decimal("1")
            cash_amount = amount or Decimal("0")
            total_assets = (pre_total_assets or Decimal("0")) + cash_amount
            share_count = (share_count or Decimal("0")) + cash_amount / pricing_nav
            nav = pricing_nav
        elif event.event_type is NavReplayEventType.MARKET_VALUATION and total_assets is not None and share_count:
            nav = total_assets / share_count
        elif event.event_type is NavReplayEventType.INITIAL:
            total_assets = self._decimal(event.payload.get("opening_cash", total_assets))
            share_count = self._decimal(event.payload.get("opening_shares", share_count))
            if nav is None and total_assets is not None and share_count:
                nav = total_assets / share_count
        elif total_assets is not None and share_count:
            nav = total_assets / share_count

        valid = event.quality_status is SnapshotQualityStatus.VALID and self._valid_nav(nav)
        return NavPoint(
            event_at=event.event_at,
            trade_date=event.trade_date,
            source_id=event.source_id,
            event_type=event.event_type,
            total_assets=total_assets,
            share_count=share_count,
            nav=nav if valid else None,
            quality_status=SnapshotQualityStatus.VALID if valid else SnapshotQualityStatus.INVALID,
        )

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _valid_nav(value: Decimal | None) -> bool:
        return value is not None and value.is_finite() and value > 0
