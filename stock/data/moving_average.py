from datetime import date
import numpy as np
import pandas as pd
from . access_data import load_history_data
from .. common import col_close


def _get_ma(stock_id: str, period: int, index: int) -> float:
    end_date = date.today()
    start_date = end_date - pd.Timedelta(days=period * 2)
    start_date_ts = start_date.strftime('%Y%m%d')
    end_date_ts = end_date.strftime('%Y%m%d')
    df_history_data = load_history_data(stock_id, start_date_ts, end_date_ts)
    if df_history_data is not None:
        ma = df_history_data[col_close].rolling(window=period).mean()
        return round(ma.iloc[index], 2)

    return np.nan


def get_yesterday_ma(stock_id: str, period: int) -> float:
    return _get_ma(stock_id, period, -2)


def get_today_ma(stock_id: str, period: int) -> float:
    return _get_ma(stock_id, period, -1)

