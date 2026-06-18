from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from paper_trading.api.deps import (
    get_market_data_provider,
    get_session,
    require_api_token,
)
from paper_trading.schemas.matching import MatchingRunRequest, MatchingRunResponse
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/matching/runs", dependencies=[Depends(require_api_token)])


@router.post("", response_model=MatchingRunResponse)
def run_matching(
    request: MatchingRunRequest,
    session: Session = Depends(get_session),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
):
    repo = PaperTradingRepository(session)
    run = MatchingService(repo, market_data, SnapshotService(repo, market_data)).run(
        request.trade_date, request.account_id
    )
    session.commit()
    return run


@router.get("", response_model=list[MatchingRunResponse])
def list_runs(session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_matching_runs()


@router.get("/{run_id}", response_model=MatchingRunResponse)
def get_run(run_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).get_matching_run(run_id)
