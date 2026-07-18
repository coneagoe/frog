from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import CashEventType, OrderSide, OrderStatus
from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.fees import calculate_a_share_fees, fee_config_from_account
from paper_trading.domain.rules import (
    ensure_lot_size,
    ensure_sufficient_cash,
    ensure_sufficient_position,
)
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository


class OrderService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider,
        validity_service: TradeValidityService | None = None,
    ):
        self.repo = repo
        self.market_data = market_data
        self.validity_service = validity_service or TradeValidityService(repo, market_data)

    def place_order(
        self,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        idempotency_key: str | None = None,
        comment: str | None = None,
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
                    comment,
                )
            return self._accept_sell_order(account_id, symbol, quantity, limit_price, trade_date, idempotency_key, comment)
        except PaperTradingError as exc:
            order = self.repo.create_order(
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
                comment=comment,
            )
            self.validity_service.analyze_order(order)
            return order

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

    def update_order_comment(self, order_id: int, comment: str | None) -> PaperOrder:
        order = self.repo.get_order(order_id)
        return self.repo.update_order_comment(order, comment)

    def _accept_buy_order(
        self,
        account_id: int,
        symbol: str,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        idempotency_key: str | None,
        comment: str | None = None,
    ) -> PaperOrder:
        account = self.repo.get_account(account_id)
        if account is None:
            raise ValueError(f"paper account not found: {account_id}")
        amount = Decimal(quantity) * limit_price
        fee_config = fee_config_from_account(account)
        frozen_cash = (amount + calculate_a_share_fees(OrderSide.BUY, amount, fee_config).total).quantize(
            Decimal("0.0001")
        )
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
            comment=comment,
        )
        self.repo.add_cash_event(
            account_id,
            CashEventType.FREEZE,
            -frozen_cash,
            order_id=order.id,
            note="buy_order_freeze",
        )
        self.validity_service.analyze_order(order)
        return order

    def _accept_sell_order(
        self,
        account_id: int,
        symbol: str,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        idempotency_key: str | None,
        comment: str | None = None,
    ) -> PaperOrder:
        position = self.repo.get_position(account_id, symbol)
        total_sellable = (
            0 if position is None else int(position.total_quantity or 0) - int(position.frozen_quantity or 0)
        )
        ensure_sufficient_position(total_sellable, quantity)
        assert position is not None

        lots = self.repo.get_lots(account_id, symbol)
        matured_qty = sum(int(lot.remaining_quantity or 0) for lot in lots if lot.buy_trade_date < trade_date)
        sellable_matured = matured_qty - int(position.frozen_quantity or 0)
        if quantity > sellable_matured:
            raise PaperTradingError(
                "A_SHARE_T1_VIOLATION",
                "可卖出数量不足：A股 T+1 规则下当日买入部分不可当日卖出",
                {
                    "total_quantity": position.total_quantity,
                    "frozen_quantity": position.frozen_quantity,
                    "requested": quantity,
                    "matured_quantity": matured_qty,
                    "trade_date": str(trade_date),
                },
            )

        position.frozen_quantity = int(position.frozen_quantity or 0) + quantity
        order = self.repo.create_order(
            account_id=account_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            limit_price=limit_price,
            trade_date=trade_date,
            status=OrderStatus.ACCEPTED,
            frozen_quantity=quantity,
            idempotency_key=idempotency_key,
            comment=comment,
        )
        self.validity_service.analyze_order(order)
        return order
