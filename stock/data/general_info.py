from os.path import exists
import logging
import pandas as pd
from stock.common import *


def get_all_stock_general_info():
    stock_general_info_path = get_stock_general_info_path()

    if not exists(stock_general_info_path):
        logging.error(f"No {stock_general_info_path}")
        return None

    df = pd.read_csv(stock_general_info_path)
    df[col_stock_id] = df[col_stock_id].astype(str)
    df[col_stock_id] = df[col_stock_id].str.zfill(6)
    return df


def get_stock_name(df: pd.DataFrame, stock_id: str):
    """
    :param df: all fund general info
    :param stock_id:
    :return:
    """
    df = df.set_index(col_stock_id)
    try:
        return df.at[stock_id, col_stock_name]
    except KeyError:
        return None
