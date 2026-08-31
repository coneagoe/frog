from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    trade_date: date
    point_type: Literal["initial", "trading"]
    event_at: datetime
    timezone: Literal["UTC"] = "UTC"
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
        return value.astimezone(timezone.utc) if isinstance(value, datetime) else value

    @field_serializer(
        "cash_available",
        "cash_frozen",
        "market_value",
        "total_assets",
        "realized_pnl",
        "unrealized_pnl",
        "cumulative_deposit",
        "cumulative_withdrawal",
        "net_cash_flow",
        "pending_settlement",
    )
    def serialize_money(self, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.0001")) if value is not None else None

    @field_serializer("net_asset_value", "share_count")
    def serialize_nav_values(self, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.000000")) if value is not None else None
