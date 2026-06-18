from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from paper_trading.domain.enums import OrderSide

CENT = Decimal("0.01")


@dataclass(frozen=True)
class FeeConfig:
    commission_rate: Decimal = Decimal("0.0003")
    min_commission: Decimal = Decimal("5.00")
    stamp_duty_rate: Decimal = Decimal("0.0005")
    transfer_fee_rate: Decimal = Decimal("0.00001")


@dataclass(frozen=True)
class FeeBreakdown:
    commission: Decimal
    stamp_duty: Decimal
    transfer_fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.stamp_duty + self.transfer_fee


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_a_share_fees(side: OrderSide, amount: Decimal, config: FeeConfig | None = None) -> FeeBreakdown:
    fee_config = config or FeeConfig()
    commission = max(quantize_money(amount * fee_config.commission_rate), fee_config.min_commission)
    stamp_duty = quantize_money(amount * fee_config.stamp_duty_rate) if side == OrderSide.SELL else Decimal("0.00")
    transfer_fee = quantize_money(amount * fee_config.transfer_fee_rate)
    return FeeBreakdown(commission=commission, stamp_duty=stamp_duty, transfer_fee=transfer_fee)
