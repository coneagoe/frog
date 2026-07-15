from decimal import Decimal

import pytest

from paper_trading.domain.enums import OrderSide
from paper_trading.domain.fees import DEFAULT_FEE_PRESET, FEE_PRESETS, FeeConfig, calculate_a_share_fees


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


def test_fee_config_allows_zero_values():
    config = FeeConfig(
        commission_rate=Decimal("0"),
        min_commission=Decimal("0"),
        stamp_duty_rate=Decimal("0"),
        transfer_fee_rate=Decimal("0"),
    )

    assert config.commission_rate == Decimal("0")
    assert config.min_commission == Decimal("0")
    assert config.stamp_duty_rate == Decimal("0")
    assert config.transfer_fee_rate == Decimal("0")


@pytest.mark.parametrize(
    "field",
    ["commission_rate", "min_commission", "stamp_duty_rate", "transfer_fee_rate"],
)
def test_fee_config_rejects_negative_values(field):
    values = {
        "commission_rate": Decimal("0.0003"),
        "min_commission": Decimal("5.00"),
        "stamp_duty_rate": Decimal("0.0005"),
        "transfer_fee_rate": Decimal("0.00001"),
    }
    values[field] = Decimal("-0.0001")

    with pytest.raises(ValueError, match=field):
        FeeConfig(**values)


def test_a_share_fee_preset_matches_default_fee_config():
    preset = FEE_PRESETS[DEFAULT_FEE_PRESET]

    assert preset.commission_rate == Decimal("0.0003")
    assert preset.min_commission == Decimal("5.00")
    assert preset.stamp_duty_rate == Decimal("0.0005")
    assert preset.transfer_fee_rate == Decimal("0.00001")
