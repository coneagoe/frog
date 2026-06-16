from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    trade_date: date
    cash_available: Decimal
    cash_frozen: Decimal
    market_value: Decimal
    total_assets: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    position_count: int
    order_count: int
    trade_count: int
