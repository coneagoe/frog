from datetime import date

from pydantic import BaseModel


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
