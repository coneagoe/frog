from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from monitor.domain_enums import MonitorFrequency, MonitorMarket, MonitorResetMode


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
