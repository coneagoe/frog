from os.path import exists, join
import pandas as pd
from fund.common import *
from fund.data.general_info import get_fund_name, get_all_fund_general_info
import logging
import pandas_market_calendars as mcal
import numpy as np


all_general_info = None


def fetch_fund_name(df):
    return get_fund_name(all_general_info, df[col_fund_id])


def convert_data(df: pd.DataFrame) -> pd.DataFrame:
    # df[col_stock_name] = df.index.to_series().apply(get_fund_name, axis=1)
    # df = df.set_index(col_stock_name)
    # df = df.drop(columns=[col_fund_id])
    df = df.T
    logging.debug(df)
    # df.columns = df.iloc[0]
    # df = df.drop(df.index[0])
    df.rename_axis(col_date, inplace=True)
    df.index = pd.to_datetime(df.index)
    df = df.astype(float)
    # logging.debug(df)
    return df


def load_history_position(position_path: str):
    if not exists(position_path):
        logging.warning(f"file does not exist: {position_path}.")
        return None

    df = pd.read_csv(position_path)
    df = df.drop_duplicates()
    df[col_fund_id] = df[col_fund_id].astype(str)
    df[col_fund_id] = df[col_fund_id].str.zfill(6)
    df[col_fund_name] = df.apply(fetch_fund_name, axis=1)
    df = df.replace('--', np.nan)
    return df


def load_history_positions(start_date: str, end_date: str) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    global all_general_info
    assets, profits, profit_rates = ([], [], [])
    all_general_info = get_all_fund_general_info()

    market_calendar = mcal.get_calendar('XSHG')
    date_range = mcal.date_range(market_calendar.schedule(start_date, end_date), frequency='1D')
    j = 0
    for i in date_range:
        if j % 2 == 0:
            j += 1
            continue

        j += 1

        date_stamp = f"{i.year}-{str(i.month).zfill(2)}-{str(i.day).zfill(2)}"
        position_path = join(get_fund_position_path(), f"{date_stamp}.csv")
        df = load_history_position(position_path)
        if df is None:
            continue

        df0 = pd.DataFrame({col_fund_name: df[col_fund_name], date_stamp: df[col_asset]})
        df0 = df0.set_index(col_fund_name)
        assets.append(df0)

        df0 = pd.DataFrame({col_fund_name: df[col_fund_name], date_stamp: df[col_profit]})
        df0 = df0.set_index(col_fund_name)
        profits.append(df0)

        df0 = pd.DataFrame({col_fund_name: df[col_fund_name], date_stamp: df[col_profit_rate]})
        df0 = df0.set_index(col_fund_name)
        profit_rates.append(df0)

    df_asset = pd.concat(assets, axis=1)
    df_profit = pd.concat(profits, axis=1)
    df_profit_rate = pd.concat(profit_rates, axis=1)

    # print(df_profit)

    df_asset = convert_data(df_asset)
    df_profit = convert_data(df_profit)
    df_profit_rate = convert_data(df_profit_rate)

    # print(df_profit)

    return df_asset, df_profit, df_profit_rate
