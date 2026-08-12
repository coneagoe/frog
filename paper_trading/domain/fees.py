from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from paper_trading.domain.enums import FeePreset, OrderSide

CENT = Decimal("0.01")
ETF_FEE_PRECISION = Decimal("0.0001")


@dataclass(frozen=True)
class FeeConfig:
    commission_rate: Decimal = Decimal("0.0003")
    min_commission: Decimal = Decimal("5.00")
    stamp_duty_rate: Decimal = Decimal("0.0005")
    transfer_fee_rate: Decimal = Decimal("0.00001")

    def __post_init__(self) -> None:
        for field_name in ("commission_rate", "min_commission", "stamp_duty_rate", "transfer_fee_rate"):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class EtfFeeConfig:
    commission_rate: Decimal = Decimal("0.00006")

    def __post_init__(self) -> None:
        if self.commission_rate < 0:
            raise ValueError("commission_rate must be non-negative")


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


DEFAULT_FEE_PRESET = FeePreset.A_SHARE
FEE_PRESETS: dict[FeePreset, FeeConfig] = {
    DEFAULT_FEE_PRESET: FeeConfig(),
}


def get_fee_preset(name: str | FeePreset | None = None) -> FeeConfig:
    preset_name = name or DEFAULT_FEE_PRESET
    try:
        return FEE_PRESETS[FeePreset(preset_name)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unknown fee preset: {preset_name}") from exc


def fee_config_from_account(account: Any) -> FeeConfig:
    default = get_fee_preset(getattr(account, "fee_preset", None))
    commission_rate = (
        Decimal(account.commission_rate) if account.commission_rate is not None else default.commission_rate
    )
    min_commission = Decimal(account.min_commission) if account.min_commission is not None else default.min_commission
    stamp_duty_rate = (
        Decimal(account.stamp_duty_rate) if account.stamp_duty_rate is not None else default.stamp_duty_rate
    )
    transfer_fee_rate = (
        Decimal(account.transfer_fee_rate) if account.transfer_fee_rate is not None else default.transfer_fee_rate
    )
    return FeeConfig(
        commission_rate=commission_rate,
        min_commission=min_commission,
        stamp_duty_rate=stamp_duty_rate,
        transfer_fee_rate=transfer_fee_rate,
    )


def etf_fee_config_from_account(account: Any) -> EtfFeeConfig:
    rate = account.etf_commission_rate
    return EtfFeeConfig(commission_rate=Decimal(rate) if rate is not None else EtfFeeConfig.commission_rate)


def calculate_a_share_fees(side: OrderSide, amount: Decimal, config: FeeConfig | None = None) -> FeeBreakdown:
    fee_config = config or FeeConfig()
    commission = max(quantize_money(amount * fee_config.commission_rate), fee_config.min_commission)
    stamp_duty = quantize_money(amount * fee_config.stamp_duty_rate) if side == OrderSide.SELL else Decimal("0.00")
    transfer_fee = quantize_money(amount * fee_config.transfer_fee_rate)
    return FeeBreakdown(commission=commission, stamp_duty=stamp_duty, transfer_fee=transfer_fee)


def calculate_etf_fees(side: OrderSide, amount: Decimal, config: EtfFeeConfig | None = None) -> FeeBreakdown:
    del side
    fee_config = config or EtfFeeConfig()
    return FeeBreakdown(
        commission=(amount * fee_config.commission_rate).quantize(ETF_FEE_PRECISION, rounding=ROUND_HALF_UP),
        stamp_duty=Decimal("0.00"),
        transfer_fee=Decimal("0.00"),
    )
