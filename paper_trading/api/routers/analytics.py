from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from paper_trading.api.deps import get_paper_trading_repository
from paper_trading.schemas.analytics import AnalyticsResponse, AnalyticsUnavailableResponse, ValuationGapResponse
from paper_trading.services.analytics_service import AnalyticsService
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/accounts", tags=["paper-analytics"])


def _account_not_found(repo: PaperTradingRepository, account_id: int) -> HTTPException:
    detail = f"paper account not found: {account_id}" if repo.owner_user_id is None else "paper account not found"
    return HTTPException(status_code=404, detail=detail)


AnalyticsPayload = Annotated[
    AnalyticsResponse | AnalyticsUnavailableResponse,
    Field(discriminator="available"),
]

__all__ = ["AnalyticsPayload", "ValuationGapResponse", "get_account_analytics", "router"]


@router.get("/{account_id}/analytics", response_model=AnalyticsPayload)
def get_account_analytics(
    account_id: int, repo: PaperTradingRepository = Depends(get_paper_trading_repository)
) -> AnalyticsPayload:
    try:
        return AnalyticsService(repo).get_account_analytics(account_id)
    except KeyError as exc:
        raise _account_not_found(repo, account_id) from exc
