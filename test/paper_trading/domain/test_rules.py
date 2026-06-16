from decimal import Decimal

import pytest

from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.rules import (
    ensure_lot_size,
    ensure_price_in_daily_range,
    ensure_sufficient_cash,
)


def test_ensure_lot_size_accepts_100_share_multiple():
    ensure_lot_size(300)


def test_ensure_lot_size_rejects_non_100_share_multiple():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_lot_size(250)

    assert exc_info.value.code == "INVALID_LOT_SIZE"


def test_ensure_price_in_daily_range_rejects_price_outside_range():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_price_in_daily_range(
            Decimal("9.90"), low=Decimal("10.00"), high=Decimal("11.00")
        )

    assert exc_info.value.code == "PRICE_OUT_OF_RANGE"


def test_ensure_sufficient_cash_rejects_shortfall():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_sufficient_cash(available=Decimal("999.99"), required=Decimal("1000.00"))

    assert exc_info.value.code == "INSUFFICIENT_CASH"
