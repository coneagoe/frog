from decimal import Decimal

import pytest

from paper_trading.domain.enums import OrderSide, TradeValidityStatus
from paper_trading.domain.errors import PaperTradingError
from paper_trading.domain.rules import (
    ensure_lot_size,
    ensure_price_in_daily_range,
    ensure_sufficient_cash,
    evaluate_daily_trade_validity,
)


def test_ensure_lot_size_accepts_100_share_multiple():
    ensure_lot_size(300)


def test_ensure_lot_size_rejects_non_100_share_multiple():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_lot_size(250)

    assert exc_info.value.code == "INVALID_LOT_SIZE"


def test_ensure_price_in_daily_range_rejects_price_outside_range():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_price_in_daily_range(Decimal("9.90"), low=Decimal("10.00"), high=Decimal("11.00"))

    assert exc_info.value.code == "PRICE_OUT_OF_RANGE"


def test_ensure_sufficient_cash_rejects_shortfall():
    with pytest.raises(PaperTradingError) as exc_info:
        ensure_sufficient_cash(available=Decimal("999.99"), required=Decimal("1000.00"))

    assert exc_info.value.code == "INSUFFICIENT_CASH"


# -- Trade validity tests --


_LOW = Decimal("9.00")
_HIGH = Decimal("10.50")
_LIMIT_UP = Decimal("11.00")
_LIMIT_DOWN = Decimal("9.00")


def test_daily_validity_rejects_price_below_low():
    result = evaluate_daily_trade_validity(
        OrderSide.BUY,
        Decimal("8.99"),
        _LOW,
        _HIGH,
        _LIMIT_UP,
        _LIMIT_DOWN,
    )
    assert result.status == TradeValidityStatus.INVALID
    assert result.reason_code == "PRICE_OUT_OF_DAILY_RANGE"
    assert result.price_in_range is False


def test_daily_validity_marks_buy_limit_up_touch_suspicious():
    result = evaluate_daily_trade_validity(
        OrderSide.BUY,
        Decimal("10.50"),
        _LOW,
        Decimal("11.00"),
        _LIMIT_UP,
        _LIMIT_DOWN,
    )
    assert result.status == TradeValidityStatus.SUSPICIOUS
    assert result.reason_code == "BUY_ON_LIMIT_UP_TOUCH"
    assert result.touched_limit_up is True


def test_daily_validity_rejects_buy_at_touched_limit_up():
    result = evaluate_daily_trade_validity(
        OrderSide.BUY,
        Decimal("11.00"),
        _LOW,
        Decimal("11.00"),
        _LIMIT_UP,
        _LIMIT_DOWN,
    )
    assert result.status == TradeValidityStatus.INVALID
    assert result.reason_code == "BUY_AT_LIMIT_UP_TOUCH"


def test_daily_validity_marks_sell_limit_down_touch_suspicious():
    result = evaluate_daily_trade_validity(
        OrderSide.SELL,
        Decimal("9.50"),
        _LOW,
        _HIGH,
        _LIMIT_UP,
        _LIMIT_DOWN,
    )
    assert result.status == TradeValidityStatus.SUSPICIOUS
    assert result.reason_code == "SELL_ON_LIMIT_DOWN_TOUCH"
    assert result.touched_limit_down is True


def test_daily_validity_rejects_sell_at_touched_limit_down():
    result = evaluate_daily_trade_validity(
        OrderSide.SELL,
        Decimal("9.00"),
        _LOW,
        _HIGH,
        _LIMIT_UP,
        _LIMIT_DOWN,
    )
    assert result.status == TradeValidityStatus.INVALID
    assert result.reason_code == "SELL_AT_LIMIT_DOWN_TOUCH"


def test_daily_validity_accepts_normal_price():
    result = evaluate_daily_trade_validity(
        OrderSide.BUY,
        Decimal("10.00"),
        _LOW,
        _HIGH,
        _LIMIT_UP,
        _LIMIT_DOWN,
    )
    assert result.status == TradeValidityStatus.VALID
    assert result.reason_code == "VALID"
