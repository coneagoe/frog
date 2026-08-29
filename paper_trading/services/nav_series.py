from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from paper_trading.domain.enums import NavBaselineEligibility, NavReplayEventType
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
        initial_state: Mapping[str, Any] | None = None,
    ) -> ReplayResult:
        events = self._event_loader(account_id)
        state = initial_state or {}
        if not self._has_eligible_baseline(events, state):
            raise ValueError("baseline is not provably reconstructible")
        replayed = self._replay.replay(events, state)
        points = [
            point
            for point in replayed.points
            if (start_date is None or point.trade_date >= start_date) and (end_date is None or point.trade_date <= end_date)
        ]
        return ReplayResult(points=points)

    @staticmethod
    def baseline_eligibility(initial_state: Mapping[str, Any]) -> NavBaselineEligibility:
        return (
            NavBaselineEligibility.ELIGIBLE
            if any(source in initial_state for source in _PROVABLE_BASELINE_SOURCES)
            else NavBaselineEligibility.INELIGIBLE
        )

    def _has_eligible_baseline(self, events: list[ReplayEvent], initial_state: Mapping[str, Any]) -> bool:
        if self.baseline_eligibility(initial_state) is NavBaselineEligibility.ELIGIBLE:
            return True
        return any(
            event.event_type is NavReplayEventType.INITIAL and event.source_kind in _PROVABLE_BASELINE_SOURCES
            for event in events
        )
