from os.path import exists, join
import pandas as pd
from fund import *
import logging
import pandas_market_calendars as mcal


def convert_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.T
    df.columns = df.iloc[0]
    df = df.drop(df.index[0])
    df.rename_axis(col_date, inplace=True)
    df.index = pd.to_datetime(df.index)
    df = df.astype(float)
    # logging.debug(df)
    return df


def load_history_position(start_date: str, end_date: str) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    df_asset, df_profit, df_profit_rate = (None, None, None)

    market_calendar = mcal.get_calendar('XSHG')
    date_range = mcal.date_range(market_calendar.schedule(start_date, end_date), frequency='1D')
    j = 0
    for i in date_range:
        if j % 2 == 0:
            date_stamp = f"{i.year}-{str(i.month).zfill(2)}-{i.day}"
            position_path = join(get_fund_position_path(), f"{date_stamp}.csv")
            if not exists(position_path):
                logging.warning(f"file does not exist: {position_path}.")
                j += 1
                continue

            df = pd.read_csv(position_path)
            df[col_fund_id] = df[col_fund_id].astype(str)
            df[col_fund_id] = df[col_fund_id].str.zfill(6)
            df = df.set_index(col_fund_name)
            if df_asset is None:
                df_asset = pd.DataFrame({col_fund_name: df[col_fund_name],
                                         date_stamp: df[col_asset]})
                df_asset = df_asset.set_index(col_fund_name)
            else:
                df_asset[date_stamp] = df[col_asset]

            if df_profit is None:
                df_profit = pd.DataFrame({col_fund_name: df[col_fund_name],
                                          date_stamp: df[col_profit]})
                df_profit = df_profit.set_index(col_fund_name)
            else:
                df_profit[date_stamp] = df[col_profit]

            if df_profit_rate is None:
                df_profit_rate = pd.DataFrame({col_fund_name: df[col_fund_name],
                                               date_stamp: df[col_profit_rate]})
                df_profit_rate = df_profit_rate.set_index(col_fund_name)
            else:
                df_profit_rate[date_stamp] = df[col_profit_rate]

        j += 1

    df_asset = convert_data(df_asset)
    df_profit = convert_data(df_profit)
    df_profit_rate = convert_data(df_profit_rate)

    return df_asset, df_profit, df_profit_rate
