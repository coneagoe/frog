from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from paper_trading.domain.enums import CashEventType, OrderSide, OrderStatus
from paper_trading.domain.fees import DEFAULT_FEE_PRESET, get_fee_preset
from paper_trading.storage.models import (
    PaperAccount,
    PaperAccountSnapshot,
    PaperCashLedger,
    PaperMatchingRun,
    PaperOrder,
    PaperPosition,
    PaperPositionLot,
    PaperPositionRoundTrip,
    PaperTrade,
    PaperTradeValidityCheck,
)


def _validate_fee_values(**values: Decimal | None) -> None:
    for field_name, value in values.items():
        if value is not None and value < 0:
            raise ValueError(f"{field_name} must be non-negative")


def _require_fee_update(**values: Decimal | None) -> None:
    if all(value is None for value in values.values()):
        raise ValueError("at least one fee field is required")


class PaperTradingRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_account(
        self,
        name: str,
        initial_cash: Decimal,
        fee_preset: str | None = None,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> PaperAccount:
        _validate_fee_values(
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )
        preset_name = fee_preset or DEFAULT_FEE_PRESET
        preset = get_fee_preset(preset_name)
        account = PaperAccount(
            name=name,
            initial_cash=initial_cash,
            fee_preset=preset_name,
            commission_rate=commission_rate if commission_rate is not None else preset.commission_rate,
            min_commission=min_commission if min_commission is not None else preset.min_commission,
            stamp_duty_rate=stamp_duty_rate if stamp_duty_rate is not None else preset.stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate if transfer_fee_rate is not None else preset.transfer_fee_rate,
        )
        self.session.add(account)
        self.session.flush()
        self.add_cash_event(account.id, CashEventType.DEPOSIT, initial_cash, note="initial_cash")
        return account

    def get_account(self, account_id: int) -> PaperAccount | None:
        return cast(PaperAccount | None, self.session.get(PaperAccount, account_id))

    def list_accounts(self) -> list[PaperAccount]:
        return list(self.session.query(PaperAccount).order_by(PaperAccount.id.asc()).all())

    def update_account_fees(
        self,
        account_id: int,
        commission_rate: Decimal | None = None,
        min_commission: Decimal | None = None,
        stamp_duty_rate: Decimal | None = None,
        transfer_fee_rate: Decimal | None = None,
    ) -> PaperAccount | None:
        _require_fee_update(
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )
        _validate_fee_values(
            commission_rate=commission_rate,
            min_commission=min_commission,
            stamp_duty_rate=stamp_duty_rate,
            transfer_fee_rate=transfer_fee_rate,
        )
        account = self.get_account(account_id)
        if account is None:
            return None
        if commission_rate is not None:
            account.commission_rate = commission_rate
        if min_commission is not None:
            account.min_commission = min_commission
        if stamp_duty_rate is not None:
            account.stamp_duty_rate = stamp_duty_rate
        if transfer_fee_rate is not None:
            account.transfer_fee_rate = transfer_fee_rate
        self.session.flush()
        return account

    def delete_account(self, account_id: int) -> bool:
        account = self.get_account(account_id)
        if account is None:
            return False

        self.session.query(PaperTradeValidityCheck).filter(PaperTradeValidityCheck.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperCashLedger).filter(PaperCashLedger.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperPositionRoundTrip).filter(PaperPositionRoundTrip.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperTrade).filter(PaperTrade.account_id == account_id).delete(synchronize_session=False)
        self.session.query(PaperOrder).filter(PaperOrder.account_id == account_id).delete(synchronize_session=False)
        self.session.query(PaperPositionLot).filter(PaperPositionLot.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperPosition).filter(PaperPosition.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperAccountSnapshot).filter(PaperAccountSnapshot.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.query(PaperMatchingRun).filter(PaperMatchingRun.account_id == account_id).delete(
            synchronize_session=False
        )
        self.session.delete(account)
        self.session.flush()
        return True

    def add_cash_event(
        self,
        account_id: int,
        event_type: CashEventType | str,
        amount: Decimal,
        order_id: int | None = None,
        trade_id: int | None = None,
        note: str | None = None,
    ) -> PaperCashLedger:
        event = PaperCashLedger(
            account_id=account_id,
            event_type=str(event_type),
            amount=amount,
            order_id=order_id,
            trade_id=trade_id,
            note=note,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def get_cash_available(self, account_id: int) -> Decimal:
        total = (
            self.session.query(func.coalesce(func.sum(PaperCashLedger.amount), 0))
            .filter(PaperCashLedger.account_id == account_id)
            .scalar()
        )
        return Decimal(total).quantize(Decimal("0.0001"))

    def get_cash_frozen(self, account_id: int) -> Decimal:
        total = (
            self.session.query(func.coalesce(func.sum(PaperOrder.frozen_cash), 0))
            .filter(
                PaperOrder.account_id == account_id,
                PaperOrder.status == OrderStatus.ACCEPTED.value,
            )
            .scalar()
        )
        return Decimal(total).quantize(Decimal("0.0001"))

    def create_order(
        self,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        status: OrderStatus,
        frozen_cash: Decimal = Decimal("0"),
        frozen_quantity: int = 0,
        idempotency_key: str | None = None,
        rejection_code: str | None = None,
        rejection_reason: str | None = None,
    ) -> PaperOrder:
        order = PaperOrder(
            account_id=account_id,
            symbol=symbol,
            side=side.value,
            quantity=quantity,
            limit_price=limit_price,
            trade_date=trade_date,
            status=status.value,
            frozen_cash=frozen_cash,
            frozen_quantity=frozen_quantity,
            idempotency_key=idempotency_key,
            rejection_code=rejection_code,
            rejection_reason=rejection_reason,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def get_order(self, order_id: int) -> PaperOrder:
        order = cast(PaperOrder | None, self.session.get(PaperOrder, order_id))
        if order is None:
            raise KeyError(f"paper order not found: {order_id}")
        return order

    def list_orders(self, account_id: int) -> list[PaperOrder]:
        return list(
            self.session.query(PaperOrder)
            .filter(PaperOrder.account_id == account_id)
            .order_by(PaperOrder.id.asc())
            .all()
        )

    def list_cash_ledger(self, account_id: int) -> list[PaperCashLedger]:
        return list(
            self.session.query(PaperCashLedger)
            .filter(PaperCashLedger.account_id == account_id)
            .order_by(PaperCashLedger.id.asc())
            .all()
        )

    def list_trades(self, account_id: int) -> list[PaperTrade]:
        return list(
            self.session.query(PaperTrade)
            .filter(PaperTrade.account_id == account_id)
            .order_by(PaperTrade.id.asc())
            .all()
        )

    def list_snapshots(self, account_id: int) -> list[PaperAccountSnapshot]:
        return list(
            self.session.query(PaperAccountSnapshot)
            .filter(PaperAccountSnapshot.account_id == account_id)
            .order_by(PaperAccountSnapshot.trade_date.asc())
            .all()
        )

    def get_orders_for_matching(self, trade_date: date, account_id: int | None = None) -> list[PaperOrder]:
        query = self.session.query(PaperOrder).filter(
            PaperOrder.trade_date == trade_date,
            PaperOrder.status == OrderStatus.ACCEPTED.value,
        )
        if account_id is not None:
            query = query.filter(PaperOrder.account_id == account_id)
        return list(query.order_by(PaperOrder.id.asc()).all())

    def update_order_status(
        self,
        order: PaperOrder,
        status: OrderStatus,
        rejection_code: str | None = None,
        rejection_reason: str | None = None,
    ) -> PaperOrder:
        order.status = status.value
        order.rejection_code = rejection_code
        order.rejection_reason = rejection_reason
        order.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return order

    def update_order_validity(self, order: PaperOrder, status: str, reason: str) -> PaperOrder:
        order.validity_status = status
        order.validity_reason = reason
        order.validity_checked_at = datetime.now(timezone.utc)
        order.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return order

    def create_trade_validity_check(self, **values: Any) -> PaperTradeValidityCheck:
        check = PaperTradeValidityCheck(**values)
        self.session.add(check)
        self.session.flush()
        return check

    def list_trade_validity_checks(self, order_id: int) -> list[PaperTradeValidityCheck]:
        return list(
            self.session.query(PaperTradeValidityCheck)
            .filter(PaperTradeValidityCheck.order_id == order_id)
            .order_by(PaperTradeValidityCheck.id.asc())
            .all()
        )

    def get_positions(self, account_id: int) -> list[PaperPosition]:
        return list(
            self.session.query(PaperPosition)
            .filter(PaperPosition.account_id == account_id)
            .order_by(PaperPosition.symbol.asc())
            .all()
        )

    def upsert_position(
        self,
        account_id: int,
        symbol: str,
        total_quantity: int,
        frozen_quantity: int,
        cost_amount: Decimal,
        realized_pnl: Decimal = Decimal("0"),
    ) -> PaperPosition:
        position = self.get_position(account_id, symbol)
        if position is None:
            position = PaperPosition(account_id=account_id, symbol=symbol)
            self.session.add(position)
        position.total_quantity = total_quantity
        position.frozen_quantity = frozen_quantity
        position.cost_amount = cost_amount
        position.realized_pnl = realized_pnl
        self.session.flush()
        return position

    def create_position_lot(
        self,
        account_id: int,
        symbol: str,
        buy_trade_date: date,
        original_quantity: int,
        remaining_quantity: int,
        cost_price: Decimal,
    ) -> PaperPositionLot:
        lot = PaperPositionLot(
            account_id=account_id,
            symbol=symbol,
            buy_trade_date=buy_trade_date,
            original_quantity=original_quantity,
            remaining_quantity=remaining_quantity,
            cost_price=cost_price,
        )
        self.session.add(lot)
        self.session.flush()
        return lot

    def save_snapshot(self, **values: Any) -> PaperAccountSnapshot:
        existing: PaperAccountSnapshot | None = (
            self.session.query(PaperAccountSnapshot)
            .filter(
                PaperAccountSnapshot.account_id == values["account_id"],
                PaperAccountSnapshot.trade_date == values["trade_date"],
            )
            .one_or_none()
        )
        if existing is not None:
            for key, value in values.items():
                setattr(existing, key, value)
            self.session.flush()
            return existing

        snapshot = PaperAccountSnapshot(**values)
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def count_orders(self, account_id: int, trade_date: date) -> int:
        return int(
            self.session.query(func.count(PaperOrder.id))
            .filter(PaperOrder.account_id == account_id, PaperOrder.trade_date == trade_date)
            .scalar()
        )

    def count_trades(self, account_id: int, trade_date: date) -> int:
        return int(
            self.session.query(func.count(PaperTrade.id))
            .filter(PaperTrade.account_id == account_id, PaperTrade.trade_date == trade_date)
            .scalar()
        )

    def update_matching_run_counts(
        self,
        run: PaperMatchingRun,
        processed: int,
        filled: int,
        skipped: int,
        rejected: int,
        failed: int,
        status: str,
    ) -> PaperMatchingRun:
        run.processed_count = processed
        run.filled_count = filled
        run.skipped_count = skipped
        run.rejected_count = rejected
        run.failed_count = failed
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        self.session.flush()
        return run

    def create_matching_run(self, trade_date: date, account_id: int | None, status: str) -> PaperMatchingRun:
        run = PaperMatchingRun(trade_date=trade_date, account_id=account_id, status=status)
        self.session.add(run)
        self.session.flush()
        return run

    def list_matching_runs(self) -> list[PaperMatchingRun]:
        return list(self.session.query(PaperMatchingRun).order_by(PaperMatchingRun.id.asc()).all())

    def get_matching_run(self, run_id: int) -> PaperMatchingRun:
        run = cast(PaperMatchingRun | None, self.session.get(PaperMatchingRun, run_id))
        if run is None:
            raise KeyError(f"paper matching run not found: {run_id}")
        return run

    def create_trade(
        self,
        order_id: int,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        price: Decimal,
        amount: Decimal,
        fees: Decimal,
        trade_date: date,
    ) -> PaperTrade:
        trade = PaperTrade(
            order_id=order_id,
            account_id=account_id,
            symbol=symbol,
            side=side.value,
            quantity=quantity,
            price=price,
            amount=amount,
            fees=fees,
            trade_date=trade_date,
        )
        self.session.add(trade)
        self.session.flush()
        return trade

    def get_position(self, account_id: int, symbol: str) -> PaperPosition | None:
        return cast(
            PaperPosition | None,
            self.session.query(PaperPosition)
            .filter(PaperPosition.account_id == account_id, PaperPosition.symbol == symbol)
            .one_or_none(),
        )

    def get_lots(self, account_id: int, symbol: str) -> list[PaperPositionLot]:
        return list(
            self.session.query(PaperPositionLot)
            .filter(
                PaperPositionLot.account_id == account_id,
                PaperPositionLot.symbol == symbol,
            )
            .order_by(PaperPositionLot.buy_trade_date.asc(), PaperPositionLot.id.asc())
            .all()
        )

    def create_round_trip(
        self,
        account_id: int,
        symbol: str,
        open_trade_id: int,
        open_trade_date: date,
        entry_amount: Decimal,
        fees: Decimal,
    ) -> PaperPositionRoundTrip:
        cycle = PaperPositionRoundTrip(
            account_id=account_id,
            symbol=symbol,
            open_trade_id=open_trade_id,
            open_trade_date=open_trade_date,
            entry_amount=entry_amount,
            fees=fees,
            status="open",
        )
        self.session.add(cycle)
        self.session.flush()
        return cycle

    def get_open_round_trip(self, account_id: int, symbol: str) -> PaperPositionRoundTrip | None:
        return cast(
            PaperPositionRoundTrip | None,
            self.session.query(PaperPositionRoundTrip)
            .filter(
                PaperPositionRoundTrip.account_id == account_id,
                PaperPositionRoundTrip.symbol == symbol,
                PaperPositionRoundTrip.status == "open",
            )
            .order_by(PaperPositionRoundTrip.id.desc())
            .first(),
        )

    def update_round_trip(self, cycle: PaperPositionRoundTrip, **values: Any) -> PaperPositionRoundTrip:
        for key, value in values.items():
            setattr(cycle, key, value)
        cycle.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return cycle

    def list_round_trips(self, account_id: int) -> list[PaperPositionRoundTrip]:
        return list(
            self.session.query(PaperPositionRoundTrip)
            .filter(PaperPositionRoundTrip.account_id == account_id)
            .order_by(PaperPositionRoundTrip.open_trade_date.asc(), PaperPositionRoundTrip.id.asc())
            .all()
        )

    def delete_round_trips(self, account_id: int) -> int:
        deleted = (
            self.session.query(PaperPositionRoundTrip)
            .filter(PaperPositionRoundTrip.account_id == account_id)
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return int(deleted)
