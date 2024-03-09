import logging
import os
import akshare as ak
import pandas as pd
from stock.common import (
    get_stock_1d_path,
    COL_DATE,
    COL_CLOSE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_ETF_ID,
    COL_ETF_NAME,
    get_stock_general_info_path,
    get_etf_general_info_path
)
from stock.data.download_data import (
    download_general_info_stock,
    download_general_info_etf,
    download_history_data_stock,
    download_history_data_etf,
    download_history_data_us_index,
    download_history_stock_1d
)
from utility import (
    is_older_than_a_month,
    is_older_than_a_week
)


g_df_stocks = None
g_df_etfs = None


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


def load_history_data(security_id: str, start_date: str, end_date: str, adjust="qfq") -> pd.DataFrame | None:
    if is_stock(security_id):
        return download_history_data_stock(security_id, "daily", start_date, end_date, adjust)

    if is_etf(security_id):
        return download_history_data_etf(security_id, "daily", start_date, end_date, adjust)

    if is_us_index(security_id):
        df = download_history_data_us_index(security_id)
        df[COL_DATE] = pd.to_datetime(df[COL_DATE])
        df = df.loc[(df[COL_DATE] >= start_date) & (df[COL_DATE] <= end_date)]
        return df

    logging.warning(f"wrong stock id({security_id}), please check.")
    return None


def load_all_stock_general_info():
    global g_df_stocks

    if g_df_stocks is not None:
        return g_df_stocks

    stock_general_info_path = get_stock_general_info_path()
    if not os.path.exists(stock_general_info_path) or \
            is_older_than_a_month(stock_general_info_path):
        download_general_info_stock()

    g_df_stocks = pd.read_csv(stock_general_info_path)
    g_df_stocks[COL_STOCK_ID] = g_df_stocks[COL_STOCK_ID].astype(str)
    g_df_stocks[COL_STOCK_ID] = g_df_stocks[COL_STOCK_ID].str.zfill(6)
    return g_df_stocks


def load_all_etf_general_info():
    global g_df_etfs

    if g_df_etfs is not None:
        return g_df_etfs

    etf_general_info_path = get_etf_general_info_path()
    if not os.path.exists(etf_general_info_path) or \
            is_older_than_a_week(etf_general_info_path):
        download_general_info_etf()

    g_df_etfs = pd.read_csv(etf_general_info_path)
    g_df_etfs[COL_ETF_ID] = g_df_etfs[COL_ETF_ID].astype(str)
    g_df_etfs[COL_ETF_ID] = g_df_etfs[COL_ETF_ID].str.zfill(6)
    return g_df_etfs


def is_stock(stock_id: str):
    global g_df_stocks

    if g_df_stocks is None:
        g_df_stocks = load_all_stock_general_info()

    try:
        return stock_id in g_df_stocks[COL_STOCK_ID].values
    except KeyError:
        logging.error(f"haha stock_id: {stock_id}")
        return False


def get_stock_name(stock_id: str):
    global g_df_stocks

    if g_df_stocks is None:
        g_df_stocks = load_all_stock_general_info()

    try:
        return g_df_stocks.loc[g_df_stocks[COL_STOCK_ID] == stock_id][COL_STOCK_NAME].iloc[0]
    except IndexError:
        return None


def is_etf(etf_id: str):
    global g_df_etfs

    if g_df_etfs is None:
        g_df_etfs = load_all_etf_general_info()

    return etf_id in g_df_etfs[COL_ETF_ID].values


def get_etf_name(etf_id: str):
    global g_df_etfs

    if g_df_etfs is None:
        g_df_etfs = load_all_etf_general_info()

    try:
        return g_df_etfs.loc[g_df_etfs[COL_ETF_ID] == etf_id][COL_ETF_NAME].iloc[0]
    except IndexError:
        return None


def is_us_index(security_id: str):
    return security_id in [".IXIC", ".DJI", ".INX"]


def get_security_name(security_id: str) -> str:
    if security_id == '.IXIC':
        return 'NASDAQ Composite'
    elif security_id == '.DJI':
        return 'Dow Jones Industrial Average'
    elif security_id == '.INX':
        return 'S&P 500'
    elif is_stock(security_id):
        return get_stock_name(security_id)
    else:
        return get_etf_name(security_id)
