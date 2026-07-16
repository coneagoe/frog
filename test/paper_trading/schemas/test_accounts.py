from decimal import Decimal

import pytest
from pydantic import ValidationError

from paper_trading.schemas.accounts import UpdateAccountFeeRequest


def test_update_account_fee_request_accepts_partial_fee_update():
    request = UpdateAccountFeeRequest(commission_rate=Decimal("0.0002"))

    assert request.commission_rate == Decimal("0.0002")
    assert request.min_commission is None


def test_update_account_fee_request_rejects_empty_payload():
    with pytest.raises(ValidationError, match="at least one fee field"):
        UpdateAccountFeeRequest()


def test_update_account_fee_request_rejects_fee_preset():
    with pytest.raises(ValidationError):
        UpdateAccountFeeRequest(commission_rate=Decimal("0.0002"), fee_preset="a_share")
