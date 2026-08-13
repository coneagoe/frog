from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd

import paper_trading.services.position_valuation_service as valuation_module
from common.const import COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_STOCK_ID
from paper_trading.services.position_valuation_service import PositionValuationService
from paper_trading.storage.market_data import StorageMarketDataProvider
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


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
        fetch_prices=lambda items: {("000001", "A"): "4.00"},
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
        fetch_prices=lambda items: {("00700", "HK"): None},
        today=date(2026, 7, 29),
    )

    result = service.value(_position(symbol="00700", market="hk_connect", total_quantity=2, cost_amount=Decimal("800")))

    assert result.mark_price == Decimal("410")
    assert result.price_source == "db_close"
    assert result.unrealized_pnl == Decimal("20")
    assert market_data.calls == [("00700", date(2026, 7, 29), "hk_connect")]


def test_missing_or_nonpositive_prices_leave_position_unvalued():
    market_data = _FakeMarketData()
    service = PositionValuationService(market_data, fetch_prices=lambda items: {("000001", "A"): "0"})

    result = service.value(_position())

    assert result.mark_price is None
    assert result.price_source is None
    assert result.unrealized_pnl is None


def test_price_failure_is_isolated_to_one_symbol():
    market_data = _FakeMarketData({("000002", "a_share"): Decimal("12")})

    def fetch_prices(items):
        prices = {}
        for symbol, market in items:
            if symbol == "000001":
                raise RuntimeError("provider failure")
            prices[(symbol, market)] = "bad"
        return prices

    service = PositionValuationService(market_data, fetch_prices=fetch_prices)

    failed = service.value(_position(symbol="000001"))
    valued = service.value(_position(symbol="000002"))

    assert failed.mark_price is None
    assert valued.mark_price == Decimal("12")


def test_value_many_fetches_real_time_prices_once_and_preserves_order():
    market_data = _FakeMarketData()
    calls = []

    def fetch_prices(items):
        calls.append(list(items))
        return {("000001", "A"): "4", ("00700", "HK"): "8"}

    service = PositionValuationService(market_data, fetch_prices=fetch_prices)
    result = service.value_many([_position(), _position(symbol="00700", market="hk_connect")])

    assert calls == [[("000001", "A"), ("00700", "HK")]]
    assert [item.mark_price for item in result] == [Decimal("4"), Decimal("8")]


def test_value_many_uses_default_batch_adapter_and_falls_back_per_row(monkeypatch):
    market_data = _FakeMarketData(
        {
            ("000001", "a_share"): Decimal("11"),
            ("00700", "hk_connect"): Decimal("410"),
        }
    )
    calls = []

    def fetch_prices(items):
        calls.append(list(items))
        return {("000001", "A"): "bad", ("00700", "HK"): None}

    monkeypatch.setattr(valuation_module, "fetch_price_map", fetch_prices)
    service = PositionValuationService(market_data, today=date(2026, 7, 29))

    result = service.value_many([_position(), _position(symbol="00700", market="hk_connect")])

    assert calls == [[("000001", "A"), ("00700", "HK")]]
    assert [item.mark_price for item in result] == [Decimal("11"), Decimal("410")]
    assert [item.price_source for item in result] == ["db_close", "db_close"]


def test_value_many_always_honors_injected_batch_adapter():
    market_data = _FakeMarketData()
    batch_calls = []

    def fetch_prices(items):
        batch_calls.append(list(items))
        return {("000001", "A"): "4"}

    service = PositionValuationService(
        market_data,
        fetch_prices=fetch_prices,
    )

    result = service.value_many([_position()])

    assert batch_calls == [[("000001", "A")]]
    assert result[0].mark_price == Decimal("4")


def test_value_many_falls_back_per_position_when_batch_quote_is_missing():
    market_data = _FakeMarketData({("00700", "hk_connect"): Decimal("410")})

    service = PositionValuationService(
        market_data,
        fetch_prices=lambda items: {("000001", "A"): "12"},
        today=date(2026, 7, 29),
    )
    result = service.value_many([_position(), _position(symbol="00700", market="hk_connect", total_quantity=2)])

    assert result[0].mark_price == Decimal("12")
    assert result[1].mark_price == Decimal("410")
    assert result[1].price_source == "db_close"


def test_etf_valuation_bypasses_a_share_live_quotes_and_uses_etf_daily_close():
    storage = FakeHistoryStorage(
        {},
        etf_daily_data={
            "510300": pd.DataFrame(
                {
                    COL_STOCK_ID: ["510300", "510300"],
                    COL_DATE: ["2026-08-08", "2026-08-10"],
                    COL_OPEN: [3.0, 3.1],
                    COL_HIGH: [3.1, 3.2],
                    COL_LOW: [2.9, 3.0],
                    COL_CLOSE: [3.05, 3.10],
                }
            )
        },
    )
    market_data = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 8, 10)]))
    live_calls = []

    def fetch_prices(items):
        live_calls.append(list(items))
        return {}

    service = PositionValuationService(
        market_data,
        fetch_prices=fetch_prices,
        today=date(2026, 8, 10),
    )

    result = service.value(_position(symbol="510300", market="etf", total_quantity=100, cost_amount=Decimal("300")))

    assert live_calls == []
    assert result.mark_price == Decimal("3.10")
    assert result.price_source == "db_close"
    assert storage.etf_daily_calls == [("510300", None, "2026-08-10")]
    assert storage.etf_calls == []
    assert storage.calls == []
    assert storage.hk_calls == []
