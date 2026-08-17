import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from paper_trading.api.deps import (
    get_market_data_provider,
    get_session,
    require_api_token,
)
from paper_trading.schemas.matching import LedgerRebuildResponse, MatchingRunRequest, MatchingRunResponse
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/matching/runs", dependencies=[Depends(require_api_token)])
logger = logging.getLogger(__name__)


@router.post("", response_model=MatchingRunResponse)
def run_matching(
    request: MatchingRunRequest,
    session: Session = Depends(get_session),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
):
    repo = PaperTradingRepository(session)
    try:
        run = MatchingService(repo, market_data, SnapshotService(repo, market_data)).run(
            request.trade_date, request.account_id
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception(
            "Matching persistence failed: trade_date=%s account_id=%s",
            request.trade_date,
            request.account_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "MATCHING_PERSISTENCE_FAILED",
                "message": "Matching persistence failed",
                "details": {},
            },
        ) from None
    return run


@router.get("", response_model=list[MatchingRunResponse])
def list_runs(session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_matching_runs()


@router.post("/rebuilds", response_model=LedgerRebuildResponse)
def rebuild_delayed_daily_bar_orders(
    session: Session = Depends(get_session),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
):
    repo = PaperTradingRepository(session)
    eligible = []
    for order in repo.list_eligible_daily_bar_rebuild_orders():
        try:
            market_data.get_daily_bar(order.symbol, order.trade_date, market=order.market)
        except KeyError:
            continue
        eligible.append(order)
    by_account: dict[int, list] = {}
    for order in eligible:
        by_account.setdefault(order.account_id, []).append(order)
    try:
        service = OrderDeleteService(repo, market_data)
        for account_id, orders in by_account.items():
            service.rebuild_account_from(account_id, orders[0].trade_date, [order.id for order in orders])
        session.commit()
    except Exception:
        session.commit()
        logger.exception("Historical ledger rebuild failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Historical ledger rebuild failed",
        ) from None
    return LedgerRebuildResponse(rebuilt_account_ids=sorted(by_account))


@router.get("/{run_id}", response_model=MatchingRunResponse)
def get_run(run_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).get_matching_run(run_id)
