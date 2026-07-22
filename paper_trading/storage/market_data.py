from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

import pandas as pd
from sqlalchemy import text

from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_DOWN_LIMIT,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_UP_LIMIT,
    AdjustType,
    PeriodType,
)
from storage.model import tb_name_stk_limit_a_stock


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    up_limit: Decimal | None = None
    down_limit: Decimal | None = None
    suspended: bool = False


class MarketDataProvider(Protocol):
    def is_trade_date(self, trade_date: date) -> bool: ...

    def next_trade_date(self, trade_date: date) -> date: ...

    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar: ...


class TradeCalendar(Protocol):
    def is_trade_date(self, trade_date: date) -> bool: ...

    def next_trade_date(self, trade_date: date) -> date: ...


class StorageMarketDataProvider:
    """Market data provider backed by a history storage and a trade calendar."""

    def __init__(self, storage, trade_calendar: TradeCalendar):
        self._storage = storage
        self._trade_calendar = trade_calendar

    def is_trade_date(self, trade_date: date) -> bool:
        return self._trade_calendar.is_trade_date(trade_date)

    def next_trade_date(self, trade_date: date) -> date:
        return self._trade_calendar.next_trade_date(trade_date)

    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
        """Load a daily bar, routing to HK GGT storage when market is 'hk_connect'."""
        stock_id = self._to_storage_stock_id(symbol)
        if market == "hk_connect":
            return self._get_hk_daily_bar(stock_id, symbol, trade_date)
        return self._get_a_share_daily_bar(stock_id, symbol, trade_date)

    def _get_a_share_daily_bar(self, stock_id: str, symbol: str, trade_date: date) -> DailyBar:
        df = self._storage.load_history_data_stock(
            stock_id,
            PeriodType.DAILY,
            AdjustType.BFQ,
            start_date=trade_date.isoformat(),
            end_date=trade_date.isoformat(),
        )
        if df.empty:
            raise KeyError(f"No daily bar for {symbol} on {trade_date.isoformat()}")
        row = df.iloc[-1]
        up_limit, down_limit = self._load_limit_prices(symbol, trade_date)
        return DailyBar(
            symbol=symbol,
            trade_date=trade_date,
            open=self._decimal_field(row, COL_OPEN, symbol, trade_date),
            high=self._decimal_field(row, COL_HIGH, symbol, trade_date),
            low=self._decimal_field(row, COL_LOW, symbol, trade_date),
            close=self._decimal_field(row, COL_CLOSE, symbol, trade_date),
            up_limit=up_limit,
            down_limit=down_limit,
        )

    def _get_hk_daily_bar(self, stock_id: str, symbol: str, trade_date: date) -> DailyBar:
        df = self._storage.load_history_data_stock_hk_ggt(
            stock_id,
            PeriodType.DAILY,
            AdjustType.BFQ,
            start_date=trade_date.isoformat(),
            end_date=trade_date.isoformat(),
        )
        if df.empty:
            raise KeyError(f"No HK daily bar for {symbol} on {trade_date.isoformat()}")
        row = df.iloc[-1]
        # HK stocks have no A-share price limits
        return DailyBar(
            symbol=symbol,
            trade_date=trade_date,
            open=self._decimal_field(row, COL_OPEN, symbol, trade_date),
            high=self._decimal_field(row, COL_HIGH, symbol, trade_date),
            low=self._decimal_field(row, COL_LOW, symbol, trade_date),
            close=self._decimal_field(row, COL_CLOSE, symbol, trade_date),
            up_limit=None,
            down_limit=None,
        )

    def _load_limit_prices(self, symbol: str, trade_date: date) -> tuple[Decimal | None, Decimal | None]:
        """Attempt to load limit prices from the stk_limit_a_stock table.

        Returns (up_limit, down_limit) when data is available,
        or (None, None) when the table or row does not exist.
        """
        stock_id = self._to_storage_stock_id(symbol)
        engine = getattr(self._storage, "engine", None)
        if engine is None:
            return None, None

        try:
            sql = (
                f'SELECT "{COL_UP_LIMIT}", "{COL_DOWN_LIMIT}" '
                f"FROM {tb_name_stk_limit_a_stock} "
                f'WHERE "{COL_STOCK_ID}" = :stock_id AND "{COL_DATE}" = :trade_date'
            )
            df = pd.read_sql(text(sql), engine, params={"stock_id": stock_id, "trade_date": trade_date.isoformat()})
            if df.empty:
                return None, None
            row = df.iloc[-1]
            up_raw = row.get(COL_UP_LIMIT)
            down_raw = row.get(COL_DOWN_LIMIT)
            up_limit = Decimal(str(up_raw)) if pd.notna(up_raw) else None
            down_limit = Decimal(str(down_raw)) if pd.notna(down_raw) else None
            return up_limit, down_limit
        except Exception:
            return None, None

    @staticmethod
    def _to_storage_stock_id(symbol: str) -> str:
        if "." in symbol:
            first, second = symbol.split(".", 1)
            if first.isdigit():
                return first
            if second.isdigit():
                return second
        return symbol

    @staticmethod
    def _decimal_field(row, column: str, symbol: str, trade_date: date) -> Decimal:
        value = row.get(column)
        if pd.isna(value):
            raise ValueError(f"Missing market data field {column} for {symbol} on {trade_date.isoformat()}")
        return Decimal(str(value))
