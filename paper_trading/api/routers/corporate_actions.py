from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_market_data_provider, get_paper_trading_repository, get_session, require_csrf
from paper_trading.domain.enums import CorporateActionType
from paper_trading.domain.errors import CorporateActionError
from paper_trading.schemas.corporate_actions import (
    CorporateActionCreateRequest,
    CorporateActionCreateResponse,
    CorporateActionEventResponse,
    CorporateActionImpactResponse,
)
from paper_trading.schemas.snapshot_recalculation import SnapshotRecalculationResponse
from paper_trading.services.corporate_action_service import CorporateActionIdempotencyConflict, CorporateActionService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/accounts")


def _aware(value: datetime | None, name: str) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise HTTPException(status_code=422, detail=f"{name} must include a timezone offset")
    return value


def _response(result) -> CorporateActionCreateResponse:
    impact = result.impact
    return CorporateActionCreateResponse(
        event=CorporateActionEventResponse.model_validate(result.event),
        impact=CorporateActionImpactResponse(
            cash_delta=impact.cash_delta,
            quantity_delta=impact.quantity_delta,
            before_quantity=impact.before_quantity,
            after_quantity=impact.after_quantity,
            before_cost_amount=impact.before_cost_amount,
            after_cost_amount=impact.after_cost_amount,
            before_cash_available=impact.before_cash_available,
            after_cash_available=impact.after_cash_available,
            affected_start_date=impact.affected_start_date,
            affected_end_date=impact.affected_end_date,
        ),
        recalculation=SnapshotRecalculationResponse(
            account_id=result.recalculation.account_id,
            updated_dates=result.recalculation.updated_dates,
            unavailable_dates=result.recalculation.unavailable_dates,
            failed_dates=result.recalculation.failed_dates,
            errors=result.recalculation.errors,
        ),
    )


@router.post("/{account_id}/corporate-actions", response_model=CorporateActionCreateResponse)
def create_corporate_action(
    account_id: int,
    request: CorporateActionCreateRequest,
    session: Session = Depends(get_session),
    repo: PaperTradingRepository = Depends(get_paper_trading_repository),
    _: None = Depends(require_csrf),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
):
    service = CorporateActionService(repo, market_data=market_data)
    try:
        result = service.apply(
            account_id,
            request.symbol,
            request.event_type,
            request.event_at,
            request.idempotency_key,
            request.parameters,
            request.market,
        )
    except KeyError as exc:
        session.rollback()
        detail = f"paper account not found: {account_id}" if repo.owner_user_id is None else "paper account not found"
        raise HTTPException(status_code=404, detail=detail) from exc
    except CorporateActionIdempotencyConflict as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message, "details": exc.details}
        ) from exc
    except CorporateActionError as exc:
        session.rollback()
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message, "details": exc.details}
        ) from exc
    except (ValueError, RuntimeError) as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _response(result)


@router.get("/{account_id}/corporate-actions", response_model=list[CorporateActionEventResponse])
def list_corporate_actions(
    account_id: int,
    symbol: str | None = None,
    event_type: CorporateActionType | None = None,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
    repo: PaperTradingRepository = Depends(get_paper_trading_repository),
):
    if repo.get_account(account_id) is None:
        detail = f"paper account not found: {account_id}" if repo.owner_user_id is None else "paper account not found"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return [
        CorporateActionEventResponse.model_validate(action)
        for action in repo.list_corporate_actions(
            account_id,
            symbol=symbol,
            event_type=event_type,
            start_at=_aware(start_at, "start_at"),
            end_at=_aware(end_at, "end_at"),
        )
    ]
