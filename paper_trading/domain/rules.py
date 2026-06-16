from decimal import Decimal

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
