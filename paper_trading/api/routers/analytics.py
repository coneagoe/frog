from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_api_token
from paper_trading.schemas.analytics import AnalyticsResponse, AnalyticsUnavailableResponse, ValuationGapResponse
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/accounts", tags=["paper-analytics"], dependencies=[Depends(require_api_token)])

AnalyticsPayload = Annotated[
    AnalyticsResponse | AnalyticsUnavailableResponse,
    Field(discriminator="available"),
]

__all__ = ["AnalyticsPayload", "ValuationGapResponse", "get_account_analytics", "router"]


@router.get("/{account_id}/analytics", response_model=AnalyticsPayload)
def get_account_analytics(account_id: int, session: Session = Depends(get_session)) -> AnalyticsPayload:
    repo = PaperTradingRepository(session)
    try:
        return AnalyticsService(repo).get_account_analytics(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
