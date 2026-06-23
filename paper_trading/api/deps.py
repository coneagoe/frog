import os
from collections.abc import Generator
from datetime import date

from fastapi import Depends, Header, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from common.const import COL_DATE
from paper_trading.storage.market_data import (
    MarketDataProvider,
    StorageMarketDataProvider,
)
from storage.config import StorageConfig
from storage.model.history_data_a_stock import (
    tb_name_history_data_daily_a_stock_bfq,
)
from storage.storage_db import get_storage


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


class _DBTradeCalendar:
    """Minimal trade calendar backed by the stock history table."""

    def __init__(self, storage):
        self._engine = storage.engine

    @staticmethod
    def _to_date(value) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    def is_trade_date(self, trade_date: date) -> bool:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT 1 FROM {tb_name_history_data_daily_a_stock_bfq} "
                    f'WHERE "{COL_DATE}" = :d LIMIT 1'
                ),
                {"d": trade_date.isoformat()},
            )
            return result.scalar() is not None

    def next_trade_date(self, trade_date: date) -> date:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    f'SELECT "{COL_DATE}" FROM {tb_name_history_data_daily_a_stock_bfq} '
                    f'WHERE "{COL_DATE}" > :d ORDER BY "{COL_DATE}" ASC LIMIT 1'
                ),
                {"d": trade_date.isoformat()},
            )
            row = result.fetchone()
            if row is not None:
                return self._to_date(row[0])
            return trade_date


def get_market_data_provider() -> MarketDataProvider:
    storage = get_storage()
    return StorageMarketDataProvider(storage, _DBTradeCalendar(storage))


SessionDep = Depends(get_session)
AuthDep = Depends(require_api_token)
