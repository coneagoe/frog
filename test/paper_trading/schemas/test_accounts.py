from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from paper_trading.schemas.accounts import ImportPositionItem, ImportPositionsRequest, UpdateAccountFeeRequest

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


# ---------------------------------------------------------------------------
# ImportPositionItem
# ---------------------------------------------------------------------------


class TestImportPositionItem:
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
