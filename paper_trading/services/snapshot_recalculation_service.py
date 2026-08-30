from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from paper_trading.domain.enums import NavReplayEventType, SnapshotPointType, SnapshotQualityStatus
from paper_trading.domain.nav_replay import NavSeriesReplay, ReplayEvent
from paper_trading.services.nav_series import NavSeriesBuilder
from paper_trading.services.snapshot_service import PositionValuation, SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperAccountSnapshot, PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository


@dataclass(frozen=True)
class SnapshotRecalculationResult:
    account_id: int
    updated_dates: list[date]
    unavailable_dates: list[date]
    failed_dates: list[date]
    errors: list[str]


class SnapshotRecalculationService:
    def __init__(self, session_factory: Callable[[], Session], market_data: MarketDataProvider):
        self.session_factory = session_factory
        self.market_data = market_data

    def recalculate(
        self, account_id: int, start_date: date, end_date: date, session: Session | None = None
    ) -> SnapshotRecalculationResult:
        if start_date > end_date:
            raise ValueError("start_date must be on or before end_date")

        owns_session = session is None
        current_session = session or self.session_factory()
        try:
            repo = PaperTradingRepository(current_session)
            if repo.get_account(account_id) is None:
                raise KeyError(f"paper account not found: {account_id}")

            dates = self._dates_with_valuation_state(repo, account_id, start_date, end_date)
            updated_dates: list[date] = []
            unavailable_dates: list[date] = []
            failed_dates: list[date] = []
            errors: list[str] = []
            snapshot_service = SnapshotService(repo, self.market_data)
            existing_event_at = {
                snapshot.trade_date: self._utc(snapshot.event_at)
                for snapshot in repo.list_snapshots(account_id)
                if snapshot.point_type == SnapshotPointType.TRADING.value
            }
            builder = NavSeriesBuilder(repo=repo)
            all_events, baseline = builder.prepare(account_id)
            events = [
                event
                for event in all_events
                if event.event_type not in {NavReplayEventType.INITIAL, NavReplayEventType.MARKET_VALUATION}
            ]
            valuation_events, gaps, valuation_failures = self._valuation_events(
                snapshot_service, events, dates, baseline
            )
            for trade_date, error in valuation_failures.items():
                failed_dates.append(trade_date)
                errors.append(f"{trade_date.isoformat()}: {error}")
            if failed_dates:
                raise RuntimeError("snapshot recalculation failed: " + "; ".join(errors))
            events.extend(valuation_events)
            replay = NavSeriesReplay().replay(events, baseline)
            by_date = {
                point.trade_date: point
                for point in replay.points
                if point.event_type is NavReplayEventType.MARKET_VALUATION
            }
            snapshots = []
            for trade_date in dates:
                if trade_date in gaps:
                    unavailable_dates.append(trade_date)
                    repo.upsert_valuation_gap(account_id, trade_date, gaps[trade_date][0], gaps[trade_date][1])
                    continue
                point = by_date.get(trade_date)
                if point is None or point.nav is None:
                    unavailable_dates.append(trade_date)
                    continue
                snapshots.append(
                    self._snapshot_values(
                        repo,
                        account_id,
                        trade_date,
                        point,
                        existing_event_at.get(
                            trade_date,
                            point.event_at or datetime.combine(trade_date, time.max, tzinfo=timezone.utc),
                        ),
                    )
                )
                existing_gap = repo.get_valuation_gap(account_id, trade_date)
                if existing_gap is not None and not existing_gap.resolved:
                    repo.upsert_valuation_gap(account_id, trade_date, [], [], resolved=True)
                updated_dates.append(trade_date)
            repo.replace_trading_snapshots(account_id, start_date, end_date, snapshots)

            if failed_dates:
                raise RuntimeError(
                    "snapshot recalculation failed for "
                    + ", ".join(day.isoformat() for day in failed_dates)
                    + (f": {'; '.join(errors)}" if errors else "")
                )
            if owns_session:
                current_session.commit()
            return SnapshotRecalculationResult(account_id, updated_dates, unavailable_dates, failed_dates, errors)
        except BaseException:
            current_session.rollback()
            raise
        finally:
            if owns_session:
                current_session.close()

    @staticmethod
    def _dates_with_valuation_state(
        repo: PaperTradingRepository, account_id: int, start_date: date, end_date: date
    ) -> list[date]:
        snapshot_dates = {
            trade_date
            for (trade_date,) in repo.session.query(PaperAccountSnapshot.trade_date)
            .filter(
                PaperAccountSnapshot.account_id == account_id,
                PaperAccountSnapshot.point_type == "trading",
                PaperAccountSnapshot.trade_date >= start_date,
                PaperAccountSnapshot.trade_date <= end_date,
            )
            .all()
        }
        gap_dates = {
            trade_date
            for (trade_date,) in repo.session.query(PaperValuationGap.trade_date)
            .filter(
                PaperValuationGap.account_id == account_id,
                PaperValuationGap.trade_date >= start_date,
                PaperValuationGap.trade_date <= end_date,
            )
            .all()
        }
        # The bounded start date is the corporate-action event date. Include it
        # even when no prior snapshot or gap exists for that date.
        event_dates = {
            event.trade_date
            for event in repo.list_replay_events(account_id)
            if event.trade_date is not None and start_date <= event.trade_date <= end_date
        }
        active_dates = {start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)}
        return sorted(snapshot_dates | gap_dates | event_dates | active_dates)

    def _valuation_events(
        self,
        snapshot_service: SnapshotService,
        events: list[ReplayEvent],
        dates: list[date],
        baseline: dict[str, Any],
    ) -> tuple[
        list[ReplayEvent],
        dict[date, tuple[list[str], list[dict[str, Any]]]],
        dict[date, str],
    ]:
        replay = NavSeriesReplay().replay(events, baseline)
        points = replay.points
        valuation_events: list[ReplayEvent] = []
        gaps: dict[date, tuple[list[str], list[dict[str, Any]]]] = {}
        failures: dict[date, str] = {}
        for trade_date in dates:
            prior = [point for point in points if point.trade_date <= trade_date]
            point = prior[-1] if prior else self._baseline_point(baseline)
            holdings = {} if point is None or point.holdings is None else point.holdings
            valuations = [
                PositionValuation(
                    holding_key.split(":", 1)[1],
                    holding_key.split(":", 1)[0] or None,
                    trade_date,
                    None,
                    None,
                    None,
                    "missing_replay_market",
                )
                for holding_key, quantity in holdings.items()
                if quantity > 0
            ]
            resolved = []
            for item in valuations:
                position = type("Position", (), {"symbol": item.symbol, "market": item.market})()
                resolved.extend(snapshot_service._resolve_valuations([position], trade_date))
            unavailable = [item for item in resolved if item.price is None]
            provider_errors = [item for item in unavailable if item.error == "market_data_error"]
            if provider_errors:
                failures[trade_date] = "; ".join(
                    sorted({item.error or "market_data_error" for item in provider_errors})
                )
                continue
            if unavailable:
                details = sorted(
                    (snapshot_service._valuation_detail(item) for item in unavailable),
                    key=snapshot_service._detail_sort_key,
                )
                gaps[trade_date] = ([detail["symbol"] for detail in details], details)
                valuation_events.append(
                    ReplayEvent(
                        event_at=datetime.combine(trade_date, time.max, tzinfo=timezone.utc),
                        trade_date=trade_date,
                        event_type=NavReplayEventType.MARKET_VALUATION,
                        source_id=f"recalculation:valuation:{trade_date.isoformat()}",
                        source_kind="recalculation",
                        payload={"valuation_quality": "gap", "valuation_details": details},
                        quality_status=SnapshotQualityStatus.INVALID,
                    )
                )
                continue
            market_values = {
                f"{item.market or ''}:{item.symbol}": holdings[f"{item.market or ''}:{item.symbol}"]
                * (item.price if item.price is not None else Decimal("0"))
                for item in resolved
            }
            market_value = sum(market_values.values(), Decimal("0"))
            cash = Decimal("0") if point is None or point.cash is None else point.cash
            cash_frozen = Decimal("0") if point is None else point.cash_frozen
            pending_settlement = Decimal("0") if point is None else point.pending_settlement
            stale_details = tuple(
                snapshot_service._valuation_detail(item) for item in resolved if item.quality == "stale_suspended"
            )
            valuation_events.append(
                ReplayEvent(
                    event_at=datetime.combine(trade_date, time.max, tzinfo=timezone.utc),
                    trade_date=trade_date,
                    event_type=NavReplayEventType.MARKET_VALUATION,
                    source_id=f"recalculation:valuation:{trade_date.isoformat()}",
                    source_kind="recalculation",
                    payload={
                        "total_assets": cash + cash_frozen + pending_settlement + market_value,
                        "market_values": market_values,
                        "valuation_quality": "stale_suspended" if stale_details else "current",
                        "valuation_details": stale_details,
                    },
                    quality_status=SnapshotQualityStatus.VALID,
                )
            )
        return valuation_events, gaps, failures

    @staticmethod
    def _baseline_point(baseline: dict[str, Any]) -> Any:
        return type(
            "BaselinePoint",
            (),
            {
                "cash": Decimal(str(baseline["cash"])),
                "cash_frozen": Decimal(str(baseline.get("cash_frozen", "0"))),
                "pending_settlement": Decimal(str(baseline.get("pending_settlement", "0"))),
                "holdings": dict(baseline.get("holdings", {})),
                "costs": dict(baseline.get("costs", {})),
                "cumulative_deposit": Decimal(str(baseline.get("cumulative_deposit", baseline["cash"]))),
                "cumulative_withdrawal": Decimal(str(baseline.get("cumulative_withdrawal", "0"))),
            },
        )()

    @staticmethod
    def _snapshot_values(
        repo: PaperTradingRepository, account_id: int, trade_date: date, point: Any, event_at: datetime
    ) -> dict[str, Any]:
        cash = point.cash if point.cash is not None else Decimal("0")
        cash_frozen = point.cash_frozen
        total_assets = point.total_assets if point.total_assets is not None else Decimal("0")
        pending_settlement = point.pending_settlement
        market_value = total_assets - cash - cash_frozen - pending_settlement
        return {
            "account_id": account_id,
            "trade_date": trade_date,
            "event_at": event_at,
            "quality_status": SnapshotQualityStatus.VALID.value,
            "valuation_quality": point.valuation_quality or "current",
            "valuation_details": list(point.valuation_details) or None,
            "cash_available": cash,
            "cash_frozen": cash_frozen,
            "market_value": market_value,
            "total_assets": total_assets,
            "realized_pnl": Decimal("0"),
            "unrealized_pnl": market_value - sum((point.costs or {}).values(), Decimal("0")),
            "position_count": sum(1 for quantity in (point.holdings or {}).values() if quantity > 0),
            "order_count": repo.count_orders(account_id, trade_date),
            "trade_count": repo.count_trades(account_id, trade_date),
            "net_asset_value": point.nav,
            "share_count": point.share_count,
            "cumulative_deposit": point.cumulative_deposit,
            "cumulative_withdrawal": point.cumulative_withdrawal,
            "net_cash_flow": point.net_cash_flow,
            "pending_settlement": pending_settlement,
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
