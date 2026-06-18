from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import CashEventType, OrderSide, OrderStatus
from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.fees import calculate_a_share_fees
from paper_trading.domain.rules import (
    ensure_lot_size,
    ensure_sufficient_cash,
    ensure_sufficient_position,
)
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository


class OrderService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def place_order(
        self,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        idempotency_key: str | None = None,
    ) -> PaperOrder:
        try:
            ensure_lot_size(quantity)
            if not self.market_data.is_trade_date(trade_date):
                raise PaperTradingError(
                    "INVALID_TRADE_DATE",
                    "Trade date is not open",
                    {"trade_date": str(trade_date)},
                )
            if side == OrderSide.BUY:
                return self._accept_buy_order(
                    account_id,
                    symbol,
                    quantity,
                    limit_price,
                    trade_date,
                    idempotency_key,
                )
            return self._accept_sell_order(account_id, symbol, quantity, limit_price, trade_date, idempotency_key)
        except PaperTradingError as exc:
            return self.repo.create_order(
                account_id=account_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                limit_price=limit_price,
                trade_date=trade_date,
                status=OrderStatus.REJECTED,
                rejection_code=exc.code,
                rejection_reason=exc.message,
                idempotency_key=idempotency_key,
            )

    def cancel_order(self, order_id: int) -> PaperOrder:
        order = self.repo.get_order(order_id)
        if order.status != OrderStatus.ACCEPTED.value:
            raise ValueError("Only accepted orders can be cancelled")
        if Decimal(order.frozen_cash or 0) > 0:
            self.repo.add_cash_event(
                order.account_id,
                CashEventType.RELEASE,
                Decimal(order.frozen_cash),
                order_id=order.id,
                note="cancel_buy_order",
            )
        if int(order.frozen_quantity or 0) > 0:
            position = self.repo.get_position(order.account_id, order.symbol)
            if position is not None:
                position.frozen_quantity = int(position.frozen_quantity or 0) - int(order.frozen_quantity or 0)
        return self.repo.update_order_status(order, OrderStatus.CANCELLED)

    def _accept_buy_order(
        self,
        account_id: int,
        symbol: str,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        idempotency_key: str | None,
    ) -> PaperOrder:
        amount = Decimal(quantity) * limit_price
        frozen_cash = (amount + calculate_a_share_fees(OrderSide.BUY, amount).total).quantize(Decimal("0.0001"))
        ensure_sufficient_cash(self.repo.get_cash_available(account_id), frozen_cash)
        order = self.repo.create_order(
            account_id=account_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            limit_price=limit_price,
            trade_date=trade_date,
            status=OrderStatus.ACCEPTED,
            frozen_cash=frozen_cash,
            idempotency_key=idempotency_key,
        )
        self.repo.add_cash_event(
            account_id,
            CashEventType.FREEZE,
            -frozen_cash,
            order_id=order.id,
            note="buy_order_freeze",
        )
        return order

    def _accept_sell_order(
        self,
        account_id: int,
        symbol: str,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        idempotency_key: str | None,
    ) -> PaperOrder:
        position = self.repo.get_position(account_id, symbol)
        sellable = 0 if position is None else int(position.total_quantity or 0) - int(position.frozen_quantity or 0)
        ensure_sufficient_position(sellable, quantity)
        assert position is not None
        position.frozen_quantity = int(position.frozen_quantity or 0) + quantity
        return self.repo.create_order(
            account_id=account_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            limit_price=limit_price,
            trade_date=trade_date,
            status=OrderStatus.ACCEPTED,
            frozen_quantity=quantity,
            idempotency_key=idempotency_key,
        )
