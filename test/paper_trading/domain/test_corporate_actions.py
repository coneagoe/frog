from dataclasses import FrozenInstanceError
from decimal import ROUND_HALF_UP, Decimal

import pytest

from paper_trading.domain.corporate_actions import (
    CorporateActionInput,
    calculate_corporate_action_impact,
    validate_corporate_action_parameters,
)
from paper_trading.domain.enums import CorporateActionType
from paper_trading.domain.errors import (
    InsufficientRightsCashError,
    InvalidCorporateActionInputError,
    InvalidCorporateActionParametersError,
    UnknownCorporateActionTypeError,
)


def test_split_preserves_total_cost_basis():
    impact = calculate_corporate_action_impact(
        CorporateActionType.SPLIT, Decimal("100"), Decimal("1000.00"), Decimal("0"), {"ratio": Decimal("2")}
    )
    assert impact.after_quantity == Decimal("200.000000000000")
    assert impact.after_cost_amount == Decimal("1000.000000000000")
    assert impact.cash_delta == Decimal("0.000000000000")


def test_dividend_adds_cash():
    impact = calculate_corporate_action_impact(
        CorporateActionType.DIVIDEND,
        Decimal("100"),
        Decimal("1000"),
        Decimal("20"),
        {"per_share_amount": Decimal("0.25")},
    )
    assert impact.cash_delta == Decimal("25.000000000000")
    assert impact.after_cash_available == Decimal("45.000000000000")


def test_reverse_split_reduces_quantity():
    impact = calculate_corporate_action_impact(
        CorporateActionType.REVERSE_SPLIT,
        Decimal("100"),
        Decimal("1000"),
        Decimal("0"),
        {"ratio": Decimal("0.5")},
    )
    assert impact.after_quantity == Decimal("50.000000000000")


def test_bonus_shares_preserve_cost_basis():
    impact = calculate_corporate_action_impact(
        CorporateActionType.BONUS_SHARE,
        Decimal("100"),
        Decimal("1000"),
        Decimal("0"),
        {"bonus_ratio": Decimal("0.1")},
    )
    assert impact.quantity_delta == Decimal("10.000000000000")
    assert impact.after_cost_amount == Decimal("1000.000000000000")


def test_rights_issue_subscribes_fully():
    impact = calculate_corporate_action_impact(
        CorporateActionType.RIGHTS_ISSUE,
        Decimal("100"),
        Decimal("1000"),
        Decimal("100"),
        {"subscription_ratio": Decimal("0.2"), "subscription_price": Decimal("2.5")},
    )
    assert impact.quantity_delta == Decimal("20.000000000000")
    assert impact.cash_delta == Decimal("-50.000000000000")
    assert impact.after_cash_available == Decimal("50.000000000000")


def test_rights_issue_rejects_insufficient_cash():
    with pytest.raises(InsufficientRightsCashError) as exc_info:
        calculate_corporate_action_impact(
            CorporateActionType.RIGHTS_ISSUE,
            Decimal("100"),
            Decimal("1000"),
            Decimal("1"),
            {"subscription_ratio": Decimal("0.2"), "subscription_price": Decimal("2.5")},
        )
    assert exc_info.value.details == {"available": "1.000000000000", "required": "50.000000000000"}


def test_zero_quantity_produces_zero_impact():
    impact = calculate_corporate_action_impact(
        CorporateActionType.DIVIDEND, Decimal("0"), Decimal("1000"), Decimal("10"), {"per_share_amount": Decimal("1")}
    )
    assert impact.quantity_delta == Decimal("0.000000000000")
    assert impact.cash_delta == Decimal("0.000000000000")


def test_zero_quantity_rights_issue_does_not_require_cash():
    impact = calculate_corporate_action_impact(
        CorporateActionType.RIGHTS_ISSUE,
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        {"subscription_ratio": Decimal("0.2"), "subscription_price": Decimal("2.5")},
    )
    assert impact.quantity_delta == Decimal("0.000000000000")
    assert impact.cash_delta == Decimal("0.000000000000")


@pytest.mark.parametrize("field", ["eligible_quantity", "cost_amount", "cash_available"])
def test_sub_quantum_negative_inputs_are_rejected_before_quantization(field):
    values = {"eligible_quantity": Decimal("0"), "cost_amount": Decimal("0"), "cash_available": Decimal("0")}
    values[field] = Decimal("-0.0000000000001")
    with pytest.raises(InvalidCorporateActionInputError):
        calculate_corporate_action_impact(
            CorporateActionType.DIVIDEND,
            values["eligible_quantity"],
            values["cost_amount"],
            values["cash_available"],
            {"per_share_amount": Decimal("1")},
        )


