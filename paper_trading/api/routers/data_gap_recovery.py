from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_browser_user, require_csrf
from paper_trading.domain.enums import DataGapRecoveryBatchStatus, DataGapRecoveryStatus
from paper_trading.schemas.data_gap_recovery import (
    DataGapRecoveryApprovalRequest,
    DataGapRecoveryBatchPage,
    DataGapRecoveryBatchResponse,
    DataGapRecoveryGapResponse,
    DataGapRecoveryPage,
    DataGapRecoveryReopenRequest,
)
from paper_trading.storage.data_gap_recovery_repository import DataGapRecoveryRepository

router = APIRouter(prefix="/paper/data-gap-recovery", tags=["data-gap-recovery"])


def _serialize_evidence(evidence: dict[str, list[object]]) -> dict[str, list[dict[str, object]]]:
    return {
        key: [{name: value for name, value in item.__dict__.items() if not name.startswith("_")} for item in items]
        for key, items in evidence.items()
    }


@router.get("/gaps", response_model=DataGapRecoveryPage)
def list_gaps(
    offset: int = Query(default=0, ge=0),
    page_size: int = Query(default=50, ge=1, le=200),
    status: DataGapRecoveryStatus | None = None,
    business_date: date | None = None,
    stock_id: str | None = Query(default=None, pattern=r"^[0-9]{5,6}$"),
    market: str | None = Query(default=None, pattern=r"^(a_share|hk_connect)$"),
    session: Session = Depends(get_session),
    user=Depends(require_browser_user),
):
    repository = DataGapRecoveryRepository(session)
    owner = None if user is None else user.id
    if stock_id is not None:
        expected_market = "hk_connect" if len(stock_id) == 5 else "a_share"
        if market is not None and market != expected_market:
            raise HTTPException(status_code=422, detail="stock_id does not match market")
        market = market or expected_market
    items = repository.list_gaps(
        offset,
        page_size,
        status=status,
        business_date=business_date,
        stock_id=stock_id,
        market=market,
        owner_user_id=owner,
    )
    total_count = repository.count_gaps(
        status=status, business_date=business_date, stock_id=stock_id, market=market, owner_user_id=owner
    )
    return DataGapRecoveryPage(
        items=[DataGapRecoveryGapResponse.model_validate(item) for item in items],
        offset=offset,
        page_size=page_size,
        total_count=total_count,
    )


@router.get("/gaps/{gap_id}", response_model=DataGapRecoveryGapResponse)
def get_gap(gap_id: int, session: Session = Depends(get_session), user=Depends(require_browser_user)):
    repository = DataGapRecoveryRepository(session)
    owner = None if user is None else user.id
    gap = repository.get_gap(gap_id, owner)
    if gap is None:
        raise HTTPException(status_code=404, detail="gap not found")
    return {**gap.__dict__, **_serialize_evidence(repository.gap_evidence(gap_id, owner))}


@router.get("/batches", response_model=DataGapRecoveryBatchPage)
def list_batches(
    offset: int = Query(default=0, ge=0),
    page_size: int = Query(default=50, ge=1, le=200),
    status: DataGapRecoveryBatchStatus | None = None,
    session: Session = Depends(get_session),
    user=Depends(require_browser_user),
):
    repository = DataGapRecoveryRepository(session)
    owner = None if user is None else user.id
    items = repository.list_batches(offset, page_size, status=status, owner_user_id=owner)
    return DataGapRecoveryBatchPage(
        items=[DataGapRecoveryBatchResponse.model_validate(item) for item in items],
        offset=offset,
        page_size=page_size,
        total_count=repository.count_batches(status, owner),
    )


@router.get("/batches/{batch_id}", response_model=DataGapRecoveryBatchResponse)
def get_batch(batch_id: int, session: Session = Depends(get_session), user=Depends(require_browser_user)):
    repository = DataGapRecoveryRepository(session)
    owner = None if user is None else user.id
    batch = repository.get_batch(batch_id, owner)
    if batch is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return {**batch.__dict__, **_serialize_evidence(repository.batch_evidence(batch_id, owner))}


def _require_mutation_user(user):
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="browser session required")
    return user


def _user_snapshot(user) -> dict[str, object]:
    return {
        "user_id": user.id,
        "email": user.email,
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
    }


def _mutate_gap(gap_id: int, operation, session: Session, user, candidate_hash: str | None = None):
    repository = DataGapRecoveryRepository(session)
    gap = repository.get_gap(gap_id, user.id)
    if gap is None:
        raise HTTPException(status_code=404, detail="gap not found")
    if candidate_hash is not None and gap.latest_candidate_hash != candidate_hash:
        session.rollback()
        raise HTTPException(status_code=409, detail="candidate hash is stale")
    try:
        operation(repository, user)
        if candidate_hash is not None and gap.latest_candidate_hash != candidate_hash:
            session.rollback()
            raise HTTPException(status_code=409, detail="candidate hash is stale")
        response = {**gap.__dict__, **_serialize_evidence(repository.gap_evidence(gap_id, user.id))}
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return response


@router.post("/gaps/{gap_id}/approve", response_model=DataGapRecoveryGapResponse)
def approve_gap(
    gap_id: int,
    request: DataGapRecoveryApprovalRequest,
    session: Session = Depends(get_session),
    user=Depends(require_browser_user),
    _: None = Depends(require_csrf),
):
    user = _require_mutation_user(user)
    return _mutate_gap(
        gap_id,
        lambda repository, authenticated: repository.approve_gap(
            gap_id, request.candidate_hash, authenticated.id, _user_snapshot(authenticated), reason=request.reason
        ),
        session,
        user,
        request.candidate_hash,
    )


@router.post("/gaps/{gap_id}/reject", response_model=DataGapRecoveryGapResponse)
def reject_gap(
    gap_id: int,
    request: DataGapRecoveryApprovalRequest,
    session: Session = Depends(get_session),
    user=Depends(require_browser_user),
    _: None = Depends(require_csrf),
):
    user = _require_mutation_user(user)
    return _mutate_gap(
        gap_id,
        lambda repository, authenticated: repository.reject_gap(
            gap_id, request.candidate_hash, authenticated.id, _user_snapshot(authenticated), reason=request.reason
        ),
        session,
        user,
        request.candidate_hash,
    )


@router.post("/gaps/{gap_id}/reopen", response_model=DataGapRecoveryGapResponse)
def reopen_gap(
    gap_id: int,
    request: DataGapRecoveryReopenRequest,
    session: Session = Depends(get_session),
    user=Depends(require_browser_user),
    _: None = Depends(require_csrf),
):
    user = _require_mutation_user(user)
    return _mutate_gap(
        gap_id,
        lambda repository, authenticated: repository.reopen_gap(
            gap_id, authenticated.id, _user_snapshot(authenticated), reason=request.reason
        ),
        session,
        user,
    )
