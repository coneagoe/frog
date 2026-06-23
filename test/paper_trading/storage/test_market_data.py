from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    AdjustType,
    PeriodType,
)
from paper_trading.storage.market_data import StorageMarketDataProvider
from test.paper_trading.fakes import FakeHistoryStorage, FakeTradeCalendar


def test_storage_market_data_provider_loads_daily_bfq_bar_by_unadjusted_db_code():
    storage = FakeHistoryStorage({
        "000001": pd.DataFrame({
            COL_STOCK_ID: ["000001"],
            COL_DATE: ["2026-06-16"],
            COL_OPEN: [9.5],
            COL_HIGH: [10.5],
            COL_LOW: [9.0],
            COL_CLOSE: [10.0],
        }),
    })
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
    storage = FakeHistoryStorage({
        "000001": pd.DataFrame({
            COL_STOCK_ID: ["000001"],
            COL_DATE: ["2026-06-16"],
            COL_OPEN: [9.5],
            COL_HIGH: [10.5],
            COL_LOW: [pd.NA],
            COL_CLOSE: [10.0],
        }),
    })
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([date(2026, 6, 16)]))

    with pytest.raises(ValueError, match="Missing market data field"):
        provider.get_daily_bar("000001.SZ", date(2026, 6, 16))
