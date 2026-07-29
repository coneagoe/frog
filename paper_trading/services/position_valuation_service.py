from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable, Literal, Mapping

from monitor.price_fetcher import fetch_price_map
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
        fetch_prices: Callable[[Iterable[tuple[str, str]]], Mapping[tuple[str, str], object]] | None = None,
        today: date | None = None,
    ):
        self.market_data = market_data
        self.fetch_prices = fetch_price_map if fetch_prices is None else fetch_prices
        self.today = today or date.today()

    def value(self, position) -> PositionValuation:
        return self.value_many([position])[0]

    def value_many(self, positions: Iterable) -> list[PositionValuation]:
        rows = list(positions)
        prices: dict[tuple[str, str], object] = {}
        if rows:
            try:
                items = [(row.symbol, self._source_market(row.market)) for row in rows]
                prices = dict(self.fetch_prices(items))
            except Exception:
                prices = {}
        return [self._value_with_price(row, prices) for row in rows]

    def _value_with_price(self, position, prices: dict[tuple[str, str], object]) -> PositionValuation:
        try:
            key = (position.symbol, self._source_market(position.market))
            price = self._valid_price(prices.get(key))
            source: PriceSource = "real_time"
            if price is None:
                price = self._db_close(position.symbol, position.market)
                source = "db_close"
            if price is not None:
                return self._result(position, price, source)
        except Exception:
            pass
        return PositionValuation(None, None, None)

    @staticmethod
    def _source_market(market: str) -> str:
        return "HK" if market == "hk_connect" else "A"

    def _db_close(self, symbol: str, market: str) -> Decimal | None:
        return self._valid_price(self.market_data.get_latest_daily_close(symbol, self.today, market))

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
        pnl = Decimal(position.total_quantity) * price - Decimal(position.cost_amount)
        return PositionValuation(price, source, pnl)
