from fastapi import APIRouter, Depends, HTTPException

from paper_trading.api.deps import get_paper_trading_repository
from paper_trading.schemas.snapshots import SnapshotResponse
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(
    prefix="/paper/accounts/{account_id}/snapshots",
)


@router.get("", response_model=list[SnapshotResponse])
def list_snapshots(account_id: int, repo: PaperTradingRepository = Depends(get_paper_trading_repository)):
    if repo.get_account(account_id) is None:
        detail = f"paper account not found: {account_id}" if repo.owner_user_id is None else "paper account not found"
        raise HTTPException(status_code=404, detail=detail)
    return repo.list_snapshots(account_id)
