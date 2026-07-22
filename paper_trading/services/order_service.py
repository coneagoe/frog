import re
from datetime import date
from decimal import Decimal

from paper_trading.domain.enums import CashEventType, Market, OrderSide, OrderStatus
from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.fees import calculate_a_share_fees, fee_config_from_account
from paper_trading.domain.hk_connect_fees import (
    calculate_hk_connect_fees,
    hk_fee_config_from_account,
)
from paper_trading.domain.hk_connect_rules import (
    ensure_hk_lot_size,
    ensure_hk_odd_lot_sell,
    validate_hk_tick_size,
)
from paper_trading.domain.rules import (
    ensure_lot_size,
    ensure_sufficient_cash,
    ensure_sufficient_position,
)
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository


class OrderService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider,
        validity_service: TradeValidityService | None = None,
        hk_metadata: HkConnectMetadataProvider | None = None,
    ):
        self.repo = repo
        self.market_data = market_data
        self.validity_service = validity_service or TradeValidityService(repo, market_data, hk_metadata=hk_metadata)
        self.hk_metadata = hk_metadata

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
        market: str | None = None,
    ) -> PaperOrder:
        resolved_market = Market.A_SHARE
        try:
            try:
                resolved_market = Market(market) if market else Market.A_SHARE
            except ValueError:
                raise PaperTradingError(
                    "INVALID_MARKET",
                    f"Unsupported market: {market}",
                    {"market": market},
                )

            if resolved_market == Market.HK_CONNECT:
                return self._place_hk_order(
                    account_id,
                    symbol,
                    side,
                    quantity,
                    limit_price,
                    trade_date,
                    resolved_market,
                    idempotency_key,
                    comment,
                )
            # A-share path (unchanged logic)
            return self._place_a_share_order(
                account_id,
                symbol,
                side,
                quantity,
                limit_price,
                trade_date,
                resolved_market,
                idempotency_key,
                comment,
            )
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
                market=resolved_market.value,
            )
            self.validity_service.analyze_order(order)
            return order

    def _place_hk_order(
        self,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        market: Market,
        idempotency_key: str | None,
        comment: str | None,
    ) -> PaperOrder:
        if not self._looks_like_hk_symbol(symbol):
            raise PaperTradingError(
                "MARKET_SYMBOL_MISMATCH",
                f"HK Connect symbols must be 5 digits; got {symbol}",
                {"symbol": symbol, "market": market.value},
            )
        meta = self.hk_metadata.get_security(symbol) if self.hk_metadata else None
        if meta is None:
            raise PaperTradingError(
                "UNKNOWN_HK_SECURITY",
                "Symbol is not a recognized HK Connect ordinary stock",
                {"symbol": symbol},
            )
        if not self.market_data.is_trade_date(trade_date):
            raise PaperTradingError(
                "INVALID_TRADE_DATE",
                "Trade date is not open",
                {"trade_date": str(trade_date)},
            )
        validate_hk_tick_size(limit_price, limit_price)
        if side == OrderSide.BUY:
            ensure_hk_lot_size(quantity, meta.board_lot)
            return self._accept_hk_buy_order(
                account_id,
                symbol,
                quantity,
                limit_price,
                trade_date,
                market,
                idempotency_key,
                comment,
            )
        # HK sell: validate odd-lot rules against the current position
        position = self.repo.get_position(account_id, symbol)
        if position is not None:
            total_qty = int(position.total_quantity or 0)
            odd_lot_remainder = total_qty % meta.board_lot
            ensure_hk_odd_lot_sell(quantity, odd_lot_remainder, board_lot=meta.board_lot)
        return self._accept_hk_sell_order(
            account_id,
            symbol,
            quantity,
            limit_price,
            trade_date,
            market,
            idempotency_key,
            comment,
        )

    @staticmethod
    def _looks_like_hk_symbol(symbol: str) -> bool:
        """Return True if symbol is a bare 5-digit string (HK stock code pattern)."""
        return bool(re.match(r"^\d{5}$", symbol))

    def _place_a_share_order(
        self,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        market: Market,
        idempotency_key: str | None,
        comment: str | None,
    ) -> PaperOrder:
        if self._looks_like_hk_symbol(symbol):
            raise PaperTradingError(
                "MARKET_SYMBOL_MISMATCH",
                f"Symbol {symbol} appears to be an HK stock; use market=HK_CONNECT",
                {"symbol": symbol, "market": market.value},
            )
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
                market,
                idempotency_key,
                comment,
            )
        return self._accept_sell_order(
            account_id,
            symbol,
            quantity,
            limit_price,
            trade_date,
            market,
            idempotency_key,
            comment,
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
        market: Market,
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
            market=market.value,
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
        market: Market,
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
            market=market.value,
        )
        self.validity_service.analyze_order(order)
        return order

    def _accept_hk_buy_order(
        self,
        account_id: int,
        symbol: str,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        market: Market,
        idempotency_key: str | None,
        comment: str | None = None,
    ) -> PaperOrder:
        account = self.repo.get_account(account_id)
        if account is None:
            raise ValueError(f"paper account not found: {account_id}")
        amount = Decimal(quantity) * limit_price
        fee_config = hk_fee_config_from_account(account)
        fees = calculate_hk_connect_fees(OrderSide.BUY, amount, fee_config)
        frozen_cash = (amount + fees.total).quantize(Decimal("0.01"))
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
            market=market.value,
        )
        self.repo.add_cash_event(
            account_id,
            CashEventType.FREEZE,
            -frozen_cash,
            order_id=order.id,
            note="hk_buy_order_freeze",
        )
        self.validity_service.analyze_order(order)
        return order

    def _accept_hk_sell_order(
        self,
        account_id: int,
        symbol: str,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        market: Market,
        idempotency_key: str | None,
        comment: str | None = None,
    ) -> PaperOrder:
        position = self.repo.get_position(account_id, symbol)
        total_sellable = (
            0 if position is None else int(position.total_quantity or 0) - int(position.frozen_quantity or 0)
        )
        ensure_sufficient_position(total_sellable, quantity)
        assert position is not None

        # HK Connect allows same-day sell (no T+1 restriction)
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
            market=market.value,
        )
        self.validity_service.analyze_order(order)
        return order
