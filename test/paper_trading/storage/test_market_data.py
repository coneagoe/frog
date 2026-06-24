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
    COL_UP_LIMIT,
    AdjustType,
    PeriodType,
)
from paper_trading.storage.market_data import StorageMarketDataProvider
from storage.model.base import Base
from storage.model.stk_limit_a_stock import StkLimitAStock
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
