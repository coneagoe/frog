import os
import logging
import pandas as pd
import akshare as ak
from stock.common import (
    COL_DATE,
    get_stock_1d_path
)


def download_history_stock_1d(stock_id: str, start_date: str, end_date: str):
    data_path = os.path.join(get_stock_1d_path(), f"{stock_id}.csv")
    if not os.path.exists(data_path):
        df = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust="")

        if df.empty:
            logging.warning(f"download history data {stock_id} fail, please check")
            return False

        df.to_csv(data_path, encoding='utf_8_sig', index=False)

        return True

    start_date_ts0 = pd.Timestamp(start_date)
    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    if start_date_ts0 < df[COL_DATE].iloc[0]:
        end_date_ts1 = df[COL_DATE].iloc[0] - pd.Timedelta(days=1)
        df0 = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                 start_date=start_date, end_date=end_date_ts1.strftime('%Y%m%d'),
                                 adjust="")
        df0[COL_DATE] = pd.to_datetime(df0[COL_DATE])
        df = pd.concat([df, df0], ignore_index=True)

    if end_date_ts0 > df[COL_DATE].iloc[-1]:
        start_date_ts1 = df[COL_DATE].iloc[-1] + pd.Timedelta(days=1)
        df0 = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                 start_date=start_date_ts1.strftime('%Y%m%d'), end_date=end_date,
                                 adjust="")
        df0[COL_DATE] = pd.to_datetime(df0[COL_DATE])
        df = pd.concat([df, df0], ignore_index=True)

    df = df.sort_values(by=[COL_DATE], ascending=True)
    df = df.drop_duplicates(subset=[COL_DATE])

    df.to_csv(data_path, encoding='utf_8_sig', index=False)
