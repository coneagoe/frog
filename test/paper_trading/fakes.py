from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from common.const import COL_DATE
from paper_trading.storage.market_data import DailyBar


class FakeHistoryStorage:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self._data = data
        self.calls: list[tuple[Any, ...]] = []

    def load_history_data_stock(self, stock_id, period, adjust, start_date=None, end_date=None):
        self.calls.append((stock_id, period, adjust, start_date, end_date))
        df = self._data.get(stock_id, pd.DataFrame()).copy()
        if df.empty:
            return df
        if start_date:
            df = df[df[COL_DATE] >= start_date]
        if end_date:
            df = df[df[COL_DATE] <= end_date]
        return df


class FakeTradeCalendar:
    def __init__(self, trade_dates: list[date]):
        self.trade_dates = sorted(trade_dates)

    def is_trade_date(self, trade_date: date) -> bool:
        return trade_date in self.trade_dates

    def next_trade_date(self, trade_date: date) -> date:
        for candidate in self.trade_dates:
            if candidate > trade_date:
                return candidate
        return trade_date


class FakeMarketDataProvider:
    """Market data provider that makes all orders match by default.

    The returned DailyBar has a wide price range (low=1, high=100) so every
    limit price falls within range.  Override by passing explicit bars.
    """

    def __init__(self, bars: dict[tuple[str, date], DailyBar] | None = None):
        self._bars = bars or {}

    def is_trade_date(self, trade_date: date) -> bool:
        return True

    def next_trade_date(self, trade_date: date) -> date:
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        key = (symbol, trade_date)
        if key in self._bars:
            return self._bars[key]
        return DailyBar(
            symbol=symbol,
            trade_date=trade_date,
            open=Decimal("10"),
            high=Decimal("100"),
            low=Decimal("1"),
            close=Decimal("50"),
        )
