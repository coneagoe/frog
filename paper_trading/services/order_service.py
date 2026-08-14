import re
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from paper_trading.domain.enums import CashEventType, Market, OrderSide, OrderStatus
from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.fees import (
    calculate_a_share_fees,
    calculate_etf_fees,
    etf_fee_config_from_account,
    fee_config_from_account,
)
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
    validate_etf_tick_size,
)
from paper_trading.services.etf_eligibility_service import ETFEligibilityService
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.etf_basic import ETFBasic


class OrderService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider,
        validity_service: TradeValidityService | None = None,
        hk_metadata: HkConnectMetadataProvider | None = None,
        etf_eligibility: ETFEligibilityService | None = None,
    ):
        self.repo = repo
        self.market_data = market_data
        self.validity_service = validity_service or TradeValidityService(repo, market_data, hk_metadata=hk_metadata)
        self.hk_metadata = hk_metadata
        self.etf_eligibility = etf_eligibility or ETFEligibilityService(repo)

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
        idempotency_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
        market_error: PaperTradingError | None = None
        try:
            resolved_market = Market(market) if market else Market.A_SHARE
        except ValueError:
            market_error = PaperTradingError(
                "INVALID_MARKET",
                f"Unsupported market: {market}",
                {"market": market},
            )
        if market_error is None and self._is_known_etf_symbol(symbol):
            resolved_market = Market.ETF
        if idempotency_key:
            existing = self.repo.get_order_by_idempotency_key(account_id, idempotency_key)
            if existing is not None:
                if market_error is not None:
                    raise market_error
                if self._matches_order_request(
                    existing,
                    account_id,
                    symbol,
                    side,
                    quantity,
                    limit_price,
                    trade_date,
                    resolved_market,
                ):
                    return existing
                raise PaperTradingError(
                    "IDEMPOTENCY_KEY_CONFLICT",
                    "idempotency key already belongs to a different order",
                )
        try:
            if market_error is not None:
                raise market_error
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
            if resolved_market == Market.ETF:
                return self._place_etf_order(
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
            if resolved_market == Market.A_SHARE and trade_date < date.today():
                return self._place_historical_a_share_order(
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
        except IntegrityError:
            self.repo.session.rollback()
            if idempotency_key:
                existing = self.repo.get_order_by_idempotency_key(account_id, idempotency_key)
                if existing is not None and self._matches_order_request(
                    existing,
                    account_id,
                    symbol,
                    side,
                    quantity,
                    limit_price,
                    trade_date,
                    resolved_market,
                ):
                    return existing
            raise

    @staticmethod
    def _matches_order_request(
        order: PaperOrder,
        account_id: int,
        symbol: str,
        side: OrderSide,
        quantity: int,
        limit_price: Decimal,
        trade_date: date,
        market: Market,
    ) -> bool:
        return bool(
            getattr(order, "account_id") == account_id
            and getattr(order, "symbol") == symbol
            and getattr(order, "side") == side.value
            and getattr(order, "quantity") == quantity
            and Decimal(str(getattr(order, "limit_price"))) == limit_price
            and getattr(order, "trade_date") == trade_date
            and getattr(order, "market") == market.value
        )

    def _is_known_etf_symbol(self, symbol: str) -> bool:
        return bool(re.match(r"^\d{6}$", symbol) and self.repo.session.get(ETFBasic, symbol) is not None)

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
        position = self.repo.get_position(account_id, market, symbol)
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

    def _place_historical_a_share_order(
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
        account = self.repo.get_account(account_id)
        if account is None:
            raise ValueError(f"paper account not found: {account_id}")

        frozen_cash = Decimal("0")
        if side == OrderSide.BUY:
            amount = Decimal(quantity) * limit_price
            fees = calculate_a_share_fees(OrderSide.BUY, amount, fee_config_from_account(account))
            frozen_cash = (amount + fees.total).quantize(Decimal("0.0001"))

        order = self.repo.create_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            trade_date=trade_date,
            status=OrderStatus.ACCEPTED,
            frozen_cash=frozen_cash,
            frozen_quantity=quantity if side == OrderSide.SELL else 0,
            idempotency_key=idempotency_key,
            comment=comment,
            market=market.value,
        )
        self.validity_service.analyze_order(order)

        from paper_trading.services.order_delete_service import OrderDeleteService

        OrderDeleteService(self.repo, self.market_data, self.hk_metadata).rebuild_account_from(
            account_id, trade_date, [order.id]
        )
        return self.repo.get_order(order.id)

    def _place_etf_order(
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
        validation = self.etf_eligibility.validate_etf_eligibility(symbol)
        if not validation.eligible:
            raise PaperTradingError(validation.code, validation.message, {"symbol": symbol, "market": market.value})
        ensure_lot_size(quantity)
        validate_etf_tick_size(limit_price)
        if not self.market_data.is_trade_date(trade_date):
            raise PaperTradingError(
                "INVALID_TRADE_DATE",
                "Trade date is not open",
                {"trade_date": str(trade_date)},
            )
        if trade_date < date.today():
            return self._place_historical_etf_order(
                account_id,
                symbol,
                side,
                quantity,
                limit_price,
                trade_date,
                market,
                idempotency_key,
                comment,
            )
        if side == OrderSide.BUY:
            return self._accept_buy_order(
                account_id, symbol, quantity, limit_price, trade_date, market, idempotency_key, comment
            )
        return self._accept_sell_order(
            account_id, symbol, quantity, limit_price, trade_date, market, idempotency_key, comment
        )

    def _place_historical_etf_order(
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
        account = self.repo.get_account(account_id)
        if account is None:
            raise ValueError(f"paper account not found: {account_id}")

        frozen_cash = Decimal("0")
        if side == OrderSide.BUY:
            amount = Decimal(quantity) * limit_price
            fees = calculate_etf_fees(OrderSide.BUY, amount, etf_fee_config_from_account(account))
            frozen_cash = (amount + fees.total).quantize(Decimal("0.0001"))

        order = self.repo.create_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            trade_date=trade_date,
            status=OrderStatus.ACCEPTED,
            frozen_cash=frozen_cash,
            frozen_quantity=quantity if side == OrderSide.SELL else 0,
            idempotency_key=idempotency_key,
            comment=comment,
            market=market.value,
        )
        self.validity_service.analyze_order(order)

        from paper_trading.services.order_delete_service import OrderDeleteService

        OrderDeleteService(self.repo, self.market_data, self.hk_metadata).rebuild_account_from(
            account_id, trade_date, [order.id]
        )
        return self.repo.get_order(order.id)

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
        if (
            market == Market.A_SHARE
            and trade_date < date.today()
            and not self.repo.has_unresolved_daily_bar_diagnostic(trade_date, market, symbol)
        ):
            raise PaperTradingError(
                "HISTORICAL_TRADE_DATE_NOT_ELIGIBLE",
                "Past trade date is not eligible for retry",
                {"trade_date": str(trade_date), "symbol": symbol},
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
            position = self.repo.get_position(order.account_id, order.market, order.symbol)
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
        fees = (
            calculate_etf_fees(OrderSide.BUY, amount, etf_fee_config_from_account(account))
            if market == Market.ETF
            else calculate_a_share_fees(OrderSide.BUY, amount, fee_config_from_account(account))
        )
        frozen_cash = (amount + fees.total).quantize(Decimal("0.0001"))
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
        position = self.repo.get_position(account_id, market, symbol)
        total_sellable = (
            0 if position is None else int(position.total_quantity or 0) - int(position.frozen_quantity or 0)
        )
        ensure_sufficient_position(total_sellable, quantity)
        assert position is not None

        lots = self.repo.get_lots(account_id, market, symbol)
        matured_qty = sum(int(lot.remaining_quantity or 0) for lot in lots if lot.buy_trade_date < trade_date)
        sellable_matured = matured_qty - int(position.frozen_quantity or 0)
        if quantity > sellable_matured:
            if market == Market.ETF:
                raise PaperTradingError(
                    "ETF_T1_VIOLATION",
                    "Insufficient sellable quantity: ETF T+1 prevents same-day purchases from selling",
                    {
                        "total_quantity": position.total_quantity,
                        "frozen_quantity": position.frozen_quantity,
                        "requested": quantity,
                        "matured_quantity": matured_qty,
                        "trade_date": str(trade_date),
                        "market": market.value,
                    },
                )
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
        position = self.repo.get_position(account_id, market, symbol)
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
