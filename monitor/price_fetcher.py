"""Fetch current price and historical OHLCV data for monitor conditions."""

from datetime import date, timedelta
from typing import Optional

import pandas as pd

from common.const import AdjustType, PeriodType
from stock.data.eastmoney.fetch_close_price import fetch_close_price
from storage import get_storage

# How many calendar days to fetch per requested trading period
# (conservative: ~2.5× to account for weekends and holidays)
_CALENDAR_MULTIPLIER = 3


def fetch_current_price(stock_code: str, market: str) -> float:
    """
    Fetch the latest real-time price for a stock/ETF/HK share.

    Uses EastMoney API (same as existing monitor_fallback_stock task).

    Args:
        stock_code: Stock/ETF code (e.g. '600519', '510300', '00700').
        market: 'A', 'ETF', or 'HK'.

    Returns:
        Current price as float (np.nan on failure).
    """
    return fetch_close_price(stock_code)


def fetch_history_df(
    stock_code: str,
    market: str,
    min_periods: int = 60,
) -> Optional[pd.DataFrame]:
    """
    Load historical daily close data from storage.

    Args:
        stock_code: Stock/ETF/HK code.
        market: 'A', 'ETF', or 'HK'.
        min_periods: Minimum number of trading rows required; returns None if fewer.

    Returns:
        DataFrame with at least COL_CLOSE column, sorted ascending by date,
        or None if insufficient data.
    """
    storage = get_storage()
    end_date = date.today().isoformat()
    start_date = (
        date.today() - timedelta(days=min_periods * _CALENDAR_MULTIPLIER)
    ).isoformat()

    if market == "ETF":
        df = storage.load_history_data_etf(
            etf_id=stock_code,
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )
    elif market == "HK":
        df = storage.load_history_data_stock_hk_ggt(
            stock_id=stock_code,
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )
    else:  # A-share (default)
        df = storage.load_history_data_stock(
            stock_id=stock_code,
            period=PeriodType.DAILY,
            adjust=AdjustType.QFQ,
            start_date=start_date,
            end_date=end_date,
        )

    if df is None or len(df) < min_periods:
        return None

    return df.sort_values(by=df.columns[0]).reset_index(drop=True)
