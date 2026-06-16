from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from paper_trading.domain.enums import OrderSide


class CreateOrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    quantity: int
    limit_price: Decimal
    trade_date: date
    idempotency_key: str | None = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    side: str
    quantity: int
    limit_price: Decimal
    trade_date: date
    status: str
    filled_quantity: int
    frozen_cash: Decimal
    frozen_quantity: int
    rejection_code: str | None = None
    rejection_reason: str | None = None


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    account_id: int
    symbol: str
    side: str
    quantity: int
    price: Decimal
    amount: Decimal
    fees: Decimal
    trade_date: date
