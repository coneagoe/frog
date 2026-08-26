from datetime import date

from pydantic import BaseModel, model_validator


class SnapshotRecalculationRequest(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "SnapshotRecalculationRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class SnapshotRecalculationResponse(BaseModel):
    account_id: int
    updated_dates: list[date]
    unavailable_dates: list[date]
    failed_dates: list[date]
    errors: list[str]
