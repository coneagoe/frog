from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean, stdev
from typing import Callable, Literal, cast
from zoneinfo import ZoneInfo

from paper_trading.domain.enums import CashEventType, MigrationRepairReason, SnapshotPointType, SnapshotQualityStatus
from paper_trading.schemas.analytics import (
    ActivityAnalytics,
    ActivitySummary,
    AnalyticsEvent,
    AnalyticsResponse,
    AnalyticsUnavailableResponse,
    CashFlowAnalyticsEvent,
    ExecutionAnalytics,
    MetricValue,
    OverviewAnalytics,
    RejectReasonBucket,
    RiskAnalytics,
    RoundTripResponse,
    SnapshotAnalyticsEvent,
    TradeQualityAnalytics,
    ValuationGapResponse,
)
from paper_trading.storage.models import (
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperOrder,
    PaperPositionRoundTrip,
    PaperValuationGap,
)
from paper_trading.storage.repository import PaperTradingRepository

_QUANTIZE = Decimal("0.000001")


class AnalyticsService:
    def __init__(self, repo: PaperTradingRepository, today_provider: Callable[[], date] | None = None):
        self.repo = repo
        self.today_provider = today_provider or (lambda: datetime.now(ZoneInfo("Asia/Shanghai")).date())

    def get_account_analytics(self, account_id: int) -> AnalyticsResponse | AnalyticsUnavailableResponse:
        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        if account.migration_repair_reason is not None:
            return AnalyticsUnavailableResponse(reason=MigrationRepairReason(account.migration_repair_reason))
        orders = self.repo.list_orders(account_id)
        snapshots = self.repo.list_snapshots(account_id)
        ledger_entries = self.repo.list_cash_ledger(account_id)
        round_trips = self.repo.list_round_trips(account_id)
        return AnalyticsResponse(
            overview=self._overview(account.initial_cash, snapshots),
            activity=self._activity(orders),
            execution=self._execution(orders),
            trade_quality=self._trade_quality(round_trips),
            risk=self._risk(snapshots),
            valuation_gaps=self._valuation_gaps(account_id),
            event_series=self._event_series(snapshots, ledger_entries),
        )

    def _valuation_gaps(self, account_id: int) -> list[ValuationGapResponse]:
        gaps = (
            self.repo.session.query(PaperValuationGap)
            .filter(PaperValuationGap.account_id == account_id)
            .order_by(PaperValuationGap.trade_date.asc(), PaperValuationGap.id.asc())
            .all()
        )
        return [
            ValuationGapResponse(
                trade_date=gap.trade_date,
                missing_symbols=list(gap.missing_symbols),
                details=list(gap.details),
                resolved=gap.resolved,
            )
            for gap in gaps
        ]

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    @staticmethod
    def _snapshot_nav(snapshot: PaperAccountSnapshot) -> Decimal | None:
        if snapshot.quality_status != SnapshotQualityStatus.VALID.value or snapshot.net_asset_value is None:
            return None
        nav = Decimal(snapshot.net_asset_value)
        if not nav.is_finite() or nav <= 0:
            return None
        return nav.quantize(_QUANTIZE)

    @staticmethod
    def _nav_series(snapshots: list[PaperAccountSnapshot]) -> list[Decimal]:
        if not snapshots:
            return []
        first = snapshots[0]
        if first.point_type != SnapshotPointType.INITIAL.value:
            return []
        first_nav = AnalyticsService._snapshot_nav(first)
        if first_nav is None:
            return []
        values = [first_nav]
        for snapshot in snapshots[1:]:
            nav = AnalyticsService._snapshot_nav(snapshot)
            if nav is not None:
                values.append(nav)
        return values

    @staticmethod
    def _linked_total_return(snapshots: list[PaperAccountSnapshot]) -> MetricValue:
        navs = AnalyticsService._nav_series(snapshots)
        if not navs:
            return MetricValue(value=None, reason="invalid_nav")
        if len(navs) < 2:
            return MetricValue(value=None, reason="insufficient_data")

        linked_return = Decimal("1")
        for previous, current in zip(navs, navs[1:]):
            linked_return *= current / previous
        return MetricValue(value=(linked_return - Decimal("1")).quantize(_QUANTIZE))

    @staticmethod
    def _event_series(
        snapshots: list[PaperAccountSnapshot], ledger_entries: list[PaperCashLedger]
    ) -> list[AnalyticsEvent]:
        events: list[tuple[datetime, int, int, AnalyticsEvent]] = []
        for snapshot in snapshots:
            if snapshot.point_type not in {
                SnapshotPointType.INITIAL.value,
                SnapshotPointType.TRADING.value,
            }:
                continue
            events.append(
                (
                    snapshot.event_at,
                    0,
                    snapshot.id,
                    SnapshotAnalyticsEvent(
                        id=snapshot.id,
                        event_at=snapshot.event_at,
                        point_type=snapshot.point_type,
                        quality_status=snapshot.quality_status,
                        invalid_reason=snapshot.invalid_reason,
                        nav=Decimal(snapshot.net_asset_value).quantize(_QUANTIZE)
                        if snapshot.net_asset_value is not None
                        else None,
                        shares=Decimal(snapshot.share_count).quantize(_QUANTIZE)
                        if snapshot.share_count is not None
                        else None,
                    ),
                )
            )
        for entry in ledger_entries:
            if entry.note == "initial_cash":
                continue
            try:
                event_type = CashEventType(entry.event_type)
            except ValueError:
                continue
            if event_type not in {CashEventType.DEPOSIT, CashEventType.WITHDRAWAL}:
                continue
            event_name = cast(Literal["deposit", "withdrawal"], event_type.value)
            events.append(
                (
                    entry.occurred_at,
                    1,
                    entry.id,
                    CashFlowAnalyticsEvent(
                        event_type=event_name,
                        id=entry.id,
                        occurred_at=entry.occurred_at,
                        amount=Decimal(entry.amount).quantize(Decimal("0.0001")),
                        effective_nav=Decimal(entry.net_asset_value).quantize(_QUANTIZE)
                        if entry.net_asset_value is not None
                        else None,
                        share_delta=Decimal(entry.share_delta).quantize(_QUANTIZE)
                        if entry.share_delta is not None
                        else None,
                    ),
                )
            )
        return [event for _, _, _, event in sorted(events, key=lambda item: item[:3])]

    def _overview(
        self,
        initial_cash: Decimal,
        snapshots: list[PaperAccountSnapshot],
    ) -> OverviewAnalytics:
        if not snapshots:
            return OverviewAnalytics(total_return=MetricValue(value=None, reason="insufficient_data"))

        latest = snapshots[-1]
        total_return = self._linked_total_return(snapshots)
        simple_asset_return = MetricValue(value=None, reason="invalid_initial_cash")
        if initial_cash and initial_cash > 0:
            simple_asset_return = MetricValue(
                value=((Decimal(latest.total_assets) - initial_cash) / initial_cash).quantize(_QUANTIZE)
            )

        return OverviewAnalytics(
            total_assets=Decimal(latest.total_assets).quantize(Decimal("0.0001")),
            cash_available=Decimal(latest.cash_available).quantize(Decimal("0.0001")),
            market_value=Decimal(latest.market_value).quantize(Decimal("0.0001")),
            realized_pnl=Decimal(latest.realized_pnl).quantize(Decimal("0.0001")),
            unrealized_pnl=Decimal(latest.unrealized_pnl).quantize(Decimal("0.0001")),
            net_asset_value=Decimal(latest.net_asset_value).quantize(_QUANTIZE)
            if latest.net_asset_value is not None
            else None,
            share_count=Decimal(latest.share_count).quantize(_QUANTIZE) if latest.share_count is not None else None,
            total_return=total_return,
            simple_asset_return=simple_asset_return,
        )

    # ------------------------------------------------------------------
    # Activity
    # ------------------------------------------------------------------
    def _activity(self, orders: list[PaperOrder]) -> ActivityAnalytics | None:
        coverage_end = self.today_provider()
        orders = [order for order in orders if order.trade_date <= coverage_end]
        if not orders:
            return None
        coverage_start = min(order.trade_date for order in orders)
        return ActivityAnalytics(
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            daily=self._activity_summary(orders, coverage_start, coverage_end, "daily"),
            weekly=self._activity_summary(orders, coverage_start, coverage_end, "weekly"),
            monthly=self._activity_summary(orders, coverage_start, coverage_end, "monthly"),
        )

    @staticmethod
    def _activity_summary(
        orders: list[PaperOrder],
        coverage_start: date,
        coverage_end: date,
        granularity: Literal["daily", "weekly", "monthly"],
    ) -> ActivitySummary:
        dates = AnalyticsService._dates_inclusive(coverage_start, coverage_end)
        if granularity == "daily":
            denominator = (coverage_end - coverage_start).days + 1
        elif granularity == "weekly":
            denominator = len({(current.isocalendar().year, current.isocalendar().week) for current in dates})
        else:
            denominator = len({(current.year, current.month) for current in dates})

        total = len(orders)
        successful = sum(1 for order in orders if order.status == "filled")
        failed = sum(1 for order in orders if order.status == "rejected")

        def average(count: int) -> Decimal:
            return (Decimal(count) / Decimal(denominator)).quantize(_QUANTIZE)

        return ActivitySummary(
            total_orders=average(total),
            successful_orders=average(successful),
            failed_orders=average(failed),
        )

    @staticmethod
    def _dates_inclusive(start: date, end: date) -> list[date]:
        return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _execution(self, orders: list[PaperOrder]) -> ExecutionAnalytics:
        total = len(orders)
        filled = sum(1 for o in orders if o.status == "filled")
        rejected = sum(1 for o in orders if o.status == "rejected")

        if total == 0:
            fill_rate = MetricValue(value=None, reason="insufficient_data")
            rejection_rate = MetricValue(value=None, reason="insufficient_data")
        else:
            fill_rate = MetricValue(value=(Decimal(filled) / Decimal(total)).quantize(_QUANTIZE))
            rejection_rate = MetricValue(value=(Decimal(rejected) / Decimal(total)).quantize(_QUANTIZE))

        reasons: dict[str, int] = {}
        for o in orders:
            if o.status == "rejected" and o.rejection_code:
                reasons[o.rejection_code] = reasons.get(o.rejection_code, 0) + 1

        return ExecutionAnalytics(
            order_count=total,
            filled_count=filled,
            rejected_count=rejected,
            fill_rate=fill_rate,
            rejection_rate=rejection_rate,
            reject_reasons=[RejectReasonBucket(reason=r, count=c) for r, c in sorted(reasons.items())],
        )

    # ------------------------------------------------------------------
    # Trade Quality
    # ------------------------------------------------------------------
    def _trade_quality(self, round_trips: list[PaperPositionRoundTrip]) -> TradeQualityAnalytics:
        closed = [rt for rt in round_trips if rt.status == "closed"]
        closed_count = len(closed)

        if closed_count == 0:
            return TradeQualityAnalytics(
                closed_count=0,
                win_rate=MetricValue(value=None, reason="insufficient_data"),
                avg_win=MetricValue(value=None, reason="insufficient_data"),
                avg_loss=MetricValue(value=None, reason="insufficient_data"),
                payoff_ratio=MetricValue(value=None, reason="insufficient_data"),
                profit_factor=MetricValue(value=None, reason="insufficient_data"),
                consecutive_wins=0,
                consecutive_losses=0,
                avg_holding_days=MetricValue(value=None, reason="insufficient_data"),
                round_trips=[self._rt_to_response(rt) for rt in self._recent_round_trips_for_display(round_trips)],
            )

        # Sort closed by close date for streak calculation (per spec)
        closed_sorted = sorted(
            closed,
            key=lambda rt: (rt.close_trade_date or date.min, rt.close_trade_id or rt.id),
        )

        winners = [rt for rt in closed if (rt.realized_pnl or 0) > 0]
        losers = [rt for rt in closed if (rt.realized_pnl or 0) < 0]

        win_rate = (Decimal(len(winners)) / Decimal(closed_count)).quantize(_QUANTIZE) if closed_count else Decimal(0)

        avg_win = (
            self._mean_decimal([Decimal(rt.realized_pnl or 0) for rt in winners])
            if winners
            else MetricValue(value=None, reason="no_winners")
        )
        avg_loss = (
            self._mean_decimal([Decimal(rt.realized_pnl or 0) for rt in losers])
            if losers
            else MetricValue(value=None, reason="no_losers")
        )

        payoff_ratio = MetricValue(value=None, reason="insufficient_data")
        if winners and losers:
            avg_win_val = self._mean_decimal([Decimal(rt.realized_pnl or 0) for rt in winners])
            avg_loss_val = self._mean_decimal([Decimal(rt.realized_pnl or 0) for rt in losers])
            if avg_win_val.value and avg_loss_val.value and avg_loss_val.value != 0:
                payoff_ratio = MetricValue(value=(avg_win_val.value / abs(avg_loss_val.value)).quantize(_QUANTIZE))
        elif winners:
            payoff_ratio = MetricValue(value=None, reason="no_losses")

        profit_factor = MetricValue(value=None, reason="insufficient_data")
        if winners:
            total_win = sum((Decimal(rt.realized_pnl or 0) for rt in winners), Decimal("0"))
            total_loss = sum((abs(Decimal(rt.realized_pnl or 0)) for rt in losers), Decimal("0"))
            if total_loss:
                profit_factor = MetricValue(value=(total_win / total_loss).quantize(_QUANTIZE))
            else:
                profit_factor = MetricValue(value=None, reason="no_losses")

        cons_wins, cons_losses = 0, 0
        cur_w, cur_l = 0, 0
        for rt in closed_sorted:
            pnl = rt.realized_pnl or 0
            if pnl > 0:
                cur_w += 1
                cur_l = 0
            elif pnl < 0:
                cur_l += 1
                cur_w = 0
            else:
                # breakeven resets both streaks
                cur_w = 0
                cur_l = 0
            cons_wins = max(cons_wins, cur_w)
            cons_losses = max(cons_losses, cur_l)

        avg_holding = (
            self._mean_decimal([Decimal(rt.holding_days or 0) for rt in closed if rt.holding_days is not None])
            if closed
            else MetricValue(value=None, reason="insufficient_data")
        )

        return TradeQualityAnalytics(
            closed_count=closed_count,
            win_rate=MetricValue(value=win_rate),
            avg_win=avg_win,
            avg_loss=avg_loss,
            payoff_ratio=payoff_ratio,
            profit_factor=profit_factor,
            consecutive_wins=cons_wins,
            consecutive_losses=cons_losses,
            avg_holding_days=avg_holding,
            round_trips=[self._rt_to_response(rt) for rt in self._recent_round_trips_for_display(round_trips)],
        )

    @staticmethod
    def _recent_round_trips_for_display(
        round_trips: list[PaperPositionRoundTrip],
    ) -> list[PaperPositionRoundTrip]:
        """Return at most 20 round trips: closed rows first (newest close date),
        then open rows (newest open date), each group newest-first."""
        _RECENT_LIMIT = 20
        return sorted(
            round_trips,
            key=lambda rt: (
                0 if rt.status == "closed" else 1,
                -(rt.close_trade_date.toordinal()) if rt.close_trade_date else -(rt.open_trade_date.toordinal()),
                -(rt.close_trade_id or 0) if rt.close_trade_date else -(rt.id or 0),
            ),
        )[:_RECENT_LIMIT]

    @staticmethod
    def _mean_decimal(values: list[Decimal]) -> MetricValue:
        if not values:
            return MetricValue(value=None, reason="insufficient_data")
        return MetricValue(value=(sum(values, Decimal("0")) / Decimal(len(values))).quantize(_QUANTIZE))

    @staticmethod
    def _rt_to_response(rt: PaperPositionRoundTrip) -> RoundTripResponse:
        return RoundTripResponse(
            id=rt.id,
            symbol=rt.symbol,
            open_trade_date=rt.open_trade_date,
            close_trade_date=rt.close_trade_date,
            entry_amount=Decimal(rt.entry_amount or 0).quantize(Decimal("0.0001")),
            exit_amount=Decimal(rt.exit_amount or 0).quantize(Decimal("0.0001")),
            fees=Decimal(rt.fees or 0).quantize(Decimal("0.0001")),
            realized_pnl=Decimal(rt.realized_pnl or 0).quantize(Decimal("0.0001")),
            return_pct=Decimal(rt.return_pct).quantize(_QUANTIZE) if rt.return_pct is not None else None,
            holding_days=rt.holding_days,
            status=rt.status,
        )

    # ------------------------------------------------------------------
    # Risk
    # ------------------------------------------------------------------
    def _risk(self, snapshots: list[PaperAccountSnapshot]) -> RiskAnalytics:
        navs = self._nav_series(snapshots)
        if len(navs) < 2:
            metric = MetricValue(value=None, reason="insufficient_data")
            return RiskAnalytics(
                max_drawdown=metric,
                current_drawdown=metric,
                sharpe=metric,
                sortino=metric,
                calmar=metric,
            )

        peak = navs[0]
        max_dd = Decimal("0")
        for nav in navs:
            if nav > peak:
                peak = nav
            dd = (nav - peak) / peak if peak else Decimal("0")
            if dd < max_dd:
                max_dd = dd

        current_dd = ((navs[-1] - max(navs)) / max(navs)).quantize(_QUANTIZE) if max(navs) else Decimal("0.000000")

        # Compute daily returns for sharpe / sortino
        daily_returns: list[Decimal] = []
        for i in range(1, len(navs)):
            prev = navs[i - 1]
            if prev:
                daily_returns.append(((navs[i] - prev) / prev).quantize(_QUANTIZE))

        sharpe = self._compute_sharpe(daily_returns)
        sortino = self._compute_sortino(daily_returns)
        total_ret = ((navs[-1] - navs[0]) / navs[0]).quantize(_QUANTIZE)
        calmar = self._compute_calmar(total_returns=total_ret, max_drawdown=max_dd)

        return RiskAnalytics(
            max_drawdown=MetricValue(value=max_dd.quantize(_QUANTIZE)),
            current_drawdown=MetricValue(value=current_dd.quantize(_QUANTIZE)),
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
        )

    @staticmethod
    def _compute_sharpe(daily_returns: list[Decimal]) -> MetricValue:
        if len(daily_returns) < 3:
            return MetricValue(value=None, reason="insufficient_data")
        returns_float = [float(r) for r in daily_returns]
        avg_ret = mean(returns_float)
        std_ret = stdev(returns_float)
        if std_ret == 0:
            return MetricValue(value=None, reason="no_volatility")
        # Annualised Sharpe (rough: sqrt(252) for daily, but we do simple)
        sharpe_val = (avg_ret / std_ret) * (252**0.5)
        return MetricValue(value=Decimal(str(sharpe_val)).quantize(_QUANTIZE))

    @staticmethod
    def _compute_sortino(daily_returns: list[Decimal]) -> MetricValue:
        if len(daily_returns) < 3:
            return MetricValue(value=None, reason="insufficient_data")
        returns_float = [float(r) for r in daily_returns]
        avg_ret = mean(returns_float)
        downside = [r for r in returns_float if r < 0]
        if not downside:
            return MetricValue(value=None, reason="no_downside_volatility")
        downside_std = stdev(downside) if len(downside) > 1 else abs(downside[0])
        if downside_std == 0:
            return MetricValue(value=None, reason="no_downside_volatility")
        sortino_val = (avg_ret / downside_std) * (252**0.5)
        return MetricValue(value=Decimal(str(sortino_val)).quantize(_QUANTIZE))

    @staticmethod
    def _compute_calmar(total_returns: Decimal, max_drawdown: Decimal) -> MetricValue:
        if max_drawdown == 0:
            return MetricValue(value=None, reason="no_drawdown")
        calmar_val = (total_returns / abs(max_drawdown)).quantize(_QUANTIZE)
        return MetricValue(value=calmar_val)
