from dataclasses import dataclass
from decimal import Decimal

from paper_trading.domain.enums import OrderSide, TradeValidityStatus
from paper_trading.domain.errors import PaperTradingError


def ensure_lot_size(quantity: int) -> None:
    if quantity <= 0 or quantity % 100 != 0:
        raise PaperTradingError(
            "INVALID_LOT_SIZE",
            "A-share orders must use positive 100-share lots",
            {"quantity": quantity},
        )


def ensure_price_in_daily_range(price: Decimal, low: Decimal, high: Decimal) -> None:
    if price < low or price > high:
        raise PaperTradingError(
            "PRICE_OUT_OF_RANGE",
            "Limit price is outside the daily trading range",
            {"price": str(price), "low": str(low), "high": str(high)},
        )


def ensure_sufficient_cash(available: Decimal, required: Decimal) -> None:
    if available < required:
        raise PaperTradingError(
            "INSUFFICIENT_CASH",
            "Insufficient available cash for the order",
            {"available": str(available), "required": str(required)},
        )


def ensure_sufficient_position(available: int, required: int) -> None:
    if available < required:
        raise PaperTradingError(
            "INSUFFICIENT_POSITION",
            "Insufficient sellable position for the order",
            {"available": available, "required": required},
        )


@dataclass(frozen=True)
class TradeValidityResult:
    status: TradeValidityStatus
    reason_code: str
    reason_detail: str
    price_in_range: bool
    touched_limit_up: bool | None
    touched_limit_down: bool | None


def evaluate_daily_trade_validity(
    side: OrderSide,
    price: Decimal,
    low: Decimal,
    high: Decimal,
    limit_up: Decimal | None,
    limit_down: Decimal | None,
) -> TradeValidityResult:
    price_in_range = low <= price <= high
    if not price_in_range:
        return TradeValidityResult(
            TradeValidityStatus.INVALID,
            "PRICE_OUT_OF_DAILY_RANGE",
            "Input price is outside the daily low/high range",
            False,
            None if limit_up is None else high >= limit_up,
            None if limit_down is None else low <= limit_down,
        )

    touched_limit_up = None if limit_up is None else high >= limit_up
    touched_limit_down = None if limit_down is None else low <= limit_down

    if side == OrderSide.BUY and touched_limit_up:
        assert limit_up is not None  # narrowed by touched_limit_up being truthy
        if price >= limit_up:
            return TradeValidityResult(
                TradeValidityStatus.INVALID,
                "BUY_AT_LIMIT_UP_TOUCH",
                "Buy price is at the touched limit-up price",
                True,
                touched_limit_up,
                touched_limit_down,
            )
        return TradeValidityResult(
            TradeValidityStatus.SUSPICIOUS,
            "BUY_ON_LIMIT_UP_TOUCH",
            "The symbol touched limit-up on this trade date",
            True,
            touched_limit_up,
            touched_limit_down,
        )

    if side == OrderSide.SELL and touched_limit_down:
        assert limit_down is not None  # narrowed by touched_limit_down being truthy
        if price <= limit_down:
            return TradeValidityResult(
                TradeValidityStatus.INVALID,
                "SELL_AT_LIMIT_DOWN_TOUCH",
                "Sell price is at the touched limit-down price",
                True,
                touched_limit_up,
                touched_limit_down,
            )
        return TradeValidityResult(
            TradeValidityStatus.SUSPICIOUS,
            "SELL_ON_LIMIT_DOWN_TOUCH",
            "The symbol touched limit-down on this trade date",
            True,
            touched_limit_up,
            touched_limit_down,
        )

    return TradeValidityResult(
        TradeValidityStatus.VALID,
        "VALID",
        "Price is inside daily range",
        True,
        touched_limit_up,
        touched_limit_down,
    )
