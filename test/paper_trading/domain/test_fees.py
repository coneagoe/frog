from decimal import Decimal

from paper_trading.domain.enums import OrderSide
from paper_trading.domain.fees import FeeConfig, calculate_a_share_fees


def test_buy_fee_uses_minimum_commission_and_transfer_fee():
    fees = calculate_a_share_fees(
        side=OrderSide.BUY,
        amount=Decimal("1000.00"),
        config=FeeConfig(
            commission_rate=Decimal("0.0003"),
            min_commission=Decimal("5.00"),
            transfer_fee_rate=Decimal("0.00001"),
        ),
    )

    assert fees.commission == Decimal("5.00")
    assert fees.stamp_duty == Decimal("0.00")
    assert fees.transfer_fee == Decimal("0.01")
    assert fees.total == Decimal("5.01")


def test_sell_fee_includes_stamp_duty():
    fees = calculate_a_share_fees(
        side=OrderSide.SELL,
        amount=Decimal("20000.00"),
        config=FeeConfig(
            commission_rate=Decimal("0.0003"),
            min_commission=Decimal("5.00"),
            stamp_duty_rate=Decimal("0.0005"),
        ),
    )

    assert fees.commission == Decimal("6.00")
    assert fees.stamp_duty == Decimal("10.00")
    assert fees.total == Decimal("16.20")
