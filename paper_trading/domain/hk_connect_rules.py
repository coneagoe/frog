from decimal import Decimal

from paper_trading.domain.errors import PaperTradingError


# Hong Kong minimum spread table (price range -> tick size)
_HK_TICK_TABLE: list[tuple[Decimal, Decimal]] = [
    (Decimal("0"), Decimal("10")),  # 0.010
    (Decimal("10"), Decimal("20")),  # 0.020
    (Decimal("20"), Decimal("100")),  # 0.050
    (Decimal("100"), Decimal("200")),  # 0.100
    (Decimal("200"), Decimal("500")),  # 0.200
    (Decimal("500"), Decimal("1000")),  # 0.500
    (Decimal("1000"), Decimal("2000")),  # 1.000
    (Decimal("2000"), Decimal("5000")),  # 2.000
    (Decimal("5000"), Decimal("100000")),  # 5.000
]

_HK_TICK_SIZES: list[Decimal] = [
    Decimal("0.010"),
    Decimal("0.020"),
    Decimal("0.050"),
    Decimal("0.100"),
    Decimal("0.200"),
    Decimal("0.500"),
    Decimal("1.000"),
    Decimal("2.000"),
    Decimal("5.000"),
]


def get_hk_tick_size(price: Decimal) -> Decimal:
    """Return the minimum tick size for a given price level."""
    for (low, high), tick in zip(_HK_TICK_TABLE, _HK_TICK_SIZES):
        if low <= price < high:
            return tick
    return _HK_TICK_SIZES[-1]  # 5.000 for 100000+


def validate_hk_tick_size(price: Decimal, reference_price: Decimal) -> None:
    """Raise if price is not aligned to the applicable HK tick size.

    The tick size is looked up from *reference_price* (a reference price that
    determines which HK price band applies).
    """
    tick_size = get_hk_tick_size(reference_price)
    # Price must be an exact multiple of tick size
    remainder = (price * Decimal("1000")) % (tick_size * Decimal("1000"))
    if remainder != 0:
        raise PaperTradingError(
            "INVALID_TICK_SIZE",
            f"Price {price} is not aligned to HK tick size {tick_size}",
            {"price": str(price), "tick_size": str(tick_size)},
        )


def ensure_hk_lot_size(quantity: int, board_lot: int) -> None:
    """Raise if quantity is not a positive multiple of board lot."""
    if quantity <= 0 or quantity % board_lot != 0:
        raise PaperTradingError(
            "INVALID_LOT_SIZE",
            f"HK Connect orders must use positive {board_lot}-share lots",
            {"quantity": quantity, "board_lot": board_lot},
        )


def ensure_hk_odd_lot_sell(quantity: int, odd_lot_remainder: int, board_lot: int = 100) -> None:
    """Raise if selling more than the odd-lot remainder when not a board lot.

    Board-lot multiples are always allowed.  If the requested quantity is not
    a board-lot multiple, it must exactly match the full odd-lot remainder.
    """
    if quantity == odd_lot_remainder:
        return  # OK: disposing of the full odd-lot remainder
    if quantity % board_lot == 0:
        return  # OK: board-lot multiple
    raise PaperTradingError(
        "INVALID_ODD_LOT_SELL",
        f"Cannot sell {quantity} shares; odd lot remainder is {odd_lot_remainder}",
        {"quantity": quantity, "odd_lot_remainder": odd_lot_remainder},
    )
