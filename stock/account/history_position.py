from os.path import exists, join
import pandas as pd
import numpy as np
import logging
import pandas_market_calendars as mcal
from stock.common import *
from stock.data.access_general_info import get_stock_name, load_all_stock_general_info
from fund import get_fund_name, load_all_fund_general_info


pd.set_option('display.max_rows', None)


# def check_stock_id(df):
#     if not pattern_valid_stock_id.match(df[col_stock_id]):
#         logging.error(f"Invalid stock id: {df[col_stock_id]}")
#         exit(-1)


def fetch_name(df):
    name = get_stock_name(df[col_stock_id])
    if name:
        return name

    name = get_fund_name(df[col_stock_id])
    if name:
        return name

    return df[col_stock_name]


def convert_data(df: pd.DataFrame) -> pd.DataFrame:
    # df[col_stock_name] = df.apply(fetch_name, axis=1)
    # df = df.set_index(col_stock_name)
    # df = df.drop(columns=[col_stock_id])

    df = df.sort_index()
    df = df.T
    logging.debug(df)
    # df.columns = df.iloc[0]
    # df = df.drop(df.index[0])
    df.rename_axis(col_date, inplace=True)
    df.index = pd.to_datetime(df.index)
    df = df.astype(float)

    logging.debug(df)

    return df


def load_history_position(position_path: str):
    if not exists(position_path):
        logging.warning(f"file does not exist: {position_path}.")
        return None

    df = pd.read_csv(position_path)
    df = df.drop_duplicates()
    # df.apply(check_stock_id, axis=1)
    df[col_stock_id] = df[col_stock_id].astype(str)
    df[col_stock_id] = df[col_stock_id].str.zfill(6)
    df[col_stock_name] = df.apply(fetch_name, axis=1)
    df = df.replace('--', np.nan)
    return df


def load_history_positions(start_date: str, end_date: str) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    assets, profits, profit_rates = ([], [], [])

    market_calendar = mcal.get_calendar('XSHG')
    date_range = mcal.date_range(market_calendar.schedule(start_date, end_date), frequency='1D')
    j = 0
    for i in date_range:
        if j % 2 == 0:
            j += 1
            continue

        j += 1

        date_stamp = f"{i.year}-{str(i.month).zfill(2)}-{str(i.day).zfill(2)}"
        position_path = join(get_stock_position_path(), f"{date_stamp}.csv")
        df = load_history_position(position_path)
        if df is None:
            continue

        df0 = pd.DataFrame({col_stock_name: df[col_stock_name], date_stamp: df[col_market_value]})
        df0 = df0.set_index(col_stock_name)
        assets.append(df0)

        df0 = pd.DataFrame({col_stock_name: df[col_stock_name], date_stamp: df[col_profit]})
        df0 = df0.set_index(col_stock_name)
        profits.append(df0)

        df0 = pd.DataFrame({col_stock_name: df[col_stock_name], date_stamp: df[col_profit_rate]})
        df0 = df0.set_index(col_stock_name)
        profit_rates.append(df0)

    df_asset = pd.concat(assets, axis=1)
    df_profit = pd.concat(profits, axis=1)
    df_profit_rate = pd.concat(profit_rates, axis=1)

    # print(df_profit)

    df_asset = convert_data(df_asset)
    df_profit = convert_data(df_profit)
    df_profit_rate = convert_data(df_profit_rate)

    # print(df_profit_rate)

    return df_asset, df_profit, df_profit_rate
