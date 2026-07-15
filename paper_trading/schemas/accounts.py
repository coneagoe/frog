from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CreateAccountRequest(BaseModel):
    name: str
    initial_cash: Decimal
    fee_preset: str | None = "a_share"
    commission_rate: Decimal | None = Field(default=None, ge=0)
    min_commission: Decimal | None = Field(default=None, ge=0)
    stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    transfer_fee_rate: Decimal | None = Field(default=None, ge=0)


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
