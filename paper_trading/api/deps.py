import os
import secrets
from collections.abc import Callable, Generator
from datetime import date, datetime, timedelta
from typing import Protocol, runtime_checkable

import pandas_market_calendars as mcal
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.api.auth_evidence import AuthEvidenceCode, error_detail, render_evidence, request_id_from_request
from paper_trading.auth import AuthSettings, decode_session_token
from paper_trading.services.etf_eligibility_service import ETFEligibilityService
from paper_trading.services.position_valuation_service import PositionValuationService
from paper_trading.storage.market_data import (
    MarketDataProvider,
    StorageMarketDataProvider,
)
from paper_trading.storage.repository import PaperTradingRepository
from storage.config import StorageConfig
from storage.model.auth import User
from storage.storage_db import get_storage


@runtime_checkable
class _DateLike(Protocol):
    def date(self) -> date: ...


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("PAPER_TRADING_API_TOKEN")
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Unauthorized", "details": {}},
        )


def _unauthorized(request: Request) -> HTTPException:
    request_id = request_id_from_request(request)
    print(render_evidence(AuthEvidenceCode.SESSION_INVALID, "/paper", request_id))
    return HTTPException(
        status_code=401,
        headers={"X-Request-ID": request_id},
        detail=error_detail(AuthEvidenceCode.SESSION_INVALID, "Session is invalid.", request_id),
    )


def get_session_factory() -> Callable[[], Session]:
    config = StorageConfig()
    url = (
        f"postgresql://{config.get_db_username()}:{config.get_db_password()}"
        f"@{config.get_db_host()}:{config.get_db_port()}/{config.get_db_name()}"
    )
    return sessionmaker(bind=create_engine(url))


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def require_browser_user(request: Request, session: Session = Depends(get_session)) -> User | None:
    authorization = request.headers.get("authorization")
    expected = os.environ.get("PAPER_TRADING_API_TOKEN")
    if expected and authorization == f"Bearer {expected}":
        return None

    settings = AuthSettings.from_environment()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _unauthorized(request)
    try:
        claims = decode_session_token(token, settings)
    except ValueError as exc:
        raise _unauthorized(request) from exc
    try:
        user = session.scalar(select(User).where(User.id == claims.user_id))
    except Exception as exc:
        request_id = request_id_from_request(request)
        print(render_evidence(AuthEvidenceCode.AUTH_UNAVAILABLE, "/paper", request_id))
        raise HTTPException(
            status_code=503,
            headers={"X-Request-ID": request_id},
            detail=error_detail(
                AuthEvidenceCode.AUTH_UNAVAILABLE,
                "登录服务暂时不可用，请稍后重试。",
                request_id,
            ),
        ) from exc
    if user is None or user.session_version != claims.session_version:
        raise _unauthorized(request)
    return user


def require_csrf(
    request: Request,
    browser_user: User | None = Depends(require_browser_user),
) -> None:
    expected = os.environ.get("PAPER_TRADING_API_TOKEN")
    if expected and request.headers.get("authorization") == f"Bearer {expected}":
        return
    if browser_user is None:
        raise _unauthorized(request)
    settings = AuthSettings.from_environment()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("x-csrf-token")
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


class _DataAvailableCalendar:
    """Trade calendar backed by pandas_market_calendars."""

    def __init__(self, calendar_name: str = "XSHG"):
        self._calendar = mcal.get_calendar(calendar_name)

    @staticmethod
    def _to_date(value: object) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, _DateLike):
            return value.date()
        raise TypeError(f"Unsupported trading day value: {value!r}")

    def is_trade_date(self, trade_date: date) -> bool:
        return not self._calendar.schedule(
            start_date=trade_date.isoformat(),
            end_date=trade_date.isoformat(),
        ).empty

    def next_trade_date(self, trade_date: date) -> date:
        trading_days = self._calendar.valid_days(
            start_date=trade_date.isoformat(),
            end_date=(trade_date + timedelta(days=370)).isoformat(),
        )
        for trading_day in trading_days:
            next_date = self._to_date(trading_day)
            if next_date > trade_date:
                return next_date
        return trade_date


def get_market_data_provider() -> MarketDataProvider:
    storage = get_storage()
    return StorageMarketDataProvider(storage, _DataAvailableCalendar())


def get_hk_metadata_provider(session: Session = Depends(get_session)):
    from paper_trading.storage.hk_metadata import HkConnectMetadataProvider

    return HkConnectMetadataProvider(session)


def get_security_name_provider(session: Session = Depends(get_session)):
    from paper_trading.storage.security_metadata import SecurityNameProvider

    return SecurityNameProvider(session)


def get_etf_eligibility_service(session: Session = Depends(get_session)) -> ETFEligibilityService:
    return ETFEligibilityService(PaperTradingRepository(session))


def get_position_valuation_service(
    market_data: MarketDataProvider = Depends(get_market_data_provider),
) -> PositionValuationService:
    return PositionValuationService(market_data)


def get_paper_trading_repository(
    session: Session = Depends(get_session),
    user: User | None = Depends(require_browser_user),
) -> PaperTradingRepository:
    return PaperTradingRepository(session, owner_user_id=None if user is None else user.id)


def get_paper_trading_repository_for_system(session: Session = Depends(get_session)) -> PaperTradingRepository:
    return PaperTradingRepository(session)


SessionDep = Depends(get_session)
AuthDep = Depends(require_api_token)
