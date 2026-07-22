from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from paper_trading.domain.enums import OrderSide

CENT = Decimal("0.01")


@dataclass(frozen=True)
class HkFeeConfig:
    commission_rate: Decimal = Decimal("0.00027")
    min_commission: Decimal = Decimal("18.00")
    stamp_duty_rate: Decimal = Decimal("0.0013")
    trading_fee_rate: Decimal = Decimal("0.0000565")
    sfc_levy_rate: Decimal = Decimal("0.0000027")
    afrc_levy_rate: Decimal = Decimal("0.0000015")
    settlement_fee_rate: Decimal = Decimal("0.00002")

    def __post_init__(self) -> None:
        for field_name in (
            "commission_rate",
            "min_commission",
            "stamp_duty_rate",
            "trading_fee_rate",
            "sfc_levy_rate",
            "afrc_levy_rate",
            "settlement_fee_rate",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class HkFeeBreakdown:
    commission: Decimal
    stamp_duty: Decimal
    trading_fee: Decimal
    sfc_levy: Decimal
    afrc_levy: Decimal
    settlement_fee: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.commission + self.stamp_duty + self.trading_fee + self.sfc_levy + self.afrc_levy + self.settlement_fee
        )


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_hk_connect_fees(
    side: OrderSide,
    amount: Decimal,
    config: HkFeeConfig | None = None,
) -> HkFeeBreakdown:
    cfg = config or HkFeeConfig()
    commission = max(quantize_money(amount * cfg.commission_rate), cfg.min_commission)
    stamp_duty = quantize_money(amount * cfg.stamp_duty_rate) if side == OrderSide.SELL else Decimal("0.00")
    # Round stamp duty up to nearest integer (HK rule)
    stamp_duty = stamp_duty.quantize(CENT)
    trading_fee = quantize_money(amount * cfg.trading_fee_rate)
    sfc_levy = quantize_money(amount * cfg.sfc_levy_rate)
    afrc_levy = quantize_money(amount * cfg.afrc_levy_rate)
    settlement_fee = quantize_money(amount * cfg.settlement_fee_rate)
    # Settlement fee has min 2.00 and max 100.00
    if settlement_fee < Decimal("2.00"):
        settlement_fee = Decimal("2.00")
    elif settlement_fee > Decimal("100.00"):
        settlement_fee = Decimal("100.00")
    return HkFeeBreakdown(
        commission=commission,
        stamp_duty=stamp_duty,
        trading_fee=trading_fee,
        sfc_levy=sfc_levy,
        afrc_levy=afrc_levy,
        settlement_fee=settlement_fee,
    )


def hk_fee_config_from_account(account) -> HkFeeConfig:
    return HkFeeConfig(
        commission_rate=(
            Decimal(account.hk_commission_rate)
            if account.hk_commission_rate is not None
            else HkFeeConfig.commission_rate
        ),
        min_commission=(
            Decimal(account.hk_min_commission) if account.hk_min_commission is not None else HkFeeConfig.min_commission
        ),
        stamp_duty_rate=(
            Decimal(account.hk_stamp_duty_rate)
            if account.hk_stamp_duty_rate is not None
            else HkFeeConfig.stamp_duty_rate
        ),
        trading_fee_rate=(
            Decimal(account.hk_trading_fee_rate)
            if account.hk_trading_fee_rate is not None
            else HkFeeConfig.trading_fee_rate
        ),
        sfc_levy_rate=(
            Decimal(account.hk_sfc_levy_rate) if account.hk_sfc_levy_rate is not None else HkFeeConfig.sfc_levy_rate
        ),
        afrc_levy_rate=(
            Decimal(account.hk_afrc_levy_rate) if account.hk_afrc_levy_rate is not None else HkFeeConfig.afrc_levy_rate
        ),
        settlement_fee_rate=(
            Decimal(account.hk_settlement_fee_rate)
            if account.hk_settlement_fee_rate is not None
            else HkFeeConfig.settlement_fee_rate
        ),
    )
