from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_api_token
from paper_trading.schemas.accounts import (
    AccountResponse,
    CashLedgerResponse,
    CreateAccountRequest,
    ImportPositionsRequest,
    ImportPositionsResponse,
    PositionResponse,
    UpdateAccountFeeRequest,
)
from paper_trading.services.account_service import AccountService
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/accounts", dependencies=[Depends(require_api_token)])


@router.post("", response_model=AccountResponse)
def create_account(request: CreateAccountRequest, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    service = AccountService(repo)
    try:
        account = service.create_account(
            name=request.name,
            initial_cash=request.initial_cash,
            fee_preset=request.fee_preset,
            commission_rate=request.commission_rate,
            min_commission=request.min_commission,
            stamp_duty_rate=request.stamp_duty_rate,
            transfer_fee_rate=request.transfer_fee_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    return account


@router.get("", response_model=list[AccountResponse])
def list_accounts(session: Session = Depends(get_session)):
    return AccountService(PaperTradingRepository(session)).list_accounts()


@router.get("/{account_id}", response_model=AccountResponse | None)
def get_account(account_id: int, session: Session = Depends(get_session)):
    return AccountService(PaperTradingRepository(session)).get_account(account_id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    deleted = AccountService(repo).delete_account(account_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper account not found: {account_id}")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account_fees(
    account_id: int,
    request: UpdateAccountFeeRequest,
    session: Session = Depends(get_session),
):
    payload = request.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="at least one fee field is required",
        )
    repo = PaperTradingRepository(session)
    service = AccountService(repo)
    try:
        account = service.update_account_fees(account_id=account_id, **payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper account not found: {account_id}")
    session.commit()
    return account


@router.get("/{account_id}/positions", response_model=list[PositionResponse])
def list_positions(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).get_positions(account_id)


@router.get("/{account_id}/cash-ledger", response_model=list[CashLedgerResponse])
def list_cash_ledger(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_cash_ledger(account_id)


@router.post("/{account_id}/positions/import", response_model=ImportPositionsResponse)
def import_positions(
    account_id: int,
    request: ImportPositionsRequest,
    session: Session = Depends(get_session),
):
    repo = PaperTradingRepository(session)
    service = AccountService(repo)
    try:
        service.import_positions(account_id, request.positions)
    except ValueError as exc:
        msg = str(exc)
        if "paper account not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg) from exc
    session.commit()
    positions = repo.get_positions(account_id)
    lots_count = repo.count_position_lots(account_id)
    return ImportPositionsResponse(imported_count=len(positions), lots_count=lots_count)
