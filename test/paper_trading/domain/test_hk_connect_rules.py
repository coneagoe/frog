from decimal import Decimal

import pytest

from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.hk_connect_rules import (
    ensure_hk_lot_size,
    ensure_hk_odd_lot_sell,
    validate_hk_tick_size,
    get_hk_tick_size,
)


def test_hk_lot_size_valid():
    ensure_hk_lot_size(100, 100)  # should not raise


def test_hk_lot_size_invalid():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_hk_lot_size(50, 100)
    assert exc_info.value.code == "INVALID_LOT_SIZE"


def test_hk_lot_size_multiple():
    ensure_hk_lot_size(400, 100)  # 4 lots


def test_hk_odd_lot_sell_full_remainder():
    ensure_hk_odd_lot_sell(50, 50)  # selling exactly the odd lot remainder


def test_hk_odd_lot_sell_extra_share():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_hk_odd_lot_sell(51, 50)  # more than odd lot remainder
    assert exc_info.value.code == "INVALID_ODD_LOT_SELL"


def test_hk_odd_lot_sell_partial_remainder_rejected():
    """Selling less than the full odd-lot remainder must be rejected (equality-only)."""
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_hk_odd_lot_sell(40, 50)  # 40 < 50, not equal
    assert exc_info.value.code == "INVALID_ODD_LOT_SELL"


def test_hk_odd_lot_sell_board_lot_allowed():
    # Board lot multiples are always OK, even when remainder exists
    ensure_hk_odd_lot_sell(100, 50)


def test_hk_tick_below_10():
    assert get_hk_tick_size(Decimal("5.00")) == Decimal("0.010")


def test_hk_tick_10_to_20():
    assert get_hk_tick_size(Decimal("15.00")) == Decimal("0.020")


def test_hk_tick_20_to_100():
    assert get_hk_tick_size(Decimal("50.00")) == Decimal("0.050")


def test_hk_tick_100_to_200():
    assert get_hk_tick_size(Decimal("150.00")) == Decimal("0.100")


def test_hk_tick_200_to_500():
    assert get_hk_tick_size(Decimal("300.00")) == Decimal("0.200")


def test_hk_tick_500_to_1000():
    assert get_hk_tick_size(Decimal("700.00")) == Decimal("0.500")


def test_hk_tick_1000_to_2000():
    assert get_hk_tick_size(Decimal("1500.00")) == Decimal("1.000")


def test_hk_tick_2000_to_5000():
    assert get_hk_tick_size(Decimal("3000.00")) == Decimal("2.000")


def test_hk_tick_5000_and_above():
    assert get_hk_tick_size(Decimal("10000.00")) == Decimal("5.000")


def test_hk_validate_tick_aligned():
    # price=5.00, symbol_range=5.01 -> tick=0.010, 5.00 % 0.010 == 0
    validate_hk_tick_size(Decimal("5.00"), Decimal("5.01"))


def test_hk_validate_tick_off_tick():
    # price=5.015, symbol_range=5.00 -> tick=0.010, 5.015 % 0.010 != 0
    with pytest.raises(PaperTradingError) as exc_info:
        validate_hk_tick_size(Decimal("5.015"), Decimal("5.00"))
    assert exc_info.value.code == "INVALID_TICK_SIZE"
