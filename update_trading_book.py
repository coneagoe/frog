# -*- coding: utf-8 -*-
import logging
from datetime import date
import pandas as pd
import numpy as np
import swifter
from stock import *


conf.config = conf.parse_config()

trading_book_path = get_trading_book_path()
sheet_names = [u"交易计划(1d)", u"持仓"]
output_book_name = "tmp.xlsx"

excel_writer = pd.ExcelWriter(output_book_name, engine='xlsxwriter')

n = 360
end_date = date.today()
start_date = end_date - pd.Timedelta(days=n)
start_date_ts = start_date.strftime('%Y%m%d')
end_date_ts = end_date.strftime('%Y%m%d')


def update_support_resistance(df: pd.DataFrame):
    df[col_current_price] = df[col_stock_id].swifter.apply(fetch_close_price)

    filter_na = df[col_buy_count].isna()
    df.loc[filter_na, col_buying_price] = df.loc[filter_na, col_current_price]

    df[[col_support, col_resistance]] = \
        df.swifter.apply(calculate_support_resistance, args=(start_date_ts, end_date_ts),
                         axis=1, result_type='expand')

    return df


for sheet_name in sheet_names:
    df = pd.read_excel(trading_book_path, sheet_name=sheet_name, dtype={col_stock_id: str})
    df = update_support_resistance(df)
    df.to_excel(excel_writer, sheet_name=sheet_name)

excel_writer.close()
