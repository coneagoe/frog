from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from paper_trading.api.deps import get_session, require_api_token
from paper_trading.schemas.accounts import (
    AccountResponse,
    CashLedgerResponse,
    CreateAccountRequest,
    PositionResponse,
)
from paper_trading.services.account_service import AccountService
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper/accounts", dependencies=[Depends(require_api_token)])


@router.post("", response_model=AccountResponse)
def create_account(request: CreateAccountRequest, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    account = AccountService(repo).create_account(request.name, request.initial_cash)
    session.commit()
    return account


@router.get("", response_model=list[AccountResponse])
def list_accounts(session: Session = Depends(get_session)):
    return AccountService(PaperTradingRepository(session)).list_accounts()


@router.get("/{account_id}", response_model=AccountResponse | None)
def get_account(account_id: int, session: Session = Depends(get_session)):
    return AccountService(PaperTradingRepository(session)).get_account(account_id)


@router.get("/{account_id}/positions", response_model=list[PositionResponse])
def list_positions(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).get_positions(account_id)


@router.get("/{account_id}/cash-ledger", response_model=list[CashLedgerResponse])
def list_cash_ledger(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_cash_ledger(account_id)
