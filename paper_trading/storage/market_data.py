from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


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


class InMemoryMarketDataProvider:
    def __init__(self, bars: dict[tuple[str, date], DailyBar], trade_dates: list[date]):
        self.bars = bars
        self.trade_dates = sorted(trade_dates)

    def is_trade_date(self, trade_date: date) -> bool:
        return trade_date in self.trade_dates

    def next_trade_date(self, trade_date: date) -> date:
        for candidate in self.trade_dates:
            if candidate > trade_date:
                return candidate
        return trade_date

    def get_daily_bar(self, symbol: str, trade_date: date) -> DailyBar:
        return self.bars[(symbol, trade_date)]
