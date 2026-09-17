from datetime import date, datetime, timedelta
from typing import Protocol, runtime_checkable

import pandas_market_calendars as mcal


@runtime_checkable
class _DateLike(Protocol):
    def date(self) -> date: ...


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
