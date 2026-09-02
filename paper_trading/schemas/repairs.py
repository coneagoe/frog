from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class HistoricalEtfMarketRepairRequest(BaseModel):
    apply: bool = False


class RepairCandidateResponse(BaseModel):
    account_id: int
    order_id: int
    symbol: str
    trade_date: date


class RepairedAccountResponse(BaseModel):
    account_id: int
    order_ids: list[int]
    replay_start_date: date


class FailedAccountResponse(BaseModel):
    account_id: int
    error: str


class HistoricalEtfMarketRepairResponse(BaseModel):
    dry_run: bool
    candidates: list[RepairCandidateResponse]
    corrected_orders: list[RepairCandidateResponse]
    repaired_accounts: list[RepairedAccountResponse]
    skipped_accounts: list[int]
    failed_accounts: list[FailedAccountResponse]


class TradingSnapshotTimestampRepairRequest(BaseModel):
    account_id: int
    start_date: date
    end_date: date | None = None
    apply: bool = False

    @model_validator(mode="after")
    def validate_date_range(self) -> "TradingSnapshotTimestampRepairRequest":
        if self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self

    @property
    def effective_end_date(self) -> date:
        return self.end_date or self.start_date


class TradingSnapshotTimestampRepairCandidate(BaseModel):
    snapshot_id: int
    trade_date: date
    event_at: datetime
    canonical_event_at: datetime


class TradingSnapshotTimestampRepairResult(BaseModel):
    account_id: int
    start_date: date
    end_date: date
    dry_run: bool = Field(default=True)
    matched_count: int
    updated_count: int
    candidates: list[TradingSnapshotTimestampRepairCandidate]


class TradingSnapshotTimestampRepairResponse(TradingSnapshotTimestampRepairResult):
    pass
