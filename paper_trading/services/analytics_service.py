from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import mean, stdev

from paper_trading.schemas.analytics import (
    ActivityBucket,
    AnalyticsResponse,
    ExecutionAnalytics,
    MetricValue,
    OverviewAnalytics,
    RejectReasonBucket,
    RiskAnalytics,
    RoundTripResponse,
    TradeQualityAnalytics,
)
from paper_trading.storage.models import (
    PaperAccountSnapshot,
    PaperOrder,
    PaperPositionRoundTrip,
    PaperTrade,
)
from paper_trading.storage.repository import PaperTradingRepository

_QUANTIZE = Decimal("0.000001")


class AnalyticsService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def get_account_analytics(self, account_id: int) -> AnalyticsResponse:
        account = self.repo.get_account(account_id)
        if account is None:
            raise KeyError(f"paper account not found: {account_id}")
        orders = self.repo.list_orders(account_id)
        trades = self.repo.list_trades(account_id)
        snapshots = self.repo.list_snapshots(account_id)
        round_trips = self.repo.list_round_trips(account_id)
        return AnalyticsResponse(
            overview=self._overview(account.initial_cash, snapshots),
            activity_daily=self._activity(orders, trades, "daily"),
            activity_weekly=self._activity(orders, trades, "weekly"),
            activity_monthly=self._activity(orders, trades, "monthly"),
            execution=self._execution(orders),
            trade_quality=self._trade_quality(round_trips),
            risk=self._risk(snapshots),
        )

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------
    def _overview(
        self,
        initial_cash: Decimal,
        snapshots: list[PaperAccountSnapshot],
    ) -> OverviewAnalytics:
        if not snapshots:
            return OverviewAnalytics(total_return=MetricValue(value=None, reason="insufficient_data"))

        if not initial_cash:
            latest = snapshots[-1]
            return OverviewAnalytics(
                total_assets=Decimal(latest.total_assets).quantize(Decimal("0.0001")),
                cash_available=Decimal(latest.cash_available).quantize(Decimal("0.0001")),
                market_value=Decimal(latest.market_value).quantize(Decimal("0.0001")),
                realized_pnl=Decimal(latest.realized_pnl).quantize(Decimal("0.0001")),
                unrealized_pnl=Decimal(latest.unrealized_pnl).quantize(Decimal("0.0001")),
                total_return=MetricValue(value=None, reason="invalid_initial_cash"),
            )

        latest = snapshots[-1]
        total_return_val = ((Decimal(latest.total_assets) - initial_cash) / initial_cash).quantize(_QUANTIZE)

        return OverviewAnalytics(
            total_assets=Decimal(latest.total_assets).quantize(Decimal("0.0001")),
            cash_available=Decimal(latest.cash_available).quantize(Decimal("0.0001")),
            market_value=Decimal(latest.market_value).quantize(Decimal("0.0001")),
            realized_pnl=Decimal(latest.realized_pnl).quantize(Decimal("0.0001")),
            unrealized_pnl=Decimal(latest.unrealized_pnl).quantize(Decimal("0.0001")),
            total_return=MetricValue(value=total_return_val),
        )

    # ------------------------------------------------------------------
    # Activity
    # ------------------------------------------------------------------
    def _activity(
        self,
        orders: list[PaperOrder],
        trades: list[PaperTrade],
        granularity: str,
    ) -> list[ActivityBucket]:
        buckets: dict[str, dict[str, int]] = defaultdict(
            lambda: {"order_count": 0, "trade_count": 0, "filled_count": 0, "rejected_count": 0}
        )

        for order in orders:
            key = self._period_key(order.trade_date, granularity)
            buckets[key]["order_count"] += 1
            if order.status == "filled":
                buckets[key]["filled_count"] += 1
            elif order.status == "rejected":
                buckets[key]["rejected_count"] += 1

        for trade in trades:
            key = self._period_key(trade.trade_date, granularity)
            buckets[key]["trade_count"] += 1

        return [
            ActivityBucket(
                period=k,
                order_count=v["order_count"],
                trade_count=v["trade_count"],
                filled_count=v["filled_count"],
                rejected_count=v["rejected_count"],
            )
            for k, v in sorted(buckets.items())
        ]

    @staticmethod
    def _period_key(d: date, granularity: str) -> str:
        if granularity == "daily":
            return d.isoformat()
        if granularity == "weekly":
            iso = d.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        # monthly
        return f"{d.year}-{d.month:02d}"

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
            total_win = sum(Decimal(rt.realized_pnl or 0) for rt in winners)
            total_loss = sum(abs(Decimal(rt.realized_pnl or 0)) for rt in losers) if losers else Decimal(0)
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
        return MetricValue(value=(sum(values) / len(values)).quantize(_QUANTIZE))

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
        if not snapshots:
            return RiskAnalytics(
                max_drawdown=MetricValue(value=None, reason="insufficient_data"),
                current_drawdown=MetricValue(value=None, reason="insufficient_data"),
                sharpe=MetricValue(value=None, reason="insufficient_data"),
                sortino=MetricValue(value=None, reason="insufficient_data"),
                calmar=MetricValue(value=None, reason="insufficient_data"),
            )

        total_assets = [Decimal(s.total_assets) for s in snapshots]
        peak = total_assets[0]
        max_dd = Decimal(0)
        for ta in total_assets:
            if ta > peak:
                peak = ta
            dd = (ta - peak) / peak if peak else Decimal(0)
            if dd < max_dd:
                max_dd = dd

        latest_ta = total_assets[-1]
        current_dd = (latest_ta - peak) / peak if peak else Decimal(0)

        # Compute daily returns for sharpe / sortino
        daily_returns: list[Decimal] = []
        for i in range(1, len(total_assets)):
            prev = total_assets[i - 1]
            if prev:
                daily_returns.append(((total_assets[i] - prev) / prev).quantize(_QUANTIZE))

        sharpe = self._compute_sharpe(daily_returns)
        sortino = self._compute_sortino(daily_returns)
        if not total_assets[0]:
            calmar = MetricValue(value=None, reason="invalid_initial_assets")
        else:
            total_ret = ((latest_ta - total_assets[0]) / total_assets[0]).quantize(_QUANTIZE)
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
