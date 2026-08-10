from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ETFEligibilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    exchange: str
    list_status: str
    last_seen_at: datetime
    last_refresh_at: datetime
    status: str
    reviewed_at: datetime | None
    reviewed_by: str | None


class ETFEligibilityListResponse(BaseModel):
    items: list[ETFEligibilityResponse]


class ClassifyETFEligibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reviewed_by: str
