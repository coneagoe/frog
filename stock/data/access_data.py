import logging
import os
import pandas as pd
from stock.const import (
    COL_DATE,
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_ETF_ID,
    COL_ETF_NAME,
)
from stock.common import (
    get_stock_general_info_path,
    get_etf_general_info_path,
    get_stock_data_path_1d,
    get_stock_data_path_1w,
    get_stock_data_path_1M,
    get_hk_ggt_stock_general_info_path,
)
from stock.data.download_data import (
    download_general_info_stock,
    download_general_info_etf,
    download_history_data_stock,
    download_history_data_etf,
    download_history_data_us_index,
    download_history_data_a_index,
    download_general_info_hk_ggt_stock,
)
from utility import (
    is_older_than_a_month,
    is_older_than_a_week
)


g_df_stocks = None
g_df_etfs = None
g_df_hk_ggt_stocks = None


def load_history_data_stock(stock_id: str, period: str, start_date: str,
                            end_date: str, adjust: str) -> pd.DataFrame:
    download_history_data_stock(stock_id, period, start_date, end_date, adjust)

    data_file_name = f"{stock_id}_{adjust}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), data_file_name)
    elif period == 'weekly':
        data_path = os.path.join(get_stock_data_path_1w(), data_file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), data_file_name)

    start_date_ts0 = pd.Timestamp(start_date)
    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    df = df[(start_date_ts0 <= df[COL_DATE]) & (df[COL_DATE] <= end_date_ts0)]
    df[COL_CLOSE] = df[COL_CLOSE].astype(float)
    return df


def load_history_data_etf(etf_id: str, period: str, start_date: str,
                          end_date: str, adjust: str) -> pd.DataFrame:
    download_history_data_etf(etf_id, period, start_date, end_date, adjust)

    data_file_name = f"{etf_id}_{adjust}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), data_file_name)
    elif period == 'weekly':
        data_path = os.path.join(get_stock_data_path_1w(), data_file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), data_file_name)

    start_date_ts0 = pd.Timestamp(start_date)
    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    df = df[(start_date_ts0 <= df[COL_DATE]) & (df[COL_DATE] <= end_date_ts0)]
    df[COL_CLOSE] = df[COL_CLOSE].astype(float)
    return df


def load_history_data_us_index(index: str, period: str, start_date: str,
                               end_date: str) -> pd.DataFrame:
    download_history_data_us_index(index=index, period=period,
                                   start_date=start_date, end_date=end_date)

    data_file_name = f"{index}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), data_file_name)
    elif period == 'weekly':
        data_path = os.path.join(get_stock_data_path_1w(), data_file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), data_file_name)

    start_date_ts0 = pd.Timestamp(start_date)
    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    df = df[(start_date_ts0 <= df[COL_DATE]) & (df[COL_DATE] <= end_date_ts0)]
    df[COL_CLOSE] = df[COL_CLOSE].astype(float)
    return df


def load_history_data_a_index(index: str, period: str, start_date: str,
                              end_date: str) -> pd.DataFrame:
    download_history_data_a_index(index=index, period=period,
                                  start_date=start_date, end_date=end_date)

    data_file_name = f"{index}.csv"
    if period == 'daily':
        data_path = os.path.join(get_stock_data_path_1d(), data_file_name)
    elif period == 'weekly':
        data_path = os.path.join(get_stock_data_path_1w(), data_file_name)
    else:
        data_path = os.path.join(get_stock_data_path_1M(), data_file_name)

    start_date_ts0 = pd.Timestamp(start_date)
    end_date_ts0 = pd.Timestamp(end_date)
    df = pd.read_csv(data_path, encoding='utf_8_sig')
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])

    df = df[(start_date_ts0 <= df[COL_DATE]) & (df[COL_DATE] <= end_date_ts0)]
    return df


def load_history_data(security_id: str, period: str, start_date: str, end_date: str,
                      adjust="qfq") -> pd.DataFrame:
    if is_stock(security_id):
        return load_history_data_stock(stock_id=security_id, period=period,
                                       start_date=start_date, end_date=end_date,
                                       adjust=adjust)

    if is_etf(security_id):
        return load_history_data_etf(etf_id=security_id, period=period,
                                     start_date=start_date, end_date=end_date,
                                     adjust=adjust)

    if is_us_index(security_id):
        return load_history_data_us_index(index=security_id, period=period,
                                          start_date=start_date, end_date=end_date)

    if is_a_index(security_id):
        return load_history_data_a_index(index=security_id, period=period,
                                         start_date=start_date, end_date=end_date)


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


def is_a_index(security_id: str):
    return security_id in [
        "sz399987",   # 中证酒
        'sh000813',   # 细分化工
        'sz399552',   # 央视成长
        "sz399998",   # 中证煤炭
        "csi930901",  # 动漫游戏
    ]


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


def is_hk_ggt_stock(stock_id: str):
    '''
    是否是港股通股票
    '''
    global g_df_hk_ggt_stocks

    if g_df_hk_ggt_stocks is None:
        g_df_hk_ggt_stocks = load_all_hk_ggt_stock_general_info()

    try:
        return stock_id in g_df_hk_ggt_stocks[COL_STOCK_ID].values
    except KeyError:
        return False


def load_all_hk_ggt_stock_general_info():
    global g_df_hk_ggt_stocks

    if g_df_hk_ggt_stocks is not None:
        return g_df_hk_ggt_stocks

    stock_general_info_path = get_hk_ggt_stock_general_info_path()
    if not os.path.exists(stock_general_info_path) or \
            is_older_than_a_month(stock_general_info_path):
        download_general_info_hk_ggt_stock()

    g_df_hk_ggt_stocks = pd.read_csv(stock_general_info_path)
    g_df_hk_ggt_stocks[COL_STOCK_ID] = g_df_hk_ggt_stocks[COL_STOCK_ID].astype(str)
    g_df_hk_ggt_stocks[COL_STOCK_ID] = g_df_hk_ggt_stocks[COL_STOCK_ID].str.zfill(5)
    return g_df_hk_ggt_stocks
