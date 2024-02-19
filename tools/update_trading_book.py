# -*- coding: utf-8 -*-
# import logging
from datetime import date
import os.path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd           # noqa: E402
import swifter                # noqa: E402

import conf                # noqa: E402
from stock import *        # noqa: E402


COL_MA_20 = u"20日均线"


conf.parse_config()

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
    df[[COL_SUPPORT, COL_RESISTANCE]] = \
        df.swifter.apply(calculate_support_resistance, args=(start_date_ts, end_date_ts),
                         axis=1, result_type='expand')

    return df


def update_stoploss(df: pd.DataFrame):
    df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].swifter.apply(fetch_close_price)
    df[COL_MA_20] = df[COL_STOCK_ID].swifter.apply(get_yesterday_ma, period=20)

    return df


def update_current_price(df: pd.DataFrame):
    df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].swifter.apply(fetch_close_price)

    filter_na = df[COL_BUY_COUNT].isna()
    df.loc[filter_na, COL_BUYING_PRICE] = df.loc[filter_na, COL_CURRENT_PRICE]

    return df


df = pd.read_excel(trading_book_path, sheet_name=sheet_name_etf, dtype={COL_STOCK_ID: str})
df = update_current_price(df)
df = update_support_resistance(df)
df.to_excel(excel_writer, sheet_name=sheet_name_etf)

df = pd.read_excel(trading_book_path, sheet_name=sheet_name_stock, dtype={COL_STOCK_ID: str})
df = update_current_price(df)
df = update_support_resistance(df)
df.to_excel(excel_writer, sheet_name=sheet_name_stock)

df = pd.read_excel(trading_book_path, sheet_name=sheet_name_position, dtype={COL_STOCK_ID: str})
df = update_stoploss(df)
df.to_excel(excel_writer, sheet_name=sheet_name_position)

excel_writer.close()
