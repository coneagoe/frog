from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paper_trading.domain.enums import Market, MigrationRepairReason
from paper_trading.schemas.accounts import (
    AccountResponse,
    CreateAccountRequest,
    ImportPositionItem,
    ImportPositionsRequest,
    UpdateAccountFeeRequest,
)


def _account_response_payload(**overrides):
    payload = {
        "id": 1,
        "name": "demo",
        "initial_cash": Decimal("100000"),
        "cash_available": Decimal("100000"),
        "fee_preset": "a_share",
        "commission_rate": Decimal("0.0003"),
        "min_commission": Decimal("5"),
        "stamp_duty_rate": Decimal("0.0005"),
        "transfer_fee_rate": Decimal("0.00001"),
        "status": "active",
        "base_currency": "CNY",
        "share_count": Decimal("100000"),
        "net_asset_value": Decimal("1"),
        "cumulative_deposit": Decimal("0"),
        "cumulative_withdrawal": Decimal("0"),
    }
    payload.update(overrides)
    return payload


def test_account_response_serializes_nullable_migration_repair_reason():
    response = AccountResponse.model_validate(_account_response_payload())

    assert response.migration_repair_reason is None
    assert response.model_dump()["migration_repair_reason"] is None

    repaired = AccountResponse.model_validate(
        _account_response_payload(migration_repair_reason=MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN)
    )

    assert repaired.migration_repair_reason == MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN
    assert repaired.model_dump()["migration_repair_reason"] == "legacy_ordering_uncertain"


# ---------------------------------------------------------------------------
# UpdateAccountFeeRequest
# ---------------------------------------------------------------------------


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


def test_update_account_fee_request_accepts_etf_only_update():
    request = UpdateAccountFeeRequest(etf_commission_rate=Decimal("0"))

    assert request.etf_commission_rate == Decimal("0")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CreateAccountRequest(name="etf", initial_cash=Decimal("100000"), etf_commission_rate=Decimal("-0.1")),
        lambda: UpdateAccountFeeRequest(etf_commission_rate=Decimal("-0.1")),
    ],
)
def test_account_fee_requests_reject_negative_etf_rate(factory):
    with pytest.raises(ValidationError):
        factory()


# ---------------------------------------------------------------------------
# ImportPositionItem
# ---------------------------------------------------------------------------


class TestImportPositionItem:
    def test_import_item_defaults_market_to_a_share(self):
        item = ImportPositionItem(symbol="000001", quantity=100, cost_price="10.00", buy_trade_date="2026-07-27")

        assert item.market is Market.A_SHARE

    def test_valid_item(self):
        item = ImportPositionItem(
            symbol="000001",
            quantity=100,
            cost_price=Decimal("10.50"),
            buy_trade_date=date(2026, 1, 15),
        )
        assert item.symbol == "000001"
        assert item.quantity == 100
        assert item.cost_price == Decimal("10.50")
        assert item.buy_trade_date == date(2026, 1, 15)

    def test_symbol_whitespace_stripped(self):
        item = ImportPositionItem(
            symbol="  000001  ",
            quantity=100,
            cost_price=Decimal("10.00"),
            buy_trade_date=date(2026, 1, 15),
        )
        assert item.symbol == "000001"

    def test_rejects_zero_quantity(self):
        with pytest.raises(ValidationError):
            ImportPositionItem(
                symbol="000001",
                quantity=0,
                cost_price=Decimal("10.00"),
                buy_trade_date=date(2026, 1, 15),
            )

    def test_rejects_negative_quantity(self):
        with pytest.raises(ValidationError):
            ImportPositionItem(
                symbol="000001",
                quantity=-1,
                cost_price=Decimal("10.00"),
                buy_trade_date=date(2026, 1, 15),
            )

    def test_rejects_negative_cost_price(self):
        with pytest.raises(ValidationError):
            ImportPositionItem(
                symbol="000001",
                quantity=100,
                cost_price=Decimal("-1"),
                buy_trade_date=date(2026, 1, 15),
            )

    def test_accepts_zero_cost_price(self):
        item = ImportPositionItem(
            symbol="000001",
            quantity=100,
            cost_price=Decimal("0"),
            buy_trade_date=date(2026, 1, 15),
        )
        assert item.cost_price == Decimal("0")

    def test_rejects_missing_symbol(self):
        with pytest.raises(ValidationError):
            ImportPositionItem(
                symbol="",
                quantity=100,
                cost_price=Decimal("10.00"),
                buy_trade_date=date(2026, 1, 15),
            )

    def test_accepts_string_trade_date(self):
        """buy_trade_date should accept YYYY-MM-DD strings."""
        item = ImportPositionItem(
            symbol="000001",
            quantity=100,
            cost_price=Decimal("10.00"),
            buy_trade_date="2026-01-15",
        )
        assert item.buy_trade_date == date(2026, 1, 15)


class TestImportPositionsRequest:
    def test_valid_request(self):
        req = ImportPositionsRequest(
            positions=[
                ImportPositionItem(
                    symbol="000001",
                    quantity=100,
                    cost_price=Decimal("10.00"),
                    buy_trade_date=date(2026, 1, 15),
                ),
                ImportPositionItem(
                    symbol="000002",
                    quantity=200,
                    cost_price=Decimal("20.00"),
                    buy_trade_date=date(2026, 2, 1),
                ),
            ]
        )
        assert len(req.positions) == 2

    def test_rejects_empty_positions(self):
        with pytest.raises(ValidationError):
            ImportPositionsRequest(positions=[])
