from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import pytest

from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_DOWN_LIMIT,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_PRE_CLOSE,
    COL_STOCK_ID,
    COL_SUSPEND_TYPE,
    COL_UP_LIMIT,
    AdjustType,
    PeriodType,
)
from paper_trading.storage.market_data import DailyBar, StorageMarketDataProvider
from storage.model.base import Base
from storage.model.stk_limit_a_stock import StkLimitAStock
from storage.model.suspend_d_a_stock import SuspendDAStock
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


class FakeStorageWithEngine:
    """Fake storage that provides both load_history_data_stock and an engine."""

    def __init__(self, engine: Any, data: dict[str, pd.DataFrame]):
        self.engine = engine
        self._inner = FakeHistoryStorage(data)

    def load_history_data_stock(self, stock_id, period, adjust, start_date=None, end_date=None):
        return self._inner.load_history_data_stock(stock_id, period, adjust, start_date, end_date)

    @property
    def calls(self):
        return self._inner.calls


class _LatestCloseStorage:
    def __init__(self):
        self.calls = []

    def load_latest_history_data_stock(self, stock_id, adjust, end_date):
        self.calls.append(("a_share", stock_id, adjust, end_date))
        return {COL_DATE: end_date, COL_CLOSE: 10}

    def load_latest_history_data_stock_hk_ggt(self, stock_id, adjust, end_date):
        self.calls.append(("hk_connect", stock_id, adjust, end_date))
        return {COL_DATE: end_date, COL_CLOSE: 405}


def _etf_frame(symbol: str, trade_date: str, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_STOCK_ID: [symbol],
            COL_DATE: [trade_date],
            COL_OPEN: [close],
            COL_HIGH: [close],
            COL_LOW: [close],
            COL_CLOSE: [close],
        }
    )


def test_etf_daily_bar_reads_raw_etf_daily_without_other_market_queries():
    trade_date = date(2026, 8, 7)
    storage = FakeHistoryStorage(
        {},
        etf_daily_data={
            "518880": pd.DataFrame(
                {
                    COL_STOCK_ID: ["518880"],
                    COL_DATE: [trade_date.isoformat()],
                    COL_OPEN: [8.775],
                    COL_HIGH: [8.892],
                    COL_LOW: [8.774],
                    COL_CLOSE: [8.892],
                }
            )
        },
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([trade_date]))

    bar = provider.get_daily_bar("518880", trade_date, market="etf")

    assert bar == DailyBar("518880", trade_date, Decimal("8.775"), Decimal("8.892"), Decimal("8.774"), Decimal("8.892"))
    assert storage.etf_daily_calls == [("518880", "2026-08-07", "2026-08-07")]
    assert storage.etf_calls == []
    assert storage.calls == []
    assert storage.hk_calls == []


def test_etf_latest_close_reads_last_raw_etf_daily_close_through_requested_date():
    trade_date = date(2026, 8, 10)
    storage = FakeHistoryStorage(
        {},
        etf_daily_data={
            "518880": pd.concat([_etf_frame("518880", "2026-08-08", 8.8), _etf_frame("518880", "2026-08-10", 8.9)])
        },
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([trade_date]))

    assert provider.get_latest_daily_close("518880", trade_date, market="etf") == Decimal("8.9")
    assert storage.etf_daily_calls == [("518880", None, "2026-08-10")]
    assert storage.etf_calls == []
    assert storage.calls == []
    assert storage.hk_calls == []


def test_missing_etf_bar_raises_without_other_market_fallback():
    storage = FakeHistoryStorage({}, etf_daily_data={})
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([]))

    with pytest.raises(KeyError, match="No ETF daily bar for 510300"):
        provider.get_daily_bar("510300", date(2026, 8, 10), market="etf")

    assert storage.etf_daily_calls == [("510300", "2026-08-10", "2026-08-10")]
    assert storage.etf_calls == []
    assert storage.calls == []
    assert storage.hk_calls == []


def test_storage_market_data_provider_loads_daily_bfq_bar_by_unadjusted_db_code():
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.5],
                    COL_HIGH: [10.5],
                    COL_LOW: [9.0],
                    COL_CLOSE: [10.0],
                }
            ),
        }
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    bar = provider.get_daily_bar("000001.SZ", date(2026, 6, 16))

    assert bar.symbol == "000001.SZ"
    assert bar.trade_date == date(2026, 6, 16)
    assert bar.open == Decimal("9.5")
    assert bar.high == Decimal("10.5")
    assert bar.low == Decimal("9.0")
    assert bar.close == Decimal("10.0")
    assert storage.calls == [("000001", PeriodType.DAILY, AdjustType.BFQ, "2026-06-16", "2026-06-16")]


