from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CreateAccountRequest(BaseModel):
    name: str
    initial_cash: Decimal


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    initial_cash: Decimal
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
