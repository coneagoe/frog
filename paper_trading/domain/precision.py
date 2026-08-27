from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTUM = Decimal("0.000000000001")
NAV_QUANTUM = Decimal("0.000000000001")
SHARES_QUANTUM = Decimal("0.000000000001")
ROUNDING_MODE = ROUND_HALF_UP


def require_finite(value: Decimal, field_name: str) -> Decimal:
    value = Decimal(value)
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return value


def quantize_account_money(value: Decimal) -> Decimal:
    return require_finite(value, "account money").quantize(MONEY_QUANTUM, rounding=ROUNDING_MODE)


def quantize_nav(value: Decimal) -> Decimal:
    return require_finite(value, "net asset value").quantize(NAV_QUANTUM, rounding=ROUNDING_MODE)


def quantize_shares(value: Decimal) -> Decimal:
    return require_finite(value, "shares").quantize(SHARES_QUANTUM, rounding=ROUNDING_MODE)