def test_storage_market_data_provider_gets_latest_bfq_close_once_with_market_routing():
    storage = _LatestCloseStorage()
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([]))

    a_close = provider.get_latest_daily_close("000001.SZ", date(2026, 7, 29), "a_share")
    hk_close = provider.get_latest_daily_close("00700.HK", date(2026, 7, 29), "hk_connect")

    assert a_close == Decimal("10")
    assert hk_close == Decimal("405")
    assert storage.calls == [
        ("a_share", "000001", AdjustType.BFQ, "2026-07-29"),
        ("hk_connect", "00700", AdjustType.BFQ, "2026-07-29"),
    ]


def test_storage_market_data_provider_raises_for_missing_ohlc_value():
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.5],
                    COL_HIGH: [10.5],
                    COL_LOW: [pd.NA],
                    COL_CLOSE: [10.0],
                }
            ),
        }
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    with pytest.raises(ValueError, match="Missing market data field"):
        provider.get_daily_bar("000001.SZ", date(2026, 6, 16))


def test_get_daily_bar_populates_limit_prices_when_stk_limit_table_has_data(tmp_path):
    """When stk_limit_a_stock has a row, up_limit/down_limit are populated."""
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'stk_limit.db'}")
    Base.metadata.create_all(engine, tables=[StkLimitAStock.__table__])

    with engine.begin() as conn:
        conn.execute(
            StkLimitAStock.__table__.insert(),
            {
                COL_DATE: date(2026, 6, 16),
                COL_STOCK_ID: "000001",
                COL_PRE_CLOSE: 10.0,
                COL_UP_LIMIT: 11.0,
                COL_DOWN_LIMIT: 9.0,
            },
        )

    storage = FakeStorageWithEngine(
        engine,
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.5],
                    COL_HIGH: [10.5],
                    COL_LOW: [9.0],
                    COL_CLOSE: [10.0],
                }
            ),
        },
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    bar = provider.get_daily_bar("000001.SZ", date(2026, 6, 16))

    assert bar.up_limit == Decimal("11.00")
    assert bar.down_limit == Decimal("9.00")
    engine.dispose()


def test_get_daily_bar_returns_none_limits_when_stk_limit_table_empty(tmp_path):
    """When stk_limit_a_stock has no row for the symbol/date, up_limit/down_limit are None."""
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'stk_limit_empty.db'}")
    Base.metadata.create_all(engine, tables=[StkLimitAStock.__table__])

    storage = FakeStorageWithEngine(
        engine,
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.5],
                    COL_HIGH: [10.5],
                    COL_LOW: [9.0],
                    COL_CLOSE: [10.0],
                }
            ),
        },
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    bar = provider.get_daily_bar("000001.SZ", date(2026, 6, 16))

    assert bar.up_limit is None
    assert bar.down_limit is None
    engine.dispose()


def test_get_daily_bar_with_hk_market_routes_to_hk_ggt_storage():
    """When market='hk_connect', get_daily_bar must use load_history_data_stock_hk_ggt
    and return no up/down limits."""
    storage = FakeHistoryStorage(
        {
            "00700": pd.DataFrame(
                {
                    COL_STOCK_ID: ["00700"],
                    COL_DATE: ["2026-07-21"],
                    COL_OPEN: [400.0],
                    COL_HIGH: [410.0],
                    COL_LOW: [395.0],
                    COL_CLOSE: [405.0],
                }
            ),
        }
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 7, 21)]))

    bar = provider.get_daily_bar("00700", date(2026, 7, 21), market="hk_connect")

    assert bar.symbol == "00700"
    assert bar.open == Decimal("400")
    assert bar.high == Decimal("410")
    assert bar.low == Decimal("395")
    assert bar.close == Decimal("405")
    # HK bars have no price limits
    assert bar.up_limit is None
    assert bar.down_limit is None
    # Must have called the HK GGT storage method, not the A-share one
    assert len(storage.hk_calls) == 1
    assert len(storage.calls) == 0  # A-share load_history_data_stock NOT called


