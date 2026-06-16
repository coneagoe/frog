from datetime import date

from pydantic import BaseModel, ConfigDict


class MatchingRunRequest(BaseModel):
    trade_date: date
    account_id: int | None = None


class MatchingRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trade_date: date
    account_id: int | None
    status: str
    processed_count: int
    filled_count: int
    skipped_count: int
    rejected_count: int
    failed_count: int
