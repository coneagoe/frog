import os
import pandas as pd
from fund.common import *
from fund.data.general_info import get_fund_name
import logging
import pandas_market_calendars as mcal
import numpy as np


def fetch_fund_name(df):
    return get_fund_name(df[col_fund_id])


def convert_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.T
    df.rename_axis(col_date, inplace=True)
    df.index = pd.to_datetime(df.index)
    df = df.astype(float)
    return df


def load_history_position(position_path: str):
    if not os.path.exists(position_path):
        logging.warning(f"file does not exist: {position_path}.")
        return None

    df = pd.read_csv(position_path)
    df = df.drop_duplicates()
    df[col_fund_id] = df[col_fund_id].astype(str)
    df[col_fund_id] = df[col_fund_id].str.zfill(6)
    df[col_fund_name] = df.apply(fetch_fund_name, axis=1)
    df = df.replace('--', np.nan)
    return df


def load_history_positions(start_date: str, end_date: str, fund_id=None) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
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
        position_path = os.path.join(get_fund_position_path(), f"{date_stamp}.csv")
        df = load_history_position(position_path)
        if df is None:
            continue

        if fund_id is not None:
            df = df[df[col_fund_id] == fund_id]

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
