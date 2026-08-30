from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from paper_trading.api.deps import (
    get_hk_metadata_provider,
    get_market_data_provider,
    get_position_valuation_service,
    get_security_name_provider,
    get_session,
    require_api_token,
)
from paper_trading.api.response_enrichment import enrich_security_names
from paper_trading.schemas.accounts import (
    AccountResponse,
    CashFlowRequest,
    CashFlowResponse,
    CashLedgerResponse,
    CreateAccountRequest,
    ImportPositionsRequest,
    ImportPositionsResponse,
    LedgerRebuildAuditResponse,
    LedgerRebuildRequest,
    PositionResponse,
    UpdateAccountFeeRequest,
)
from paper_trading.services.account_service import AccountService
from paper_trading.services.cash_service import CashService
from paper_trading.services.ledger_rebuild_service import LedgerRebuildService
from paper_trading.services.position_valuation_service import PositionValuationService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository
from paper_trading.storage.security_metadata import SecurityNameProvider

router = APIRouter(prefix="/paper/accounts", dependencies=[Depends(require_api_token)])


def _account_response(repo: PaperTradingRepository, account) -> AccountResponse | None:
    if account is None:
        return None
    payload = {
        field_name: getattr(account, field_name)
        for field_name in AccountResponse.model_fields
        if field_name != "cash_available"
    }
    payload["cash_available"] = repo.get_cash_available(account.id)
    return AccountResponse(**payload)


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
            etf_commission_rate=request.etf_commission_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    return _account_response(repo, account)


@router.get("", response_model=list[AccountResponse])
def list_accounts(session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    accounts = AccountService(repo).list_accounts()
    return [_account_response(repo, account) for account in accounts]


@router.get("/{account_id}", response_model=AccountResponse | None)
def get_account(account_id: int, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    account = AccountService(repo).get_account(account_id)
    return _account_response(repo, account)


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
    return _account_response(repo, account)


@router.get("/{account_id}/positions", response_model=list[PositionResponse])
def list_positions(
    account_id: int,
    session: Session = Depends(get_session),
    provider: SecurityNameProvider = Depends(get_security_name_provider),
    valuation: PositionValuationService = Depends(get_position_valuation_service),
):
    rows = PaperTradingRepository(session).get_positions(account_id)
    responses = enrich_security_names(rows, PositionResponse, provider)
    valuations = valuation.value_many(rows)
    return [response.model_copy(update=result.__dict__) for response, result in zip(responses, valuations)]


@router.get("/{account_id}/cash-ledger", response_model=list[CashLedgerResponse])
def list_cash_ledger(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_cash_ledger(account_id)


@router.post("/{account_id}/ledger-rebuilds", response_model=LedgerRebuildAuditResponse)
def rebuild_account_ledger(
    account_id: int,
    request: LedgerRebuildRequest,
    session: Session = Depends(get_session),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
    hk_metadata: HkConnectMetadataProvider = Depends(get_hk_metadata_provider),
):
    repo = PaperTradingRepository(session)
    if repo.get_account(account_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper account not found: {account_id}")
    service = LedgerRebuildService(repo, market_data, hk_metadata)
    try:
        rebuild = service.rebuild_account_from(
            account_id,
            request.start_date,
            trigger_evidence=request.trigger_evidence or {"source": "api"},
        )
        session.commit()
        return rebuild
    except Exception as exc:
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Historical ledger rebuild failed",
        ) from exc


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


def _cash_flow_response(result) -> CashFlowResponse:
    return CashFlowResponse(
        account_id=result.account.id,
        cash_available=result.cash_available,
        net_asset_value=result.account.net_asset_value,
        share_count=result.account.share_count,
        ledger=result.ledger,
    )


@router.post("/{account_id}/cash/deposit", response_model=CashFlowResponse)
def deposit_cash(account_id: int, request: CashFlowRequest, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    has_positions = any(position.total_quantity > 0 for position in repo.get_positions(account_id))
    market_data = get_market_data_provider() if has_positions else None
    service = CashService(repo, market_data)
    try:
        result = service.deposit(account_id, request.amount, request.trade_date, request.note, request.occurred_at)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    return _cash_flow_response(result)


@router.post("/{account_id}/cash/withdraw", response_model=CashFlowResponse)
def withdraw_cash(account_id: int, request: CashFlowRequest, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    has_positions = any(position.total_quantity > 0 for position in repo.get_positions(account_id))
    market_data = get_market_data_provider() if has_positions else None
    service = CashService(repo, market_data)
    try:
        result = service.withdraw(account_id, request.amount, request.trade_date, request.note, request.occurred_at)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    session.commit()
    return _cash_flow_response(result)
