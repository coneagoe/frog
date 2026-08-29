import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from paper_trading.domain.enums import Market, MigrationRepairReason


class CreateAccountRequest(BaseModel):
    name: str
    initial_cash: Decimal = Field(gt=0)
    fee_preset: str | None = "a_share"
    commission_rate: Decimal | None = Field(default=None, ge=0)
    min_commission: Decimal | None = Field(default=None, ge=0)
    stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    transfer_fee_rate: Decimal | None = Field(default=None, ge=0)
    etf_commission_rate: Decimal | None = Field(default=None, ge=0)


class UpdateAccountFeeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commission_rate: Decimal | None = Field(default=None, ge=0)
    min_commission: Decimal | None = Field(default=None, ge=0)
    stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    transfer_fee_rate: Decimal | None = Field(default=None, ge=0)
    hk_commission_rate: Decimal | None = Field(default=None, ge=0)
    hk_min_commission: Decimal | None = Field(default=None, ge=0)
    hk_stamp_duty_rate: Decimal | None = Field(default=None, ge=0)
    hk_trading_fee_rate: Decimal | None = Field(default=None, ge=0)
    hk_sfc_levy_rate: Decimal | None = Field(default=None, ge=0)
    hk_afrc_levy_rate: Decimal | None = Field(default=None, ge=0)
    hk_settlement_fee_rate: Decimal | None = Field(default=None, ge=0)
    etf_commission_rate: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_fee_field(self) -> Self:
        if all(
            value is None
            for value in (
                self.commission_rate,
                self.min_commission,
                self.stamp_duty_rate,
                self.transfer_fee_rate,
                self.hk_commission_rate,
                self.hk_min_commission,
                self.hk_stamp_duty_rate,
                self.hk_trading_fee_rate,
                self.hk_sfc_levy_rate,
                self.hk_afrc_levy_rate,
                self.hk_settlement_fee_rate,
                self.etf_commission_rate,
            )
        ):
            raise ValueError("at least one fee field is required")
        return self


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    initial_cash: Decimal
    cash_available: Decimal
    fee_preset: str
    commission_rate: Decimal
    min_commission: Decimal
    stamp_duty_rate: Decimal
    transfer_fee_rate: Decimal
    hk_commission_rate: Decimal | None = None
    hk_min_commission: Decimal | None = None
    hk_stamp_duty_rate: Decimal | None = None
    hk_trading_fee_rate: Decimal | None = None
    hk_sfc_levy_rate: Decimal | None = None
    hk_afrc_levy_rate: Decimal | None = None
    hk_settlement_fee_rate: Decimal | None = None
    etf_commission_rate: Decimal | None = None
    status: str
    base_currency: str
    share_count: Decimal
    net_asset_value: Decimal
    cumulative_deposit: Decimal
    cumulative_withdrawal: Decimal
    migration_repair_reason: MigrationRepairReason | None = None

    @field_serializer("initial_cash", "cash_available", "cumulative_deposit", "cumulative_withdrawal")
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))

    @field_serializer("share_count", "net_asset_value")
    def serialize_nav_values(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.000000"))


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    total_quantity: int
    frozen_quantity: int
    cost_amount: Decimal
    realized_pnl: Decimal
    market: str = "a_share"
    stock_name: str | None = None
    mark_price: Decimal | None = None
    price_source: Literal["real_time", "db_close"] | None = None
    unrealized_pnl: Decimal | None = None


class CashLedgerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    event_type: str
    amount: Decimal
    occurred_at: datetime
    trade_date: date | None = None
    net_asset_value: Decimal | None = None
    share_delta: Decimal | None = None
    rounding_residual: Decimal = Decimal("0")
    note: str | None = None

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))

    @field_serializer("net_asset_value", "share_delta")
    def serialize_nav_values(self, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.000000")) if value is not None else None


class ImportPositionItem(BaseModel):
    symbol: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    cost_price: Decimal = Field(ge=0)
    buy_trade_date: date
    market: Market = Market.A_SHARE

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


class CashFlowRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    trade_date: date
    occurred_at: datetime | None = None
    note: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone_offset(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone offset")
        return value


class CashFlowResponse(BaseModel):
    account_id: int
    cash_available: Decimal
    net_asset_value: Decimal
    share_count: Decimal
    ledger: CashLedgerResponse

    @field_serializer("cash_available")
    def serialize_cash_available(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))

    @field_serializer("net_asset_value", "share_count")
    def serialize_nav_values(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.000000"))


class LedgerRebuildRequest(BaseModel):
    start_date: date
    trigger_evidence: dict | None = None


class LedgerRebuildAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    start_date: date
    triggering_order_ids: list[int]
    trigger_evidence: dict
    status: str
    deleted_counts: dict[str, int]
    regenerated_counts: dict[str, int]
    error_details: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
