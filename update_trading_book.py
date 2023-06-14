# -*- coding: utf-8 -*-
import logging
from datetime import date
import pandas as pd
import numpy as np
import swifter
from stock import *


col_ma_20 = u"20日均线"


conf.config = conf.parse_config()

trading_book_path = get_trading_book_path()
sheet_name_etf = u"ETF"
sheet_name_position = u"持仓"
sheet_name_stock = 'stock'

n = 360
end_date = date.today()
start_date = end_date - pd.Timedelta(days=n)
start_date_ts = start_date.strftime('%Y%m%d')
end_date_ts = end_date.strftime('%Y%m%d')

output_file_name = f"trading_book_{end_date_ts}.xlsx"
excel_writer = pd.ExcelWriter(output_file_name, engine='xlsxwriter')


def update_support_resistance(df: pd.DataFrame):
    df[[col_support, col_resistance]] = \
        df.swifter.apply(calculate_support_resistance, args=(start_date_ts, end_date_ts),
                         axis=1, result_type='expand')

    return df


def calculate_ma_20(df: pd.DataFrame):
    n = 40
    end_date = date.today()
    start_date = end_date - pd.Timedelta(days=n)
    start_date_ts = start_date.strftime('%Y%m%d')
    end_date_ts = end_date.strftime('%Y%m%d')
    df_history_data = load_history_data(df[col_stock_id], start_date_ts, end_date_ts)
    if df_history_data is not None:
        ma_20 = df_history_data[col_close].rolling(window=20).mean()
        return ma_20.iloc[-1]

    return np.nan


def update_stoploss(df: pd.DataFrame):
    df[col_current_price] = df[col_stock_id].swifter.apply(fetch_close_price)
    df[col_ma_20] = df.swifter.apply(calculate_ma_20, axis=1)

    return df


def update_current_price(df: pd.DataFrame):
    df[col_current_price] = df[col_stock_id].swifter.apply(fetch_close_price)

    filter_na = df[col_buy_count].isna()
    df.loc[filter_na, col_buying_price] = df.loc[filter_na, col_current_price]

    return df


df = pd.read_excel(trading_book_path, sheet_name=sheet_name_etf, dtype={col_stock_id: str})
df = update_current_price(df)
df.to_excel(excel_writer, sheet_name=sheet_name_etf)

df = pd.read_excel(trading_book_path, sheet_name=sheet_name_stock, dtype={col_stock_id: str})
df = update_current_price(df)
df = update_support_resistance(df)
df.to_excel(excel_writer, sheet_name=sheet_name_stock)

df = pd.read_excel(trading_book_path, sheet_name=sheet_name_position, dtype={col_stock_id: str})
df = update_stoploss(df)
df.to_excel(excel_writer, sheet_name=sheet_name_position)

excel_writer.close()
