from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_api_token
from paper_trading.schemas.analytics import AnalyticsResponse
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/accounts", tags=["paper-analytics"], dependencies=[Depends(require_api_token)])


@router.get("/{account_id}/analytics", response_model=AnalyticsResponse)
def get_account_analytics(account_id: int, session: Session = Depends(get_session)) -> AnalyticsResponse:
    repo = PaperTradingRepository(session)
    try:
        return AnalyticsService(repo).get_account_analytics(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
