import os
from collections.abc import Generator
from datetime import date, datetime, timedelta
from typing import Protocol, runtime_checkable

import pandas_market_calendars as mcal
from fastapi import Depends, Header, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.storage.market_data import (
    MarketDataProvider,
    StorageMarketDataProvider,
)
from storage.config import StorageConfig
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


def _session_factory():
    config = StorageConfig()
    url = (
        f"postgresql://{config.get_db_username()}:{config.get_db_password()}"
        f"@{config.get_db_host()}:{config.get_db_port()}/{config.get_db_name()}"
    )
    return sessionmaker(bind=create_engine(url))


def get_session() -> Generator[Session, None, None]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


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


SessionDep = Depends(get_session)
AuthDep = Depends(require_api_token)
