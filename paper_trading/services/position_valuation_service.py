from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable, Literal

from monitor.price_fetcher import fetch_current_price
from paper_trading.storage.market_data import MarketDataProvider

PriceSource = Literal["real_time", "db_close"]


@dataclass(frozen=True)
class PositionValuation:
    mark_price: Decimal | None
    price_source: PriceSource | None
    unrealized_pnl: Decimal | None


class PositionValuationService:
    def __init__(
        self,
        market_data: MarketDataProvider,
        *,
        fetch_price: Callable[[str, str], object] = fetch_current_price,
        today: date | None = None,
    ):
        self.market_data = market_data
        self.fetch_price = fetch_price
        self.today = today or date.today()

    def value(self, position) -> PositionValuation:
        try:
            price = self._real_time_price(position.symbol, position.market)
            source: PriceSource = "real_time"
            if price is None:
                price = self._db_close(position.symbol, position.market)
                source = "db_close"
            if price is not None:
                return self._result(position, price, source)
        except Exception:
            pass
        return PositionValuation(None, None, None)

    def _real_time_price(self, symbol: str, market: str) -> Decimal | None:
        source_market = "HK" if market == "hk_connect" else "A"
        try:
            return self._valid_price(self.fetch_price(symbol, source_market))
        except Exception:
            return None

    def _db_close(self, symbol: str, market: str) -> Decimal | None:
        # The provider routes BFQ history by market. Walk backwards so the
        # fallback remains usable on weekends and market holidays.
        for days_ago in range(366):
            try:
                bar = self.market_data.get_daily_bar(symbol, self.today - timedelta(days=days_ago), market)
            except Exception:
                continue
            price = self._valid_price(bar.close)
            if price is not None:
                return price
        return None

    @staticmethod
    def _valid_price(value: object) -> Decimal | None:
        try:
            price = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if not price.is_finite() or price <= 0:
            return None
        return price

    @staticmethod
    def _result(position, price: Decimal, source: PriceSource) -> PositionValuation:
        cost_per_share = position.cost_amount / Decimal(position.total_quantity)
        pnl = (price - cost_per_share) * Decimal(position.total_quantity)
        return PositionValuation(price, source, pnl)
