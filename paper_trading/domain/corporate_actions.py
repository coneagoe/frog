from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from paper_trading.domain.enums import CorporateActionType
from paper_trading.domain.errors import (
    InsufficientRightsCashError,
    InvalidCorporateActionInputError,
    InvalidCorporateActionParametersError,
    UnknownCorporateActionTypeError,
)
from paper_trading.domain.precision import (
    quantize_account_money,
    quantize_shares,
    require_finite,
)


@dataclass(frozen=True)
class CorporateActionInput:
    event_type: CorporateActionType
    parameters: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        event_type = _coerce_event_type(self.event_type)
        normalized = {
            name: _finite_input(value, name) for name, value in self.parameters.items()
        }
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "parameters", MappingProxyType(normalized))


@dataclass(frozen=True)
class CorporateActionImpact:
    cash_delta: Decimal
    quantity_delta: Decimal
    before_quantity: Decimal
    after_quantity: Decimal
    before_cost_amount: Decimal
    after_cost_amount: Decimal
    before_cash_available: Decimal
    after_cash_available: Decimal
    affected_start_date: date | None = None
    affected_end_date: date | None = None


def _positive_parameter(parameters: Mapping[str, Decimal], name: str) -> Decimal:
    try:
        value = require_finite(Decimal(parameters[name]), name)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidCorporateActionParametersError(f"{name} must be provided and finite") from exc
    if value <= 0:
        raise InvalidCorporateActionParametersError(f"{name} must be strictly positive", {name: str(value)})
    return value


def _coerce_event_type(event_type: CorporateActionType) -> CorporateActionType:
    try:
        return CorporateActionType(event_type)
    except (TypeError, ValueError) as exc:
        raise UnknownCorporateActionTypeError(event_type) from exc


def _finite_input(value: Decimal, name: str) -> Decimal:
    try:
        return require_finite(Decimal(value), name)
    except (TypeError, ValueError) as exc:
        raise InvalidCorporateActionInputError(f"{name} must be finite", {"field": name}) from exc


def validate_corporate_action_parameters(
    event_type: CorporateActionType, parameters: Mapping[str, Decimal]
) -> None:
    action_type = _coerce_event_type(event_type)

    required = {
        CorporateActionType.DIVIDEND: ("per_share_amount",),
        CorporateActionType.SPLIT: ("ratio",),
        CorporateActionType.REVERSE_SPLIT: ("ratio",),
        CorporateActionType.BONUS_SHARE: ("bonus_ratio",),
        CorporateActionType.RIGHTS_ISSUE: ("subscription_ratio", "subscription_price"),
    }[action_type]
    values = {name: _positive_parameter(parameters, name) for name in required}
    if action_type is CorporateActionType.REVERSE_SPLIT and values["ratio"] >= 1:
        raise InvalidCorporateActionParametersError(
            "reverse split ratio must be below one", {"ratio": str(values["ratio"])}
        )


def calculate_corporate_action_impact(
    event_type: CorporateActionType,
    eligible_quantity: Decimal,
    cost_amount: Decimal,
    cash_available: Decimal,
    parameters: Mapping[str, Decimal],
) -> CorporateActionImpact:
    action_type = _coerce_event_type(event_type)
    validate_corporate_action_parameters(action_type, parameters)
    raw_quantity = _non_negative_input(eligible_quantity, "eligible quantity")
    raw_cost = _non_negative_input(cost_amount, "cost amount")
    raw_cash = _non_negative_input(cash_available, "cash available")
    before_quantity = quantize_shares(raw_quantity)
    before_cost = quantize_account_money(raw_cost)
    before_cash = quantize_account_money(raw_cash)

    cash_delta = Decimal("0")
    quantity_delta = Decimal("0")
    after_cost = before_cost
    if action_type is CorporateActionType.DIVIDEND:
        cash_delta = before_quantity * _positive_parameter(parameters, "per_share_amount")
    elif action_type in (CorporateActionType.SPLIT, CorporateActionType.REVERSE_SPLIT):
        ratio = _positive_parameter(parameters, "ratio")
        quantity_delta = before_quantity * (ratio - 1)
    elif action_type is CorporateActionType.BONUS_SHARE:
        quantity_delta = before_quantity * _positive_parameter(parameters, "bonus_ratio")
    else:
        subscription_ratio = _positive_parameter(parameters, "subscription_ratio")
        subscription_price = _positive_parameter(parameters, "subscription_price")
        quantity_delta = before_quantity * subscription_ratio
        cash_delta = -(quantity_delta * subscription_price)
        required_cash = quantize_account_money(-cash_delta)
        if before_cash < required_cash:
            raise InsufficientRightsCashError(before_cash, required_cash)

    return CorporateActionImpact(
        cash_delta=quantize_account_money(cash_delta),
        quantity_delta=quantize_shares(quantity_delta),
        before_quantity=before_quantity,
        after_quantity=quantize_shares(before_quantity + quantity_delta),
        before_cost_amount=before_cost,
        after_cost_amount=quantize_account_money(after_cost),
        before_cash_available=before_cash,
        after_cash_available=quantize_account_money(before_cash + cash_delta),
    )


def _non_negative_input(value: Decimal, name: str) -> Decimal:
    normalized = _finite_input(value, name)
    if normalized < 0:
        raise InvalidCorporateActionInputError(f"{name} must be non-negative", {"field": name})
    return normalized
