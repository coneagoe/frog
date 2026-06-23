from datetime import date

import pandas as pd

from common.const import COL_DATE


class FakeHistoryStorage:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self._data = data
        self.calls = []

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
