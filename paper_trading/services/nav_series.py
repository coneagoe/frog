from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from paper_trading.domain.enums import NavBaselineEligibility, NavReplayEventType, SnapshotQualityStatus
from paper_trading.domain.nav_replay import NavSeriesReplay, ReplayEvent, ReplayResult

_PROVABLE_BASELINE_SOURCES = frozenset({"creation", "ledger", "history"})


class NavSeriesBuilder:
    def __init__(self, event_loader: Callable[[int], list[ReplayEvent]] | None = None):
        self._event_loader = event_loader or (lambda account_id: [])
        self._replay = NavSeriesReplay()

    def build(
        self,
        account_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> ReplayResult:
        events = self._event_loader(account_id)
        baseline = self._baseline_from_events(events)
        if baseline is None:
            raise ValueError("baseline is not provably reconstructible")
        replayed = self._replay.replay(events, baseline)
        points = [
            point
            for point in replayed.points
            if (start_date is None or point.trade_date >= start_date) and (end_date is None or point.trade_date <= end_date)
        ]
        return ReplayResult(points=tuple(points))

    @staticmethod
    def baseline_eligibility(initial_state: Mapping[str, Any]) -> NavBaselineEligibility:
        for source in _PROVABLE_BASELINE_SOURCES:
            value = initial_state.get(source)
            if isinstance(value, Mapping) and NavSeriesBuilder._valid_baseline_source(value):
                return NavBaselineEligibility.ELIGIBLE
        return NavBaselineEligibility.INELIGIBLE

    @staticmethod
    def _valid_baseline_source(source: Mapping[str, Any]) -> bool:
        cash = source.get("opening_cash")
        shares = source.get("opening_shares")
        if cash is None or shares is None:
            return False
        try:
            cash_value = Decimal(cash)
            shares_value = Decimal(shares)
        except (InvalidOperation, TypeError, ValueError):
            return False
        return cash_value.is_finite() and shares_value.is_finite() and cash_value >= 0 and shares_value > 0

    def _baseline_from_events(self, events: list[ReplayEvent]) -> dict[str, Any] | None:
        candidates = [
            event
            for event in events
            if event.event_type is NavReplayEventType.INITIAL
            and event.source_kind in _PROVABLE_BASELINE_SOURCES
            and event.quality_status is SnapshotQualityStatus.VALID
            and self._valid_baseline_source(event.payload)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda event: (event.event_at, event.source_id))
        return {
            "total_assets": candidates[0].payload["opening_cash"],
            "share_count": candidates[0].payload["opening_shares"],
        }
