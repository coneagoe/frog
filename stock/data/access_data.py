import logging
import os
import retrying
import akshare as ak
import pandas as pd
from stock.common import *
from stock.data.access_general_info import is_etf, is_stock
from stock.data.download_history_stock import download_history_stock_1d


def load_stock_history_data(stock_id: str, start_date: str, end_date: str):
    data_path = os.path.join(get_stock_1d_path(), f"{stock_id}.csv")
    if not os.path.exists(data_path):
        download_history_stock_1d(stock_id, start_date, end_date)
        pass

    if os.path.exists(data_path):
        start_date_ts0 = pd.Timestamp(start_date)
        end_date_ts0 = pd.Timestamp(end_date)
        df = pd.read_csv(data_path, encoding='utf_8_sig')
        df[COL_DATE] = pd.to_datetime(df[COL_DATE])

        if df[COL_DATE].iloc[0] <= start_date_ts0 and df[COL_DATE].iloc[-1] >= end_date_ts0:
            df = df[(df[COL_DATE] >= start_date_ts0) & (df[COL_DATE] <= end_date_ts0)]
            df[COL_CLOSE] = df[COL_CLOSE].astype(float)
            return df

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

        df = df[(df[COL_DATE] >= start_date_ts0) & (df[COL_DATE] <= end_date_ts0)]
        df[COL_CLOSE] = df[COL_CLOSE].astype(float)
        return df
    else:
        df = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust="")
        if df.empty:
            logging.warning(f"No data available for stock({stock_id}) from {start_date} to {end_date}.")
            return None

        df.to_csv(data_path, encoding='utf_8_sig', index=False)

        return df


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def load_history_data(security_id: str, start_date: str, end_date: str, adjust="qfq") -> pd.DataFrame | None:
    """
    :param security_id:
        ".IXIC": NASDAQ Composite
        ".DJI": Dow Jones Industrial Average
        ".INX": S&P 500
    :param start_date:
    :param end_date:
    :param adjust:
    :return:
    """
    if is_stock(security_id):
        df = ak.stock_zh_a_hist(symbol=security_id, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust=adjust)
        return df

    if is_etf(security_id):
        try:
            df = ak.fund_etf_hist_em(symbol=security_id, period="daily",
                                     start_date=start_date, end_date=end_date,
                                     adjust=adjust)
            return df
        except KeyError:
            start_timestamp = pd.Timestamp(start_date)
            end_timestamp = pd.Timestamp(end_date)
            df = ak.fund_money_fund_info_em(security_id)
            df[u'净值日期'] = pd.to_datetime(df[u'净值日期'])
            df = df[(df[u'净值日期'] >= start_timestamp) & (df[u'净值日期'] <= end_timestamp)]
            df = df.rename(columns={'净值日期': COL_DATE, '每万份收益': COL_CLOSE})
            df[COL_CLOSE] = df[COL_CLOSE].astype(float)
            df = df.set_index(COL_DATE)
            df = df.sort_index(ascending=True)
            df = df.reset_index()

            return df

    if security_id in [".IXIC", ".DJI", ".INX"]:
        df = ak.index_us_stock_sina(symbol=security_id)
        df = df.rename(columns={'date': COL_DATE, 'close': COL_CLOSE})
        return df

    logging.warning(f"wrong stock id({security_id}), please check.")
    return None
