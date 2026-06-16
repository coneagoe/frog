import os
from collections.abc import Generator

from fastapi import Depends, Header, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.storage.market_data import (
    InMemoryMarketDataProvider,
    MarketDataProvider,
)
from storage.config import StorageConfig


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


def get_market_data_provider() -> MarketDataProvider:
    return InMemoryMarketDataProvider(bars={}, trade_dates=[])


SessionDep = Depends(get_session)
AuthDep = Depends(require_api_token)
