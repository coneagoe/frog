from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_market_data_provider, get_session_factory, require_api_token
from paper_trading.schemas.snapshot_recalculation import (
    SnapshotRecalculationRequest,
    SnapshotRecalculationResponse,
)
from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationService
from paper_trading.storage.market_data import MarketDataProvider

router = APIRouter(
    prefix="/paper/accounts/{account_id}/snapshots",
    dependencies=[Depends(require_api_token)],
)


@router.post("/recalculate", response_model=SnapshotRecalculationResponse)
def recalculate_snapshots(
    account_id: int,
    request: SnapshotRecalculationRequest,
    session_factory: Callable[[], Session] = Depends(get_session_factory),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
) -> SnapshotRecalculationResponse:
    try:
        result = SnapshotRecalculationService(session_factory, market_data).recalculate(
            account_id, request.start_date, request.end_date
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SnapshotRecalculationResponse(
        account_id=result.account_id,
        updated_dates=result.updated_dates,
        unavailable_dates=result.unavailable_dates,
        failed_dates=result.failed_dates,
        errors=result.errors,
    )
