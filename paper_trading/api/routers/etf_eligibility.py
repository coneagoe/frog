from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_api_token
from paper_trading.domain.enums import ETFEligibilityStatus
from paper_trading.schemas.etf_eligibility import (
    ClassifyETFEligibilityRequest,
    ETFEligibilityListResponse,
    ETFEligibilityResponse,
)
from paper_trading.services.etf_eligibility_service import ETFEligibilityService
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/etf-eligibility", dependencies=[Depends(require_api_token)])


def _unprocessable(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": code, "message": message, "details": {}},
    )


@router.get("", response_model=ETFEligibilityListResponse)
def list_etf_eligibility(
    status_filter: str | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
):
    try:
        items = PaperTradingRepository(session).list_etf_eligibility(status_filter)
    except ValueError as exc:
        raise _unprocessable("INVALID_ETF_ELIGIBILITY_STATUS", str(exc)) from exc
    return ETFEligibilityListResponse(items=items)


@router.get("/{symbol}", response_model=ETFEligibilityResponse)
def get_etf_eligibility(symbol: str, session: Session = Depends(get_session)):
    try:
        eligibility = PaperTradingRepository(session).get_etf_eligibility(symbol)
    except ValueError as exc:
        raise _unprocessable("INVALID_ETF_SYMBOL", str(exc)) from exc
    if eligibility is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ETF eligibility not found: {symbol}")
    return eligibility


@router.post("/{symbol}/classify", response_model=ETFEligibilityResponse)
def classify_etf_eligibility(
    symbol: str,
    request: ClassifyETFEligibilityRequest,
    session: Session = Depends(get_session),
):
    try:
        eligibility = ETFEligibilityService(PaperTradingRepository(session)).classify(
            symbol, ETFEligibilityStatus(request.status), request.reviewed_by
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        if "classification must be supported or money_market" in message:
            code = "INVALID_ETF_ELIGIBILITY_CLASSIFICATION"
        elif "exchange must be SH or SZ" in message:
            code = "INVALID_ETF_EXCHANGE"
        elif "listing status must be L" in message:
            code = "INVALID_ETF_LISTING_STATUS"
        else:
            code = "INVALID_ETF_ELIGIBILITY"
        raise _unprocessable(code, message) from exc
    session.commit()
    return eligibility
