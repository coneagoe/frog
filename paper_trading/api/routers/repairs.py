from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_market_data_provider, get_session_factory, require_api_token
from paper_trading.schemas.repairs import (
    FailedAccountResponse,
    HistoricalEtfMarketRepairRequest,
    HistoricalEtfMarketRepairResponse,
    RepairCandidateResponse,
    RepairedAccountResponse,
    TradingSnapshotTimestampRepairRequest,
    TradingSnapshotTimestampRepairResponse,
)
from paper_trading.services.historical_etf_market_repair_service import HistoricalEtfMarketRepairService
from paper_trading.services.trading_snapshot_timestamp_repair_service import TradingSnapshotTimestampRepairService
from paper_trading.storage.market_data import MarketDataProvider

router = APIRouter(prefix="/paper/repairs", dependencies=[Depends(require_api_token)])


@router.post("/etf-markets", response_model=HistoricalEtfMarketRepairResponse)
def repair_historical_etf_markets(
    request: HistoricalEtfMarketRepairRequest = HistoricalEtfMarketRepairRequest(),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
) -> HistoricalEtfMarketRepairResponse:
    result = HistoricalEtfMarketRepairService(session_factory, market_data).run(request.apply)
    return HistoricalEtfMarketRepairResponse(
        dry_run=result.dry_run,
        candidates=[RepairCandidateResponse.model_validate(item, from_attributes=True) for item in result.candidates],
        corrected_orders=[
            RepairCandidateResponse.model_validate(item, from_attributes=True) for item in result.corrected_orders
        ],
        repaired_accounts=[
            RepairedAccountResponse.model_validate(item, from_attributes=True) for item in result.repaired_accounts
        ],
        skipped_accounts=result.skipped_accounts,
        failed_accounts=[
            FailedAccountResponse.model_validate(item, from_attributes=True) for item in result.failed_accounts
        ],
    )


@router.post("/trading-snapshot-event-at", response_model=TradingSnapshotTimestampRepairResponse)
def repair_trading_snapshot_event_at(
    request: TradingSnapshotTimestampRepairRequest,
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> TradingSnapshotTimestampRepairResponse:
    try:
        result = TradingSnapshotTimestampRepairService(session_factory).run(
            request.account_id, request.start_date, request.end_date, request.apply
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TradingSnapshotTimestampRepairResponse(**result.model_dump())
