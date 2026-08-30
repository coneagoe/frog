from collections.abc import Callable, Mapping
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from paper_trading.domain.enums import NavBaselineEligibility, NavReplayEventType, SnapshotQualityStatus
from paper_trading.domain.nav_replay import NavSeriesReplay, ReplayEvent, ReplayResult
from paper_trading.storage.models import PaperPendingSettlement

_PROVABLE_BASELINE_SOURCES = frozenset({"creation", "ledger", "history"})


class NavSeriesBuilder:
    def __init__(
        self,
        repo: Any | None = None,
        event_loader: Callable[[int], list[ReplayEvent]] | None = None,
    ):
        self._repo = None if callable(repo) else repo
        if callable(repo) and event_loader is None:
            event_loader = cast(Callable[[int], list[ReplayEvent]], repo)
            repo = None
        if event_loader is not None:
            self._event_loader = event_loader
        elif repo is not None:
            self._event_loader = cast(Callable[[int], list[ReplayEvent]], getattr(repo, "list_replay_events"))
        else:
            self._event_loader = lambda _account_id: (_ for _ in ()).throw(
                ValueError("NavSeriesBuilder requires a repository or event_loader")
            )
        self._replay = NavSeriesReplay()

    def build(
        self,
        account_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> ReplayResult:
        events, baseline = self.prepare(account_id)
        replayed = self._replay.replay(events, baseline)
        points = [
            point
            for point in replayed.points
            if (start_date is None or point.trade_date >= start_date)
            and (end_date is None or point.trade_date <= end_date)
        ]
        return ReplayResult(points=tuple(points))

    def prepare(self, account_id: int) -> tuple[list[ReplayEvent], dict[str, Any]]:
        """Return normalized, deduplicated replay facts and their proven baseline."""
        events = self._event_loader(account_id)
        if self._repo is not None:
            events = self._enrich_initial_events(account_id, events)
            events = self._normalize_hk_settlement_dates(account_id, events)
        events = self._deduplicate_trade_settlements(events)
        baseline = self._baseline_from_events(events)
        if baseline is None:
            raise ValueError("baseline is not provably reconstructible")
        return events, baseline

    def _enrich_initial_events(self, account_id: int, events: list[ReplayEvent]) -> list[ReplayEvent]:
        if self._repo is None:
            return events
        snapshots = {
            f"paper_account_snapshots:{snapshot.id}": snapshot
            for snapshot in self._repo.list_snapshots(account_id)
            if snapshot.point_type == "initial"
        }
        enriched: list[ReplayEvent] = []
        for event in events:
            snapshot = snapshots.get(event.source_id)
            if snapshot is None:
                enriched.append(event)
                continue
            payload = dict(event.payload)
            payload.update(
                cumulative_deposit=snapshot.cumulative_deposit,
                cumulative_withdrawal=snapshot.cumulative_withdrawal,
                pending_settlement=snapshot.pending_settlement,
                cash_available=snapshot.cash_available,
                cash_frozen=snapshot.cash_frozen,
                total_assets=snapshot.total_assets,
            )
            enriched.append(
                ReplayEvent(
                    event_at=event.event_at,
                    trade_date=event.trade_date,
                    event_type=event.event_type,
                    source_id=event.source_id,
                    source_kind=event.source_kind,
                    payload=payload,
                    quality_status=event.quality_status,
                )
            )
        return enriched

    def _normalize_hk_settlement_dates(self, account_id: int, events: list[ReplayEvent]) -> list[ReplayEvent]:
        if self._repo is None:
            return events
        hk_trade_ids = {
            trade.id
            for trade in self._repo.list_trades(account_id)
            if trade.market == "hk_connect" and trade.side == "sell"
        }
        settlement_dates = {
            row.trade_id: row.expected_settle_date
            for row in self._repo.session.query(PaperPendingSettlement)
            .filter(PaperPendingSettlement.account_id == account_id)
            .all()
            if row.trade_id in hk_trade_ids
        }
        normalized: list[ReplayEvent] = []
        for event in events:
            settle_date = settlement_dates.get(event.payload.get("trade_id"))
            if (
                event.source_kind != "paper_cash_ledger"
                or event.payload.get("ledger_event_type") != "trade"
                or settle_date is None
            ):
                normalized.append(event)
                continue
            normalized.append(
                ReplayEvent(
                    event_at=datetime.combine(settle_date, time.max, tzinfo=timezone.utc),
                    trade_date=settle_date,
                    event_type=event.event_type,
                    source_id=event.source_id,
                    source_kind=event.source_kind,
                    payload=event.payload,
                    quality_status=event.quality_status,
                )
            )
        return normalized

    @staticmethod
    def _deduplicate_trade_settlements(events: list[ReplayEvent]) -> list[ReplayEvent]:
        trade_ids = {
            event.payload.get("trade_id")
            for event in events
            if event.source_kind == "paper_trades" and event.payload.get("trade_id") is not None
        }
        hk_trade_ids = {
            event.payload.get("trade_id")
            for event in events
            if event.source_kind == "paper_trades"
            and event.payload.get("market") == "hk_connect"
            and event.payload.get("side") == "sell"
        }
        return [
            event
            for event in events
            if not (
                event.source_kind == "paper_cash_ledger"
                and event.event_type is NavReplayEventType.TRADE_SETTLEMENT
                and (
                    (
                        event.payload.get("trade_id") in trade_ids
                        and event.payload.get("trade_id") not in hk_trade_ids
                        and event.payload.get("ledger_event_type") == "trade"
                    )
                    or event.payload.get("ledger_event_type") == "corporate_action"
                )
            )
        ]

    @staticmethod
    def baseline_eligibility(initial_state: Mapping[str, Any]) -> NavBaselineEligibility:
        for source in _PROVABLE_BASELINE_SOURCES:
            value = initial_state.get(source)
            if isinstance(value, Mapping) and NavSeriesBuilder._valid_baseline_source(value):
                return NavBaselineEligibility.ELIGIBLE
        return NavBaselineEligibility.INELIGIBLE

    @staticmethod
    def _valid_baseline_source(source: Mapping[str, Any]) -> bool:
        cash = source.get("opening_cash", source.get("total_assets"))
        shares = source.get("opening_shares", source.get("share_count"))
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
        opening_cash = candidates[0].payload.get("opening_cash", candidates[0].payload.get("total_assets"))
        opening_shares = candidates[0].payload.get("opening_shares", candidates[0].payload.get("share_count"))
        return {
            "total_assets": opening_cash,
            "share_count": opening_shares,
            "cash": opening_cash,
            "holdings": {},
            "costs": {},
            "cumulative_deposit": candidates[0].payload.get("cumulative_deposit", opening_cash),
            "cumulative_withdrawal": candidates[0].payload.get("cumulative_withdrawal", Decimal("0")),
            "pending_settlement": candidates[0].payload.get("pending_settlement", Decimal("0")),
        }
