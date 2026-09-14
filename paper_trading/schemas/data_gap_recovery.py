from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataGapRecoveryGapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    business_date: date
    market: str
    stock_id: str
    adjust: str
    status: str
    summary: dict[str, Any]
    first_observed_at: datetime
    last_observed_at: datetime
    resolved_at: datetime | None = None
    latest_candidate_hash: str | None = None
    candidates: list[Any] = Field(default_factory=list)
    attempts: list[Any] = Field(default_factory=list)
    approvals: list[Any] = Field(default_factory=list)
    accounts: list[Any] = Field(default_factory=list)
    alerts: list[Any] = Field(default_factory=list)


class DataGapRecoveryPage(BaseModel):
    items: list[DataGapRecoveryGapResponse]
    offset: int
    page_size: int
    total_count: int


class DataGapRecoveryBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    summary: dict[str, Any]
    download_id: str | None = None
    cutoff: datetime | None = None
    finished_at: datetime | None = None
    gap_count: int
    recovered_count: int
    failed_count: int
    created_at: datetime
    attempts: list[Any] = Field(default_factory=list)
    gaps: list[Any] = Field(default_factory=list)
    alerts: list[Any] = Field(default_factory=list)


class DataGapRecoveryBatchPage(BaseModel):
    items: list[DataGapRecoveryBatchResponse]
    offset: int
    page_size: int
    total_count: int
