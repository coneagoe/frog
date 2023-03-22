from os.path import exists
import logging
import pandas as pd
from stock.common import *


g_df_stocks = None
g_df_etfs = None


def load_all_stock_general_info():
    global g_df_stocks

    if g_df_stocks is not None:
        return g_df_stocks

    stock_general_info_path = get_stock_general_info_path()

    if not exists(stock_general_info_path):
        logging.error(f"No {stock_general_info_path}")
        return None

    g_df_stocks = pd.read_csv(stock_general_info_path)
    g_df_stocks[col_stock_id] = g_df_stocks[col_stock_id].astype(str)
    g_df_stocks[col_stock_id] = g_df_stocks[col_stock_id].str.zfill(6)
    return g_df_stocks


def load_all_etf_general_info():
    global g_df_etfs

    if g_df_etfs is not None:
        return g_df_etfs

    etf_general_info_path = get_etf_general_info_path()

    if not exists(etf_general_info_path):
        logging.error(f"No {etf_general_info_path}")
        return None

    g_df_etfs = pd.read_csv(etf_general_info_path)
    g_df_etfs[col_etf_id] = g_df_etfs[col_etf_id].astype(str)
    g_df_etfs[col_etf_id] = g_df_etfs[col_etf_id].str.zfill(6)
    return g_df_etfs


def get_stock_name(stock_id: str):
    global g_df_stocks

    if g_df_stocks is None:
        g_df_stocks = load_all_stock_general_info()

    try:
        return g_df_stocks.loc[g_df_stocks[col_stock_id] == stock_id][col_stock_name].iloc[0]
    except IndexError:
        return None


def get_etf_name(etf_id: str):
    global g_df_etfs

    if g_df_etfs is None:
        g_df_etfs = load_all_etf_general_info()

    try:
        return g_df_etfs.loc[g_df_etfs[col_etf_id] == etf_id][col_etf_name].iloc[0]
    except IndexError:
        return None
