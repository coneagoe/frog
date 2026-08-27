from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from paper_trading.domain.enums import CorporateActionProcessingStatus, CorporateActionType, Market
from paper_trading.schemas.snapshot_recalculation import SnapshotRecalculationResponse


class CorporateActionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=20)
    market: Market = Market.A_SHARE
    event_type: CorporateActionType
    event_at: datetime
    idempotency_key: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Decimal]

    @field_validator("symbol", "idempotency_key")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("event_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_at must include a timezone offset")
        return value

    @field_validator("parameters")
    @classmethod
    def require_finite_parameters(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        for name, parameter in value.items():
            try:
                if not parameter.is_finite():
                    raise ValueError(f"parameters.{name} must be finite")
            except AttributeError as exc:
                raise ValueError(f"parameters.{name} must be finite") from exc
        return value

    @model_validator(mode="after")
    def validate_parameters(self) -> "CorporateActionCreateRequest":
        required = {
            CorporateActionType.DIVIDEND: {"per_share_amount"},
            CorporateActionType.SPLIT: {"ratio"},
            CorporateActionType.REVERSE_SPLIT: {"ratio"},
            CorporateActionType.BONUS_SHARE: {"bonus_ratio"},
            CorporateActionType.RIGHTS_ISSUE: {"subscription_ratio", "subscription_price"},
        }[self.event_type]
        if set(self.parameters) != required:
            raise ValueError(f"parameters must contain exactly: {', '.join(sorted(required))}")
        for name, value in self.parameters.items():
            try:
                if not value.is_finite() or value <= 0:
                    raise ValueError(f"parameters.{name} must be strictly positive and finite")
            except (InvalidOperation, AttributeError) as exc:
                raise ValueError(f"parameters.{name} must be strictly positive and finite") from exc
        if self.event_type is CorporateActionType.REVERSE_SPLIT and self.parameters["ratio"] >= 1:
            raise ValueError("reverse split ratio must be below one")
        return self


class CorporateActionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    market: Market
    symbol: str
    event_type: CorporateActionType
    event_at: datetime
    idempotency_key: str
    parameters: dict[str, Any]
    processing_status: CorporateActionProcessingStatus
    processed_at: datetime | None
    processing_metadata: dict[str, Any] | None
    error_details: str | None
    cash_delta: Decimal
    quantity_delta: Decimal
    before_quantity: Decimal
    after_quantity: Decimal
    before_cost_amount: Decimal
    after_cost_amount: Decimal
    before_cash_available: Decimal
    after_cash_available: Decimal
    affected_start_date: date | None
    affected_end_date: date | None
    created_at: datetime

    @field_serializer(
        "cash_delta",
        "before_cost_amount",
        "after_cost_amount",
        "before_cash_available",
        "after_cash_available",
    )
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))

    @field_serializer("quantity_delta", "before_quantity", "after_quantity")
    def serialize_quantity(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.000001"))


class CorporateActionImpactResponse(BaseModel):
    cash_delta: Decimal
    quantity_delta: Decimal
    before_quantity: Decimal
    after_quantity: Decimal
    before_cost_amount: Decimal
    after_cost_amount: Decimal
    before_cash_available: Decimal
    after_cash_available: Decimal
    affected_start_date: date | None
    affected_end_date: date | None

    @field_serializer(
        "cash_delta",
        "before_cost_amount",
        "after_cost_amount",
        "before_cash_available",
        "after_cash_available",
    )
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))

    @field_serializer("quantity_delta", "before_quantity", "after_quantity")
    def serialize_quantity(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.000001"))


class CorporateActionCreateResponse(BaseModel):
    event: CorporateActionEventResponse
    impact: CorporateActionImpactResponse
    recalculation: SnapshotRecalculationResponse
