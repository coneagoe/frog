from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from paper_trading.api.deps import (
    get_market_data_provider,
    get_session,
    require_api_token,
)
from paper_trading.domain.enums import OrderStatus
from paper_trading.schemas.orders import (
    CreateOrderRequest,
    OrderResponse,
    TradeResponse,
    TradeValidityCheckResponse,
    UpdateOrderCommentRequest,
)
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_service import OrderService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.repository import PaperTradingRepository

router = APIRouter(prefix="/paper", dependencies=[Depends(require_api_token)])


@router.post("/accounts/{account_id}/orders", response_model=OrderResponse)
def create_order(
    account_id: int,
    request: CreateOrderRequest,
    session: Session = Depends(get_session),
    market_data: MarketDataProvider = Depends(get_market_data_provider),
):
    repo = PaperTradingRepository(session)
    if repo.get_account(account_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"paper account not found: {account_id}")
    order_service = OrderService(repo, market_data)
    order = order_service.place_order(
        account_id,
        request.symbol,
        request.side,
        request.quantity,
        request.limit_price,
        request.trade_date,
        request.idempotency_key,
        request.comment,
    )
    if order.status == OrderStatus.ACCEPTED.value:
        snapshot_service = SnapshotService(repo, market_data)
        MatchingService(repo, market_data, snapshot_service).run(request.trade_date, account_id)
        session.refresh(order)
    session.commit()
    return order


@router.get("/accounts/{account_id}/orders", response_model=list[OrderResponse])
def list_orders(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_orders(account_id)


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).get_order(order_id)


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: int, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    order = OrderService(repo, get_market_data_provider()).cancel_order(order_id)
    session.commit()
    return order


@router.patch("/orders/{order_id}/comment", response_model=OrderResponse)
def update_order_comment(order_id: int, request: UpdateOrderCommentRequest, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    order = OrderService(repo, get_market_data_provider()).update_order_comment(order_id, request.comment)
    session.commit()
    return order


@router.get(
    "/accounts/{account_id}/orders/{order_id}/validity-checks",
    response_model=list[TradeValidityCheckResponse],
)
def list_order_validity_checks(account_id: int, order_id: int, session: Session = Depends(get_session)):
    repo = PaperTradingRepository(session)
    order = repo.get_order(order_id)
    if order.account_id != account_id:
        return []
    return repo.list_trade_validity_checks(order_id)


@router.get("/accounts/{account_id}/trades", response_model=list[TradeResponse])
def list_trades(account_id: int, session: Session = Depends(get_session)):
    return PaperTradingRepository(session).list_trades(account_id)
