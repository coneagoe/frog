import re
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from common.const import (
    COL_AMOUNT,
    COL_CHANGE,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_TURNOVER_RATE,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)
from download.dl.downloader_tushare import (
    _empty_hk_history_dataframe,
    convert_date,
    hk_history_columns,
    hk_history_numeric_columns,
)


def download_history_data_stock_hk_yf(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.BFQ,
) -> pd.DataFrame:
    if not re.fullmatch(r"\d{5}", stock_id):
        raise ValueError("Stock ID must be 5 digits.")
    if period != PeriodType.DAILY:
        raise ValueError("yfinance HK history only supports daily period.")
    if adjust != AdjustType.BFQ:
        raise ValueError("yfinance HK history only supports BFQ adjustment.")

    symbol = f"{int(stock_id):04d}.HK"
    start = datetime.strptime(convert_date(start_date), "%Y%m%d").strftime("%Y-%m-%d")
    end = (datetime.strptime(convert_date(end_date), "%Y%m%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.Ticker(symbol).history(
        start=start,
        end=end,
        interval="1d",
        auto_adjust=False,
        actions=False,
        back_adjust=False,
        repair=False,
        prepost=False,
        raise_errors=True,
    )
    if raw is None or raw.empty:
        return _empty_hk_history_dataframe()

    missing = {"Open", "High", "Low", "Close", "Volume"}.difference(raw.columns)
    if missing:
        raise ValueError(
            f"Missing required column '{sorted(missing)[0]}' in yfinance history response"
        )

    normalized = raw.rename(
        columns={
            "Open": COL_OPEN,
            "High": COL_HIGH,
            "Low": COL_LOW,
            "Close": COL_CLOSE,
            "Volume": COL_VOLUME,
        }
    ).copy()
    index = pd.DatetimeIndex(normalized.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    normalized[COL_DATE] = index
    normalized[COL_STOCK_ID] = stock_id
    normalized[COL_AMOUNT] = normalized[COL_CLOSE] * normalized[COL_VOLUME]
    normalized[COL_CHANGE] = 0.0
    normalized[COL_CHANGE_RATE] = 0.0
    normalized[COL_TURNOVER_RATE] = 0.0
    normalized = normalized.reindex(columns=hk_history_columns)
    normalized[hk_history_numeric_columns] = normalized[hk_history_numeric_columns].astype("float64")
    return normalized.reset_index(drop=True)