def test_get_daily_bar_with_a_share_market_uses_a_share_storage():
    """When market='a_share' (or omitted), get_daily_bar must use load_history_data_stock."""
    storage = FakeHistoryStorage(
        {
            "000001": pd.DataFrame(
                {
                    COL_STOCK_ID: ["000001"],
                    COL_DATE: ["2026-06-16"],
                    COL_OPEN: [9.5],
                    COL_HIGH: [10.5],
                    COL_LOW: [9.0],
                    COL_CLOSE: [10.0],
                }
            ),
        }
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    # Without explicit market (defaults to A-share)
    bar = provider.get_daily_bar("000001.SZ", date(2026, 6, 16))

    assert bar.symbol == "000001.SZ"
    assert len(storage.calls) == 1
    assert len(storage.hk_calls) == 0


def test_provider_reports_explicit_a_share_suspension(monkeypatch):
    provider = StorageMarketDataProvider(FakeHistoryStorage({}), FakeTradeCalendar([]))
    monkeypatch.setattr(provider, "_load_a_share_suspension", lambda *_: True)

    assert provider.is_symbol_suspended("000001.SZ", date(2026, 8, 25), "a_share") is True


def test_provider_returns_prior_close_with_its_date():
    storage = _LatestCloseStorage()
    storage.load_latest_history_data_stock = lambda *_args, **_kwargs: {
        COL_DATE: "2026-08-22",
        COL_CLOSE: "10.25",
    }
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([]))

    assert provider.get_latest_daily_close_with_date("000001.SZ", date(2026, 8, 25), "a_share") == (
        Decimal("10.25"),
        date(2026, 8, 22),
    )


def test_provider_reports_false_when_market_has_no_suspension_source(monkeypatch):
    provider = StorageMarketDataProvider(FakeHistoryStorage({}), FakeTradeCalendar([]))
    monkeypatch.setattr(provider, "_load_a_share_suspension", lambda *_: True)

    assert provider.is_symbol_suspended("00700.HK", date(2026, 8, 25), "hk_connect") is False
    assert provider.is_symbol_suspended("518880", date(2026, 8, 25), "etf") is False


def test_provider_does_not_treat_missing_bar_as_suspension():
    provider = StorageMarketDataProvider(FakeHistoryStorage({}), FakeTradeCalendar([]))

    assert provider.is_symbol_suspended("000001.SZ", date(2026, 8, 25), "a_share") is False


def test_provider_loads_explicit_a_share_suspension_from_suspend_table(tmp_path):
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'suspend.db'}")
    Base.metadata.create_all(engine, tables=[SuspendDAStock.__table__])
    with engine.begin() as conn:
        conn.execute(
            SuspendDAStock.__table__.insert(),
            {
                COL_STOCK_ID: "000001",
                COL_DATE: date(2026, 8, 25),
                COL_SUSPEND_TYPE: "S",
            },
        )

    storage = FakeStorageWithEngine(engine, {})
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([]))

    assert provider.is_symbol_suspended("000001.SZ", date(2026, 8, 25), "a_share") is True
    assert provider.is_symbol_suspended("000002.SZ", date(2026, 8, 25), "a_share") is False
    engine.dispose()


def test_provider_does_not_treat_resume_row_as_suspension(tmp_path):
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'resume.db'}")
    Base.metadata.create_all(engine, tables=[SuspendDAStock.__table__])
    with engine.begin() as conn:
        conn.execute(
            SuspendDAStock.__table__.insert(),
            {
                COL_STOCK_ID: "000001",
                COL_DATE: date(2026, 8, 25),
                COL_SUSPEND_TYPE: "R",
            },
        )

    storage = FakeStorageWithEngine(engine, {})
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([]))

    assert provider.is_symbol_suspended("000001.SZ", date(2026, 8, 25), "a_share") is False
    engine.dispose()


def test_provider_returns_none_dated_close_when_storage_has_no_row():
    class EmptyLatestCloseStorage:
        def load_latest_history_data_stock(self, stock_id, adjust, end_date):
            del stock_id, adjust, end_date
            return None

    provider = StorageMarketDataProvider(EmptyLatestCloseStorage(), FakeTradeCalendar([]))

    assert provider.get_latest_daily_close_with_date("000001.SZ", date(2026, 8, 25), "a_share") is None
    assert provider.get_latest_daily_close("000001.SZ", date(2026, 8, 25), "a_share") is None


def test_provider_returns_hk_and_etf_prior_close_with_date():
    storage = _LatestCloseStorage()
    etf_storage = FakeHistoryStorage(
        {},
        etf_daily_data={
            "518880": pd.concat([_etf_frame("518880", "2026-08-08", 8.8), _etf_frame("518880", "2026-08-10", 8.9)])
        },
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([]))
    etf_provider = StorageMarketDataProvider(etf_storage, FakeTradeCalendar([]))

    assert provider.get_latest_daily_close_with_date("00700.HK", date(2026, 8, 25), "hk_connect") == (
        Decimal("405"),
        date(2026, 8, 25),
    )
    assert etf_provider.get_latest_daily_close_with_date("518880", date(2026, 8, 10), "etf") == (
        Decimal("8.9"),
        date(2026, 8, 10),
    )
