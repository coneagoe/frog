import logging
import os

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from fund.common import (
    COL_ASSET,
    COL_DATE,
    COL_FUND_ID,
    COL_FUND_NAME,
    COL_PROFIT,
    COL_PROFIT_RATE,
    get_fund_position_path,
)
from fund.data.general_info import get_fund_name


def fetch_fund_name(df):
    return get_fund_name(df[COL_FUND_ID])


def convert_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.T
    df.rename_axis(COL_DATE, inplace=True)
    df.index = pd.to_datetime(df.index)
    df = df.astype(float)
    return df


def load_history_position(position_path: str):
    if not os.path.exists(position_path):
        logging.warning(f"file does not exist: {position_path}.")
        return None

    df = pd.read_csv(position_path)
    df = df.drop_duplicates()
    df[COL_FUND_ID] = df[COL_FUND_ID].astype(str)
    df[COL_FUND_ID] = df[COL_FUND_ID].str.zfill(6)
    df[COL_FUND_NAME] = df.apply(fetch_fund_name, axis=1)
    df = df.replace("--", np.nan)
    return df


def load_history_positions(
    start_date: str, end_date: str, fund_ids=tuple
) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    assets, profits, profit_rates = ([], [], [])

    market_calendar = mcal.get_calendar("XSHG")
    date_range = mcal.date_range(
        market_calendar.schedule(start_date, end_date), frequency="1D"
    )
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

        if fund_ids:
            df = df[df[COL_FUND_ID].isin(fund_ids)]

        df0 = pd.DataFrame(
            {COL_FUND_NAME: df[COL_FUND_NAME], date_stamp: df[COL_ASSET]}
        )
        df0 = df0.set_index(COL_FUND_NAME)
        assets.append(df0)

        df0 = pd.DataFrame(
            {COL_FUND_NAME: df[COL_FUND_NAME], date_stamp: df[COL_PROFIT]}
        )
        df0 = df0.set_index(COL_FUND_NAME)
        profits.append(df0)

        df0 = pd.DataFrame(
            {COL_FUND_NAME: df[COL_FUND_NAME], date_stamp: df[COL_PROFIT_RATE]}
        )
        df0 = df0.set_index(COL_FUND_NAME)
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
