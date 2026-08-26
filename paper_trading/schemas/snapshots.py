from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    trade_date: date
    point_type: Literal["initial", "trading"]
    event_at: datetime
    quality_status: Literal["valid", "invalid"]
    invalid_reason: str | None = None
    valuation_quality: Literal["current", "stale_suspended"] | None = None
    valuation_details: list[dict[str, Any]] | None = None
    cash_available: Decimal
    cash_frozen: Decimal
    market_value: Decimal
    total_assets: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    position_count: int
    order_count: int
    trade_count: int
    net_asset_value: Decimal | None = None
    share_count: Decimal | None = None
    cumulative_deposit: Decimal | None = None
    cumulative_withdrawal: Decimal | None = None
    net_cash_flow: Decimal | None = None
    pending_settlement: Decimal = Decimal("0.0000")

    @field_validator("event_at", mode="before")
    @classmethod
    def _aware_event_at(cls, value: datetime) -> datetime:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
