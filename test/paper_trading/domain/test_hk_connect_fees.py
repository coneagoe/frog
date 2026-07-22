from decimal import Decimal

from paper_trading.domain.enums import OrderSide
from paper_trading.domain.hk_connect_fees import (
    HkFeeConfig,
    calculate_hk_connect_fees,
)


def test_hk_buy_fees():
    config = HkFeeConfig(
        commission_rate=Decimal("0.0002"),
        min_commission=Decimal("18.00"),
        stamp_duty_rate=Decimal("0.0013"),
        trading_fee_rate=Decimal("0.0000565"),
        sfc_levy_rate=Decimal("0.0000027"),
        afrc_levy_rate=Decimal("0.0000015"),
        settlement_fee_rate=Decimal("0.00002"),
    )
    fees = calculate_hk_connect_fees(OrderSide.BUY, Decimal("40000.00"), config)
    assert fees.commission >= Decimal("18.00")  # minimum commission applies
    assert fees.trading_fee > Decimal("0")
    assert fees.total > Decimal("0")


def test_hk_sell_fees_include_stamp():
    config = HkFeeConfig()
    fees = calculate_hk_connect_fees(OrderSide.SELL, Decimal("50000.00"), config)
    assert fees.stamp_duty > Decimal("0")


def test_hk_sfc_and_afrc_levy():
    config = HkFeeConfig()
    fees = calculate_hk_connect_fees(OrderSide.BUY, Decimal("100000.00"), config)
    assert fees.sfc_levy > Decimal("0")
    assert fees.afrc_levy > Decimal("0")
    assert fees.settlement_fee >= Decimal("0")


def test_hk_min_commission_applied():
    config = HkFeeConfig(commission_rate=Decimal("0.0001"), min_commission=Decimal("50.00"))
    fees = calculate_hk_connect_fees(OrderSide.BUY, Decimal("100.00"), config)
    assert fees.commission == Decimal("50.00")


def test_hk_fee_config_defaults():
    config = HkFeeConfig()
    assert config.commission_rate == Decimal("0.00027")
    assert config.min_commission == Decimal("18.00")
    assert config.stamp_duty_rate == Decimal("0.0013")
