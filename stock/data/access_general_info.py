import os
import logging
import re
import pandas as pd
from stock.common import *
from stock.data.download_general_info import download_general_info_stock, download_general_info_etf
from utility import is_older_than_a_month, is_older_than_a_week


pattern_stock_id = re.compile(r'^600|601|603|00|30|688')

g_df_stocks = None
g_df_etfs = None


def load_all_stock_general_info():
    global g_df_stocks

    if g_df_stocks is not None:
        return g_df_stocks

    stock_general_info_path = get_stock_general_info_path()
    if not os.path.exists(stock_general_info_path) or \
            is_older_than_a_month(stock_general_info_path):
        download_general_info_stock()

    g_df_stocks = pd.read_csv(stock_general_info_path)
    g_df_stocks[col_stock_id] = g_df_stocks[col_stock_id].astype(str)
    g_df_stocks[col_stock_id] = g_df_stocks[col_stock_id].str.zfill(6)
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
    g_df_etfs[col_etf_id] = g_df_etfs[col_etf_id].astype(str)
    g_df_etfs[col_etf_id] = g_df_etfs[col_etf_id].str.zfill(6)
    return g_df_etfs


def is_stock(stock_id: str):
    #print(f"haha: {stock_id}")
    #return pattern_stock_id.match(stock_id)

    global g_df_stocks

    if g_df_stocks is None:
        g_df_stocks = load_all_stock_general_info()

    try:
        return stock_id in g_df_stocks[col_stock_id].values
    except:
        logging.error(f"haha stock_id: {stock_id}")
        return False


def get_stock_name(stock_id: str):
    global g_df_stocks

    if g_df_stocks is None:
        g_df_stocks = load_all_stock_general_info()

    try:
        return g_df_stocks.loc[g_df_stocks[col_stock_id] == stock_id][col_stock_name].iloc[0]
    except IndexError:
        return None


def is_etf(etf_id: str):
    global g_df_etfs

    if g_df_etfs is None:
        g_df_etfs = load_all_etf_general_info()

    return etf_id in g_df_etfs[col_etf_id].values


def get_etf_name(etf_id: str):
    global g_df_etfs

    if g_df_etfs is None:
        g_df_etfs = load_all_etf_general_info()

    try:
        return g_df_etfs.loc[g_df_etfs[col_etf_id] == etf_id][col_etf_name].iloc[0]
    except IndexError:
        return None


def get_stock_or_etf_name(security_id: str) -> str:
    if is_stock(security_id):
        return get_stock_name(security_id)
    else:
        return get_etf_name(security_id)
