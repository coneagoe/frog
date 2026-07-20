from collections import defaultdict
from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import REPLAY_REJECTION_MARKER, CashEventType, MatchingRunStatus, OrderSide, OrderStatus
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder, PaperPosition
from paper_trading.storage.repository import PaperTradingRepository


class OrderDeleteService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def delete_order(self, order_id: int) -> bool:
        try:
            order = self.repo.get_order(order_id)
        except KeyError:
            return False

        account_id = order.account_id
        self.repo.clear_account_rebuild_state(account_id)
        deleted = self.repo.delete_order(order_id)
        if deleted is None:
            return False
        self.repo.reset_orders_for_replay(account_id)
        # Bulk update with synchronize_session=False leaves stale objects in
        # the identity map; expunge all stale references so subsequent queries
        # return fresh rows from the database.
        self.repo.session.expunge_all()

        # Process surviving orders per date, maintaining (trade_date, id)
        # order within each date.  For each date we create a matching run
        # with counts and generate a snapshot immediately (so the snapshot
        # reflects state at that date, not including later dates).
        matching_service = MatchingService(
            self.repo,
            self.market_data,
            SnapshotService(self.repo, self.market_data),
        )

        orders = self.repo.list_orders(account_id)
        orders.sort(key=lambda o: (o.trade_date, o.id))

        # Group accepted orders by trade_date.
        by_date: dict[date, list[PaperOrder]] = defaultdict(list)
        for o in orders:
            if o.status == OrderStatus.ACCEPTED.value:
                by_date[o.trade_date].append(o)

        for trade_date in sorted(by_date):
            run = self.repo.create_matching_run(
                trade_date,
                account_id,
                MatchingRunStatus.RUNNING.value,
            )
            processed = filled = skipped = rejected = failed = 0

            for order in by_date[trade_date]:
                processed += 1
                self._restore_single_reservation(account_id, order)
                if order.status != OrderStatus.ACCEPTED.value:
                    rejected += 1  # reservation restore already rejected it
                    continue
                outcome = matching_service.match_order(order)
                if outcome == "filled":
                    filled += 1
                elif outcome == "rejected":
                    rejected += 1
                elif outcome == "skipped":
                    skipped += 1
                elif outcome == "failed":
                    failed += 1

            if filled > 0:
                matching_service.snapshot_service.generate_snapshot(
                    account_id,
                    trade_date,
                )

            self.repo.update_matching_run_counts(
                run,
                processed,
                filled,
                skipped,
                rejected,
                failed,
                MatchingRunStatus.COMPLETED.value,
            )

        RoundTripService(self.repo).rebuild_account(account_id)

        # Regenerate validity checks for surviving orders.
        self._regenerate_validity_checks(account_id)
        return True

    @staticmethod
    def _check_sell_reservation(
        position: PaperPosition,
        lots: list,
        order_trade_date: date,
        frozen_qty: int,
    ) -> tuple[bool, str | None, str | None]:
        """Check whether a sell reservation can be restored.

        Returns ``(ok, code, reason)`` where *ok* is True if the reservation
        can proceed, False if the order should be rejected with *code* /
        *reason*.

        Distinguishes A-share T+1 violations (matured sellable < requested)
        from plain insufficient position (total available < requested).
        """
        total_available = int(position.total_quantity or 0) - int(position.frozen_quantity or 0)
        if total_available < frozen_qty:
            return (
                False,
                "INSUFFICIENT_POSITION",
                f"{REPLAY_REJECTION_MARKER} Deleted order removed inventory for sell order",
            )

        # Enough total — now check T+1 maturity.
        matured_qty = sum(int(lot.remaining_quantity or 0) for lot in lots if lot.buy_trade_date < order_trade_date)
        sellable = matured_qty - int(position.frozen_quantity or 0)
        if sellable >= frozen_qty:
            return True, None, None

        return (
            False,
            "A_SHARE_T1_VIOLATION",
            f"{REPLAY_REJECTION_MARKER} 可卖出数量不足：A股 T+1 规则下当日买入部分不可用于卖出",
        )

    def _restore_single_reservation(self, account_id: int, order: PaperOrder) -> None:
        """Restore pre-match reservation for a single ACCEPTED order.

        Called immediately before ``matching_service.match_order(order)``.
        """
        side = OrderSide(order.side)
        if side == OrderSide.BUY:
            frozen_cash = Decimal(order.frozen_cash or 0)
            if frozen_cash > 0:
                if self.repo.get_cash_available(account_id) >= frozen_cash:
                    self.repo.add_cash_event(
                        account_id,
                        CashEventType.FREEZE,
                        -frozen_cash,
                        order_id=order.id,
                        note="buy_order_freeze",
                    )
                else:
                    self.repo.update_order_status(
                        order,
                        OrderStatus.REJECTED,
                        rejection_code="INSUFFICIENT_CASH",
                        rejection_reason=(
                            f"{REPLAY_REJECTION_MARKER} Deleted order removed cash proceeds needed for buy order"
                        ),
                    )
        else:
            frozen_qty = int(order.frozen_quantity or 0)
            if frozen_qty > 0:
                position = self.repo.get_position(account_id, order.symbol)
                if position is not None:
                    lots = self.repo.get_lots(account_id, order.symbol)
                    ok, code, reason = self._check_sell_reservation(
                        position,
                        lots,
                        order.trade_date,
                        frozen_qty,
                    )
                    if ok:
                        position.frozen_quantity = int(position.frozen_quantity or 0) + frozen_qty
                    else:
                        self.repo.update_order_status(order, OrderStatus.REJECTED, code, reason)
                else:
                    self.repo.update_order_status(
                        order,
                        OrderStatus.REJECTED,
                        rejection_code="INSUFFICIENT_POSITION",
                        rejection_reason=f"{REPLAY_REJECTION_MARKER} Deleted order removed inventory for sell order",
                    )

    def _regenerate_validity_checks(self, account_id: int) -> None:
        validity_service = TradeValidityService(self.repo, self.market_data)
        for order in self.repo.list_orders(account_id):
            if order.status in (
                OrderStatus.ACCEPTED.value,
                OrderStatus.FILLED.value,
                OrderStatus.PARTIALLY_FILLED.value,
                OrderStatus.REJECTED.value,
                OrderStatus.CANCELLED.value,
            ):
                validity_service.analyze_order(order)
