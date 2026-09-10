from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from monitor.domain_enums import MonitorEvaluationErrorKind, MonitorFrequency, MonitorMarket, MonitorResetMode
from monitor.monitor_health_service import MonitorOperationalState


class MonitorTargetResponse(BaseModel):
    id: int
    stock_code: str
    market: MonitorMarket
    condition: dict[str, Any]
    note: str | None
    frequency: MonitorFrequency
    reset_mode: MonitorResetMode
    enabled: bool
    last_state: bool
    triggered_at: datetime | None
    created_at: datetime | None
    stock_name: str | None = None


class MonitorTargetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MonitorTargetResponse]
    page: int
    page_size: int
    total_count: int
    total_pages: int


class MonitorTargetHealthErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MonitorEvaluationErrorKind
    summary: str
    detail: str | None
    occurred_at: datetime


class MonitorTargetHealthSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    running: int
    paused: int
    disabled: int
    triggered: int
    daily: int
    intraday: int


class MonitorTargetHealthItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    stock_code: str
    market: MonitorMarket
    frequency: MonitorFrequency
    workflow: str | None
    enabled: bool
    paused: bool
    operational_state: MonitorOperationalState
    last_state: bool
    last_checked_at: datetime | None
    triggered_at: datetime | None
    latest_error: MonitorTargetHealthErrorResponse | None
    stock_name: str | None = None


class MonitorTargetHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: MonitorTargetHealthSummaryResponse
    items: list[MonitorTargetHealthItemResponse]
    page: int
    page_size: int
    total_count: int
    total_pages: int


class CreateMonitorTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    market: MonitorMarket
    condition: dict[str, Any]
    note: str | None = None
    frequency: MonitorFrequency = MonitorFrequency.DAILY
    reset_mode: MonitorResetMode = MonitorResetMode.AUTO
    enabled: bool = True


class UpdateMonitorTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str | None = None
    market: MonitorMarket | None = None
    condition: dict[str, Any] | None = None
    note: str | None = None
    frequency: MonitorFrequency | None = None
    reset_mode: MonitorResetMode | None = None
    enabled: bool | None = None


class SetMonitorTargetEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
