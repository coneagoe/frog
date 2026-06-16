from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_api_token
from paper_trading.schemas.snapshots import SnapshotResponse
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(
    prefix="/paper/accounts/{account_id}/snapshots",
    dependencies=[Depends(require_api_token)],
)


@router.get("", response_model=list[SnapshotResponse])
def list_snapshots(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_snapshots(account_id)
