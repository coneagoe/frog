from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_browser_user
from paper_trading.domain.enums import DataGapRecoveryBatchStatus, DataGapRecoveryStatus
from paper_trading.schemas.data_gap_recovery import (
    DataGapRecoveryBatchPage,
    DataGapRecoveryBatchResponse,
    DataGapRecoveryGapResponse,
    DataGapRecoveryPage,
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
    stock_id: str | None = Query(default=None, pattern=r"^[0-9]{6}$"),
    session: Session = Depends(get_session),
    user=Depends(require_browser_user),
):
    repository = DataGapRecoveryRepository(session)
    owner = None if user is None else user.id
    items = repository.list_gaps(
        offset,
        page_size,
        status=status,
        business_date=business_date,
        stock_id=stock_id,
        owner_user_id=owner,
    )
    return DataGapRecoveryPage(
        items=[DataGapRecoveryGapResponse.model_validate(item) for item in items],
        offset=offset,
        page_size=page_size,
        total_count=repository.count_gaps(
            status=status, business_date=business_date, stock_id=stock_id, owner_user_id=owner
        ),
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
