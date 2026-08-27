from decimal import Decimal

import pytest

from paper_trading.domain.corporate_actions import (
    CorporateActionInput,
    calculate_corporate_action_impact,
    validate_corporate_action_parameters,
)
from paper_trading.domain.enums import CorporateActionType
from paper_trading.domain.errors import (
    InsufficientRightsCashError,
    InvalidCorporateActionParametersError,
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
    with pytest.raises(InsufficientRightsCashError):
        calculate_corporate_action_impact(
            CorporateActionType.RIGHTS_ISSUE,
            Decimal("100"),
            Decimal("1000"),
            Decimal("1"),
            {"subscription_ratio": Decimal("0.2"), "subscription_price": Decimal("2.5")},
        )


def test_zero_quantity_produces_zero_impact():
    impact = calculate_corporate_action_impact(
        CorporateActionType.DIVIDEND, Decimal("0"), Decimal("1000"), Decimal("10"), {"per_share_amount": Decimal("1")}
    )
    assert impact.quantity_delta == Decimal("0.000000000000")
    assert impact.cash_delta == Decimal("0.000000000000")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_non_finite_values_are_rejected(value):
    with pytest.raises((ValueError, InvalidCorporateActionParametersError)):
        CorporateActionInput(CorporateActionType.SPLIT, {"ratio": value})


@pytest.mark.parametrize("action_type, parameters", [
    (CorporateActionType.DIVIDEND, {"per_share_amount": Decimal("0")}),
    (CorporateActionType.SPLIT, {"ratio": Decimal("-1")}),
    (CorporateActionType.BONUS_SHARE, {"bonus_ratio": Decimal("0")}),
    (CorporateActionType.RIGHTS_ISSUE, {"subscription_ratio": Decimal("0"), "subscription_price": Decimal("1")}),
])
def test_zero_or_negative_parameters_are_rejected(action_type, parameters):
    with pytest.raises(InvalidCorporateActionParametersError):
        validate_corporate_action_parameters(action_type, parameters)


def test_reverse_split_requires_factor_below_one():
    with pytest.raises(InvalidCorporateActionParametersError):
        validate_corporate_action_parameters(CorporateActionType.REVERSE_SPLIT, {"ratio": Decimal("1")})


def test_corporate_action_input_normalizes_and_is_immutable():
    action = CorporateActionInput(CorporateActionType.SPLIT, {"ratio": Decimal("2")})
    assert action.parameters["ratio"] == Decimal("2")
    with pytest.raises(TypeError):
        action.parameters["ratio"] = Decimal("3")  # type: ignore[index]
