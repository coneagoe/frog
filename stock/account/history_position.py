import logging
import os

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from fund.data import get_fund_name
from stock.data import get_stock_name

from ..common import get_stock_position_path
from ..const import (
    COL_DATE,
    COL_MARKET_VALUE,
    COL_PROFIT,
    COL_PROFIT_RATE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
)

# pd.set_option('display.max_rows', None)


# def check_stock_id(df):
#     if not pattern_valid_stock_id.match(df[COL_STOCK_ID]):
#         logging.error(f"Invalid stock id: {df[COL_STOCK_ID]}")
#         exit(-1)


def fetch_name(df: pd.DataFrame):
    name = get_stock_name(df[COL_STOCK_ID])
    if name:
        return name

    name = get_fund_name(df[COL_STOCK_ID])
    if name:
        return name

    return df[COL_STOCK_NAME]


def convert_data(df: pd.DataFrame) -> pd.DataFrame:
    # df[COL_STOCK_NAME] = df.apply(fetch_name, axis=1)
    # df = df.set_index(COL_STOCK_NAME)
    # df = df.drop(columns=[COL_STOCK_ID])

    df = df.sort_index()
    df = df.T
    logging.debug(df)
    # df.columns = df.iloc[0]
    # df = df.drop(df.index[0])
    df.rename_axis(COL_DATE, inplace=True)
    df.index = pd.to_datetime(df.index)
    df = df.astype(float)

    logging.debug(df)

    return df


def load_history_position(position_path: str) -> pd.DataFrame | None:
    if not os.path.exists(position_path):
        logging.warning(f"file does not exist: {position_path}.")
        return None

    df = pd.read_csv(position_path)
    df = df.drop_duplicates()
    # df.apply(check_stock_id, axis=1)
    df[COL_STOCK_ID] = df[COL_STOCK_ID].astype(str)
    df[COL_STOCK_ID] = df[COL_STOCK_ID].str.zfill(6)
    df[COL_STOCK_NAME] = df.apply(fetch_name, axis=1)
    df = df.replace("--", np.nan)
    return df


def load_history_positions(
    start_date: str, end_date: str, stock_ids=tuple
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
        position_path = os.path.join(get_stock_position_path(), f"{date_stamp}.csv")
        df = load_history_position(position_path)
        if df is None:
            continue

        if stock_ids:
            df = df[df[COL_STOCK_ID].isin(stock_ids)]

        df0 = pd.DataFrame(
            {COL_STOCK_NAME: df[COL_STOCK_NAME], date_stamp: df[COL_MARKET_VALUE]}
        )
        df0 = df0.set_index(COL_STOCK_NAME)
        assets.append(df0)

        df0 = pd.DataFrame(
            {COL_STOCK_NAME: df[COL_STOCK_NAME], date_stamp: df[COL_PROFIT]}
        )
        df0 = df0.set_index(COL_STOCK_NAME)
        profits.append(df0)

        df0 = pd.DataFrame(
            {COL_STOCK_NAME: df[COL_STOCK_NAME], date_stamp: df[COL_PROFIT_RATE]}
        )
        df0 = df0.set_index(COL_STOCK_NAME)
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
