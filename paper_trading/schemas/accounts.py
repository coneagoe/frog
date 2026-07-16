import re
from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CreateAccountRequest(BaseModel):
    name: str
    initial_cash: Decimal
    fee_preset: str | None = "a_share"
    commission_rate: Decimal | None = Field(default=None, ge=0)
    min_commission: Decimal | None = Field(default=None, ge=0)
    stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    transfer_fee_rate: Decimal | None = Field(default=None, ge=0)


class UpdateAccountFeeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commission_rate: Decimal | None = Field(default=None, ge=0)
    min_commission: Decimal | None = Field(default=None, ge=0)
    stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    transfer_fee_rate: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_fee_field(self) -> Self:
        if all(
            value is None
            for value in (
                self.commission_rate,
                self.min_commission,
                self.stamp_duty_rate,
                self.transfer_fee_rate,
            )
        ):
            raise ValueError("at least one fee field is required")
        return self


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    initial_cash: Decimal
    fee_preset: str
    commission_rate: Decimal
    min_commission: Decimal
    stamp_duty_rate: Decimal
    transfer_fee_rate: Decimal
    status: str
    base_currency: str


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    total_quantity: int
    frozen_quantity: int
    cost_amount: Decimal
    realized_pnl: Decimal


class CashLedgerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    event_type: str
    amount: Decimal
    note: str | None = None


class ImportPositionItem(BaseModel):
    symbol: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    cost_price: Decimal = Field(ge=0)
    buy_trade_date: date

    @model_validator(mode="before")
    @classmethod
    def strip_symbol(cls, values: dict) -> dict:
        if isinstance(values, dict) and "symbol" in values:
            values["symbol"] = values["symbol"].strip()
        return values

    @field_validator("buy_trade_date", mode="before")
    @classmethod
    def validate_buy_trade_date_format(cls, value: object) -> object:
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise ValueError("buy_trade_date must be a YYYY-MM-DD string")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("buy_trade_date must be in YYYY-MM-DD format")
        return value


class ImportPositionsRequest(BaseModel):
    positions: list[ImportPositionItem] = Field(min_length=1)


class ImportPositionsResponse(BaseModel):
    imported_count: int
    lots_count: int
