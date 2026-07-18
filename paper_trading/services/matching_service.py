from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import (
    CashEventType,
    MatchingRunStatus,
    OrderSide,
    OrderStatus,
)
from paper_trading.domain.fees import calculate_a_share_fees, fee_config_from_account
from paper_trading.domain.rules import ensure_price_in_daily_range
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository


class MatchingService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider,
        snapshot_service: SnapshotService,
    ):
        self.repo = repo
        self.market_data = market_data
        self.snapshot_service = snapshot_service
        self.round_trip_service = RoundTripService(repo)

    def run(self, trade_date: date, account_id: int | None = None):
        run = self.repo.create_matching_run(trade_date, account_id, MatchingRunStatus.RUNNING.value)
        processed = filled = skipped = rejected = failed = 0
        affected_accounts: set[int] = set()
        for order in self.repo.get_orders_for_matching(trade_date, account_id):
            processed += 1
            try:
                bar = self.market_data.get_daily_bar(order.symbol, trade_date)
                if bar.suspended:
                    self._reject_order(order, "SUSPENDED_SYMBOL", "Symbol is suspended")
                    rejected += 1
                    continue
                try:
                    ensure_price_in_daily_range(Decimal(order.limit_price), bar.low, bar.high)
                except Exception:
                    skipped += 1
                    continue
                self._fill_order(order)
                filled += 1
                affected_accounts.add(order.account_id)
            except Exception:
                failed += 1
        for current_account_id in affected_accounts:
            self.snapshot_service.generate_snapshot(current_account_id, trade_date)
        return self.repo.update_matching_run_counts(
            run,
            processed,
            filled,
            skipped,
            rejected,
            failed,
            MatchingRunStatus.COMPLETED.value,
        )

    def _reject_order(self, order: PaperOrder, code: str, reason: str) -> None:
        if Decimal(order.frozen_cash or 0) > 0:
            self.repo.add_cash_event(
                order.account_id,
                CashEventType.RELEASE,
                Decimal(order.frozen_cash),
                order_id=order.id,
                note="reject_order_release",
            )
        if int(order.frozen_quantity or 0) > 0:
            position = self.repo.get_position(order.account_id, order.symbol)
            if position is not None:
                position.frozen_quantity = int(position.frozen_quantity or 0) - int(order.frozen_quantity or 0)
        self.repo.update_order_status(order, OrderStatus.REJECTED, code, reason)

    def _fill_order(self, order: PaperOrder) -> None:
        side = OrderSide(order.side)
        price = Decimal(order.limit_price)
        quantity = int(order.quantity)
        account = self.repo.get_account(order.account_id)
        if account is None:
            raise ValueError(f"paper account not found: {order.account_id}")
        amount = (Decimal(quantity) * price).quantize(Decimal("0.0001"))
        fees = calculate_a_share_fees(side, amount, fee_config_from_account(account)).total.quantize(Decimal("0.0001"))
        trade = self.repo.create_trade(
            order.id,
            order.account_id,
            order.symbol,
            side,
            quantity,
            price,
            amount,
            fees,
            order.trade_date,
            comment=order.comment,
        )
        if side == OrderSide.BUY:
            self._settle_buy(order, trade.id, amount, fees)
            position = self.repo.get_position(order.account_id, order.symbol)
            self.round_trip_service.record_fill(
                trade,
                post_position_quantity=0 if position is None else int(position.total_quantity or 0),
            )
        else:
            self._settle_sell(order, trade.id, amount, fees)
            position = self.repo.get_position(order.account_id, order.symbol)
            self.round_trip_service.record_fill(
                trade,
                post_position_quantity=0 if position is None else int(position.total_quantity or 0),
            )
        order.filled_quantity = quantity
        self.repo.update_order_status(order, OrderStatus.FILLED)

    def _settle_buy(self, order: PaperOrder, trade_id: int, amount: Decimal, fees: Decimal) -> None:
        actual_cost = amount + fees
        release = Decimal(order.frozen_cash or 0) - actual_cost
        if release:
            self.repo.add_cash_event(
                order.account_id,
                CashEventType.RELEASE,
                release,
                order_id=order.id,
                trade_id=trade_id,
            )
        position = self.repo.get_position(order.account_id, order.symbol)
        current_quantity = 0 if position is None else int(position.total_quantity or 0)
        current_cost = Decimal("0") if position is None else Decimal(position.cost_amount or 0)
        self.repo.upsert_position(
            order.account_id,
            order.symbol,
            total_quantity=current_quantity + int(order.quantity),
            frozen_quantity=(0 if position is None else int(position.frozen_quantity or 0)),
            cost_amount=(current_cost + actual_cost).quantize(Decimal("0.0001")),
        )
        self.repo.create_position_lot(
            order.account_id,
            order.symbol,
            order.trade_date,
            int(order.quantity),
            int(order.quantity),
            Decimal(order.limit_price),
        )

    def _settle_sell(self, order: PaperOrder, trade_id: int, amount: Decimal, fees: Decimal) -> None:
        self.repo.add_cash_event(
            order.account_id,
            CashEventType.TRADE,
            amount - fees,
            order_id=order.id,
            trade_id=trade_id,
        )
        position = self.repo.get_position(order.account_id, order.symbol)
        if position is None:
            return
        quantity_to_sell = int(order.quantity)
        remaining = quantity_to_sell
        cost_reduction = Decimal("0")
        for lot in self.repo.get_lots(order.account_id, order.symbol):
            if remaining <= 0:
                break
            used = min(int(lot.remaining_quantity or 0), remaining)
            lot.remaining_quantity = int(lot.remaining_quantity or 0) - used
            cost_reduction += (Decimal(used) * Decimal(lot.cost_price)).quantize(Decimal("0.0001"))
            remaining -= used
        position.total_quantity = int(position.total_quantity or 0) - quantity_to_sell
        position.frozen_quantity = int(position.frozen_quantity or 0) - int(order.frozen_quantity or 0)
        position.cost_amount = (Decimal(position.cost_amount or 0) - cost_reduction).quantize(Decimal("0.0001"))
        position.realized_pnl = (Decimal(position.realized_pnl or 0) + amount - fees - cost_reduction).quantize(
            Decimal("0.0001")
        )
