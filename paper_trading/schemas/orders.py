from datetime import date, datetime
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
    comment: str | None = None
    market: str | None = None  # defaults to a_share via None


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
    comment: str | None = None
    validity_status: str | None = None
    validity_reason: str | None = None
    validity_checked_at: datetime | None = None
    market: str = "a_share"


class UpdateOrderCommentRequest(BaseModel):
    comment: str | None = None


class TradeValidityCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    account_id: int
    symbol: str
    trade_date: date
    side: str
    input_price: Decimal
    daily_low: Decimal | None = None
    daily_high: Decimal | None = None
    limit_up_price: Decimal | None = None
    limit_down_price: Decimal | None = None
    touched_limit_up: bool | None = None
    touched_limit_down: bool | None = None
    price_in_range: bool | None = None
    status: str
    reason_code: str
    reason_detail: str | None = None
    data_granularity: str
    created_at: datetime
    market: str = "a_share"


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
    comment: str | None = None
    market: str = "a_share"