@pytest.mark.parametrize("value", [Decimal("0.0000000000005"), Decimal("1.2345678901235")])
def test_quantization_uses_half_up_boundaries(value):
    impact = calculate_corporate_action_impact(
        CorporateActionType.DIVIDEND, value, Decimal("0"), Decimal("0"), {"per_share_amount": Decimal("1")}
    )
    assert impact.before_quantity == value.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)


def test_calculation_rejects_invalid_inputs_and_unknown_event_types():
    with pytest.raises(InvalidCorporateActionInputError):
        calculate_corporate_action_impact(
            CorporateActionType.DIVIDEND, Decimal("NaN"), Decimal("0"), Decimal("0"), {"per_share_amount": Decimal("1")}
        )
    with pytest.raises(UnknownCorporateActionTypeError):
        calculate_corporate_action_impact("bogus", Decimal("0"), Decimal("0"), Decimal("0"), {})  # type: ignore[arg-type]


def test_malformed_numeric_input_raises_typed_error():
    with pytest.raises(InvalidCorporateActionInputError) as exc_info:
        calculate_corporate_action_impact(
            CorporateActionType.DIVIDEND,
            "not-a-number",  # type: ignore[arg-type]
            Decimal("0"),
            Decimal("0"),
            {"per_share_amount": Decimal("1")},
        )

    assert exc_info.value.code == "INVALID_CORPORATE_ACTION_INPUT"


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_non_finite_values_are_rejected(value):
    with pytest.raises(InvalidCorporateActionInputError):
        CorporateActionInput(CorporateActionType.SPLIT, {"ratio": value})


@pytest.mark.parametrize(
    "action_type, parameters",
    [
        (CorporateActionType.DIVIDEND, {"per_share_amount": Decimal("0")}),
        (CorporateActionType.SPLIT, {"ratio": Decimal("-1")}),
        (CorporateActionType.BONUS_SHARE, {"bonus_ratio": Decimal("0")}),
        (CorporateActionType.RIGHTS_ISSUE, {"subscription_ratio": Decimal("0"), "subscription_price": Decimal("1")}),
    ],
)
def test_zero_or_negative_parameters_are_rejected(action_type, parameters):
    with pytest.raises(InvalidCorporateActionParametersError):
        validate_corporate_action_parameters(action_type, parameters)


def test_reverse_split_requires_factor_below_one():
    with pytest.raises(InvalidCorporateActionParametersError):
        validate_corporate_action_parameters(CorporateActionType.REVERSE_SPLIT, {"ratio": Decimal("1")})


@pytest.mark.parametrize(
    ("action_type", "parameters"),
    [
        (CorporateActionType.DIVIDEND, {"per_share_amount": Decimal("1"), "ratio": Decimal("2")}),
        (
            CorporateActionType.RIGHTS_ISSUE,
            {"subscription_ratio": Decimal("1"), "subscription_price": Decimal("2"), "extra": Decimal("1")},
        ),
    ],
)
def test_extra_parameters_are_rejected(action_type, parameters):
    with pytest.raises(InvalidCorporateActionParametersError, match="unexpected"):
        validate_corporate_action_parameters(action_type, parameters)


@pytest.mark.parametrize("ratio", [Decimal("0"), Decimal("-0.5"), Decimal("1")])
def test_reverse_split_rejects_zero_negative_or_non_reducing_ratios(ratio):
    with pytest.raises(InvalidCorporateActionParametersError):
        validate_corporate_action_parameters(CorporateActionType.REVERSE_SPLIT, {"ratio": ratio})


def test_corporate_action_input_normalizes_and_is_immutable():
    action = CorporateActionInput(CorporateActionType.SPLIT, {"ratio": Decimal("2")})
    assert action.parameters["ratio"] == Decimal("2")
    with pytest.raises(TypeError):
        action.parameters["ratio"] = Decimal("3")  # type: ignore[index]


def test_impact_contains_all_fields_and_is_immutable():
    impact = calculate_corporate_action_impact(
        CorporateActionType.DIVIDEND, Decimal("2"), Decimal("10"), Decimal("3"), {"per_share_amount": Decimal("1")}
    )
    assert {
        "cash_delta",
        "quantity_delta",
        "before_quantity",
        "after_quantity",
        "before_cost_amount",
        "after_cost_amount",
        "before_cash_available",
        "after_cash_available",
        "affected_start_date",
        "affected_end_date",
    } == set(impact.__dataclass_fields__)
    assert impact.affected_start_date is None
    assert impact.affected_end_date is None
    with pytest.raises(FrozenInstanceError):
        setattr(impact, "cash_delta", Decimal("0"))
