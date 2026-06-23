from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

import pandas as pd

from common.const import COL_CLOSE, COL_HIGH, COL_LOW, COL_OPEN, AdjustType, PeriodType


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

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar: ...


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

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        stock_id = self._to_storage_stock_id(symbol)
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

        return DailyBar(
            symbol=symbol,
            trade_date=trade_date,
            open=self._decimal_field(row, COL_OPEN, symbol, trade_date),
            high=self._decimal_field(row, COL_HIGH, symbol, trade_date),
            low=self._decimal_field(row, COL_LOW, symbol, trade_date),
            close=self._decimal_field(row, COL_CLOSE, symbol, trade_date),
        )

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
