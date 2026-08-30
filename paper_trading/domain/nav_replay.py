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
    valuation_quality: str | None = None
    valuation_details: tuple[Mapping[str, Any], ...] = ()
    cash: Decimal | None = None
    holdings: Mapping[str, Decimal] | None = None
    costs: Mapping[str, Decimal] | None = None


@dataclass(frozen=True)
class ReplayResult:
    points: tuple[NavPoint, ...]


class NavSeriesReplay:
    def replay(self, events: list[ReplayEvent], initial_state: Mapping[str, Any]) -> ReplayResult:
        state = dict(initial_state)
        state.setdefault("cash", self._decimal(state.get("total_assets")) or Decimal("0"))
        state.setdefault("holdings", {})
        state.setdefault("costs", {})
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
        total_assets = self._decimal(state.get("total_assets"))
        share_count = self._decimal(state.get("share_count"))
        nav = self._decimal(state.get("nav"))
        cash = self._decimal(state.get("cash"))
        holdings = dict(state.get("holdings", {}))
        costs = dict(state.get("costs", {}))
        valuation_quality = event.payload.get("valuation_quality")
        valuation_details = tuple(event.payload.get("valuation_details", ()))

        if event.event_type is NavReplayEventType.CASH_FLOW:
            if "total_assets" in event.payload or "post_total_assets" in event.payload:
                raise ValueError("cash-flow payload uses pre-event state and cannot contain post total_assets")
            if "nav" in event.payload:
                raise ValueError("cash-flow payload cannot contain state-bearing nav")
            if "share_count" in event.payload:
                raise ValueError("cash-flow payload cannot contain state-bearing share_count")
            if "pre_share_count" in event.payload:
                pre_share_count = self._decimal(event.payload["pre_share_count"])
                if state.get("share_count") is None or pre_share_count != self._decimal(state["share_count"]):
                    raise ValueError("cash-flow pre_share_count conflicts with replay state")
            pre_total_assets = self._decimal(event.payload.get("pre_total_assets", state.get("total_assets")))
            if state.get("total_assets") is not None and pre_total_assets != self._decimal(state["total_assets"]):
                raise ValueError("cash-flow pre_total_assets conflicts with replay state")
            amount = self._decimal(event.payload.get("amount"))
            pricing_nav = nav if self._valid_nav(nav) else Decimal("1")
            if pricing_nav is None:
                pricing_nav = Decimal("1")
            cash_amount = amount or Decimal("0")
            total_assets = (pre_total_assets or Decimal("0")) + cash_amount
            share_count = (share_count or Decimal("0")) + cash_amount / pricing_nav
            nav = pricing_nav
            cash = (cash or Decimal("0")) + cash_amount
        elif event.event_type is NavReplayEventType.MARKET_VALUATION:
            valuation_total = self._decimal(event.payload.get("total_assets"))
            if valuation_total is None:
                nav = None
            else:
                total_assets = valuation_total
            if valuation_total is not None and share_count:
                nav = valuation_total / share_count
        elif event.event_type is NavReplayEventType.INITIAL:
            total_assets = self._decimal(
                event.payload.get("opening_cash", event.payload.get("total_assets", total_assets))
            )
            share_count = self._decimal(
                event.payload.get("opening_shares", event.payload.get("share_count", share_count))
            )
            if nav is None and total_assets is not None and share_count:
                nav = total_assets / share_count
            cash = total_assets
        elif event.event_type is NavReplayEventType.TRADE_SETTLEMENT:
            amount = self._decimal(event.payload.get("amount")) or Decimal("0")
            fees = self._decimal(event.payload.get("fees")) or Decimal("0")
            quantity = self._decimal(event.payload.get("quantity")) or Decimal("0")
            price = self._decimal(event.payload.get("price")) or Decimal("0")
            symbol = str(event.payload.get("symbol", ""))
            side = str(event.payload.get("side", ""))
            sign = Decimal("1") if side == "sell" else Decimal("-1")
            cash = (cash or Decimal("0")) + sign * amount - fees
            holdings[symbol] = holdings.get(symbol, Decimal("0")) + sign * quantity
            costs[symbol] = costs.get(symbol, Decimal("0")) + sign * quantity * price
            total_assets = (total_assets or Decimal("0")) - fees
            if share_count:
                nav = total_assets / share_count
        elif event.event_type is NavReplayEventType.CORPORATE_ACTION:
            total_assets = (total_assets or Decimal("0")) + (
                self._decimal(event.payload.get("cash_delta")) or Decimal("0")
            )
            if share_count:
                nav = total_assets / share_count
            symbol = str(event.payload.get("symbol", ""))
            holdings[symbol] = holdings.get(symbol, Decimal("0")) + (
                self._decimal(event.payload.get("quantity_delta")) or Decimal("0")
            )
            if "after_cost_amount" in event.payload:
                costs[symbol] = self._decimal(event.payload.get("after_cost_amount")) or costs.get(symbol, Decimal("0"))
            cash = (cash or Decimal("0")) + (self._decimal(event.payload.get("cash_delta")) or Decimal("0"))
        elif total_assets is not None and share_count:
            nav = total_assets / share_count

        valid = event.quality_status is SnapshotQualityStatus.VALID and self._valid_nav(nav)
        point = NavPoint(
            event_at=event.event_at,
            trade_date=event.trade_date,
            source_id=event.source_id,
            event_type=event.event_type,
            total_assets=total_assets,
            share_count=share_count,
            nav=nav if valid else None,
            quality_status=SnapshotQualityStatus.VALID if valid else SnapshotQualityStatus.INVALID,
            valuation_quality=valuation_quality,
            valuation_details=valuation_details,
            cash=cash,
            holdings=dict(holdings),
            costs=dict(costs),
        )
        state["cash"] = cash
        state["holdings"] = holdings
        state["costs"] = costs
        state["total_assets"] = total_assets
        state["share_count"] = share_count
        if valid:
            state["nav"] = nav
        return point

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
