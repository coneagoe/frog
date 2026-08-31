from collections import defaultdict
from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import REPLAY_REJECTION_MARKER, CashEventType, MatchingRunStatus, OrderSide, OrderStatus
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder, PaperPosition
from paper_trading.storage.repository import PaperTradingRepository


class OrderDeleteService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider,
        hk_metadata: HkConnectMetadataProvider | None = None,
    ):
        self.repo = repo
        self.market_data = market_data
        self.hk_metadata = hk_metadata

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
                self.repo.start_order_replay_lifecycle(o)
                by_date[o.trade_date].append(o)

        for trade_date in sorted(by_date):
            run = self.repo.create_matching_run(
                trade_date,
                account_id,
                MatchingRunStatus.RUNNING.value,
            )
            processed = filled = skipped = rejected = failed = warning_count = 0

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
                elif outcome == "warning":
                    warning_count += 1

            if filled > 0:
                snapshot_outcome = matching_service.snapshot_service.generate_snapshot_or_gap(
                    account_id,
                    trade_date,
                )
                if snapshot_outcome.status == "valuation_gap":
                    warning_count += 1

            status = (
                MatchingRunStatus.FAILED.value
                if failed
                else MatchingRunStatus.COMPLETED_WITH_WARNINGS.value
                if warning_count
                else MatchingRunStatus.COMPLETED.value
            )
            self.repo.update_matching_run_counts(
                run,
                processed,
                filled,
                skipped,
                rejected,
                failed,
                status,
                warning_count=warning_count,
            )

        RoundTripService(self.repo).rebuild_account(account_id)

        # Regenerate validity checks for surviving orders.
        self._regenerate_validity_checks(account_id)
        return True

    def rebuild_account_from(self, account_id: int, start_date: date, triggering_order_ids: list[int]):
        """Rebuild an account's derived ledger after delayed daily-bar data arrives."""
        from paper_trading.services.ledger_rebuild_service import LedgerRebuildService

        return LedgerRebuildService(self.repo, self.market_data, self.hk_metadata).rebuild_account_from(
            account_id,
            start_date,
            trigger_evidence={"source": "delayed_daily_bar", "triggering_order_ids": triggering_order_ids},
            triggering_order_ids=triggering_order_ids,
        )

    @staticmethod
    def _check_sell_reservation(
        position: PaperPosition,
        lots: list,
        order_trade_date: date,
        frozen_qty: int,
        market: str,
    ) -> tuple[bool, str | None, str | None]:
        """Check whether a sell reservation can be restored.

        Returns ``(ok, code, reason)`` where *ok* is True if the reservation
        can proceed, False if the order should be rejected with *code* /
        *reason*.

        Distinguishes market-specific T+1 violations (matured sellable <
        requested) from plain insufficient position (total available < requested).
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

        if market == "etf":
            return (
                False,
                "ETF_T1_VIOLATION",
                f"{REPLAY_REJECTION_MARKER} Insufficient sellable quantity: "
                "ETF T+1 prevents same-day purchases from selling",
            )
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
        lifecycle = self.repo.list_effective_order_events(account_id, order.id)
        outstanding_quantity = max(
            sum((Decimal(event.quantity_delta) for event in lifecycle), Decimal("0")), Decimal("0")
        )
        outstanding_cash = max(-sum((Decimal(event.cash_delta) for event in lifecycle), Decimal("0")), Decimal("0"))
        if side == OrderSide.BUY:
            if outstanding_cash > 0:
                account = self.repo.get_account(account_id)
                available_cash = self.repo.get_cash_available_as_of_internal(account_id, order.trade_date)
                if account is not None:
                    available_cash = account.initial_cash + sum(
                        (
                            Decimal(event.amount)
                            for event in self.repo.list_cash_ledger(account_id)
                            if event.trade_date is not None
                            and event.trade_date <= order.trade_date
                            and event.event_type not in {"deposit", "withdrawal"}
                        ),
                        Decimal("0"),
                    )
                if available_cash >= outstanding_cash:
                    self.repo.add_cash_event(
                        account_id,
                        CashEventType.FREEZE,
                        -outstanding_cash,
                        order_id=order.id,
                        trade_date=order.trade_date,
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
            if outstanding_quantity > 0:
                position = self.repo.get_position(account_id, order.market, order.symbol)
                if position is not None:
                    lots = self.repo.get_lots(account_id, order.market, order.symbol)
                    ok, code, reason = self._check_sell_reservation(
                        position,
                        lots,
                        order.trade_date,
                        int(outstanding_quantity),
                        order.market,
                    )
                    if ok:
                        position.frozen_quantity = int(position.frozen_quantity or 0) + int(outstanding_quantity)
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
        validity_service = TradeValidityService(self.repo, self.market_data, hk_metadata=self.hk_metadata)
        for order in self.repo.list_orders(account_id):
            if order.status in (
                OrderStatus.ACCEPTED.value,
                OrderStatus.FILLED.value,
                OrderStatus.PARTIALLY_FILLED.value,
                OrderStatus.REJECTED.value,
                OrderStatus.CANCELLED.value,
            ):
                validity_service.analyze_order(order)
