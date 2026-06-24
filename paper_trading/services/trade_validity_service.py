from decimal import Decimal

from paper_trading.domain.enums import OrderSide, TradeValidityStatus
from paper_trading.domain.rules import evaluate_daily_trade_validity
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperOrder, PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository


class TradeValidityService:
    def __init__(self, repo: PaperTradingRepository, market_data: MarketDataProvider):
        self.repo = repo
        self.market_data = market_data

    def analyze_order(self, order: PaperOrder) -> PaperTradeValidityCheck:
        try:
            bar = self.market_data.get_daily_bar(order.symbol, order.trade_date)
        except (KeyError, ValueError) as exc:
            check = self.repo.create_trade_validity_check(
                order_id=order.id,
                account_id=order.account_id,
                symbol=order.symbol,
                trade_date=order.trade_date,
                side=order.side,
                input_price=Decimal(order.limit_price),
                data_granularity="daily",
                daily_low=None,
                daily_high=None,
                limit_up_price=None,
                limit_down_price=None,
                touched_limit_up=None,
                touched_limit_down=None,
                price_in_range=None,
                status=TradeValidityStatus.UNCHECKED.value,
                reason_code="MARKET_DATA_UNAVAILABLE",
                reason_detail=str(exc),
            )
            self.repo.update_order_validity(order, check.status, check.reason_code)
            return check

        side = OrderSide(order.side)
        price = Decimal(order.limit_price)

        if bar.up_limit is None and bar.down_limit is None:
            # Cannot evaluate limit-touch risk without limit prices.
            price_in_range = bar.low <= price <= bar.high
            if not price_in_range:
                status = TradeValidityStatus.INVALID
                reason_code = "PRICE_OUT_OF_DAILY_RANGE"
                reason_detail = "Input price is outside the daily low/high range"
            else:
                status = TradeValidityStatus.UNCHECKED
                reason_code = "LIMIT_PRICE_UNAVAILABLE"
                reason_detail = "Daily limit prices not available; limit-touch analysis skipped"
            check = self.repo.create_trade_validity_check(
                order_id=order.id,
                account_id=order.account_id,
                symbol=order.symbol,
                trade_date=order.trade_date,
                side=order.side,
                input_price=price,
                data_granularity="daily",
                daily_low=bar.low,
                daily_high=bar.high,
                limit_up_price=None,
                limit_down_price=None,
                touched_limit_up=None,
                touched_limit_down=None,
                price_in_range=price_in_range,
                status=status.value,
                reason_code=reason_code,
                reason_detail=reason_detail,
            )
            self.repo.update_order_validity(order, check.status, check.reason_code)
            return check

        result = evaluate_daily_trade_validity(side, price, bar.low, bar.high, bar.up_limit, bar.down_limit)
        check = self.repo.create_trade_validity_check(
            order_id=order.id,
            account_id=order.account_id,
            symbol=order.symbol,
            trade_date=order.trade_date,
            side=order.side,
            input_price=price,
            data_granularity="daily",
            daily_low=bar.low,
            daily_high=bar.high,
            limit_up_price=bar.up_limit,
            limit_down_price=bar.down_limit,
            touched_limit_up=result.touched_limit_up,
            touched_limit_down=result.touched_limit_down,
            price_in_range=result.price_in_range,
            status=result.status.value,
            reason_code=result.reason_code,
            reason_detail=result.reason_detail,
        )
        self.repo.update_order_validity(order, check.status, check.reason_code)
        return check
