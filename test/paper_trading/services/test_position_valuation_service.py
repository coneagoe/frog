from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from paper_trading.services.position_valuation_service import PositionValuationService


def _position(**overrides):
    values = {
        "symbol": "000001",
        "market": "a_share",
        "total_quantity": 3,
        "cost_amount": Decimal("10.00"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeMarketData:
    def __init__(self, closes=None):
        self.closes = closes or {}
        self.calls = []

    def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
        self.calls.append((symbol, trade_date, market))
        return self.closes.get((symbol, market))

    def is_trade_date(self, trade_date):
        return True

    def next_trade_date(self, trade_date):
        return trade_date

    def get_daily_bar(self, symbol, trade_date, market=None):
        raise AssertionError("legacy date-walking fallback must not be used")


def test_valid_live_price_has_priority_and_uses_total_cost_formula():
    market_data = _FakeMarketData({("000001", "a_share"): Decimal("99")})
    service = PositionValuationService(
        market_data,
        fetch_price=lambda symbol, market: "4.00",
        today=date(2026, 7, 29),
    )

    result = service.value(_position())

    assert result.mark_price == Decimal("4.00")
    assert result.price_source == "real_time"
    assert result.unrealized_pnl == Decimal("2.00")
    assert market_data.calls == []


def test_invalid_live_prices_fall_back_to_latest_bfq_close_with_market_routing():
    market_data = _FakeMarketData({("00700", "hk_connect"): Decimal("410")})
    service = PositionValuationService(
        market_data,
        fetch_price=lambda symbol, market: None,
        today=date(2026, 7, 29),
    )

    result = service.value(_position(symbol="00700", market="hk_connect", total_quantity=2, cost_amount=Decimal("800")))

    assert result.mark_price == Decimal("410")
    assert result.price_source == "db_close"
    assert result.unrealized_pnl == Decimal("20")
    assert market_data.calls == [("00700", date(2026, 7, 29), "hk_connect")]


def test_missing_or_nonpositive_prices_leave_position_unvalued():
    market_data = _FakeMarketData()
    service = PositionValuationService(market_data, fetch_price=lambda symbol, market: "0")

    result = service.value(_position())

    assert result.mark_price is None
    assert result.price_source is None
    assert result.unrealized_pnl is None


def test_price_failure_is_isolated_to_one_symbol():
    market_data = _FakeMarketData({("000002", "a_share"): Decimal("12")})

    def fetch_price(symbol, market):
        if symbol == "000001":
            raise RuntimeError("provider failure")
        return "bad"

    service = PositionValuationService(market_data, fetch_price=fetch_price)

    failed = service.value(_position(symbol="000001"))
    valued = service.value(_position(symbol="000002"))

    assert failed.mark_price is None
    assert valued.mark_price == Decimal("12")
