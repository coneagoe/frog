# -*- coding: utf-8 -*-
import logging
import pandas as pd
import numpy as np
from datetime import date
import conf
from stock import *


sheet_names = [u"交易计划(1d)", u"持仓"]
output_book_name = "tmp.xlsx"


conf.config = conf.parse_config()

trading_book_path = get_trading_book_path()

excel_writer = pd.ExcelWriter(output_book_name, engine='xlsxwriter')

n = 360
end_date = date.today()
start_date = end_date - pd.Timedelta(days=n)
start_date = start_date.strftime('%Y%m%d')
end_date = end_date.strftime('%Y%m%d')


for sheet_name in sheet_names:
    df = pd.read_excel(trading_book_path, sheet_name=sheet_name, dtype={col_stock_id: str})
    security_ids = df[col_stock_id]
    current_prices = []
    supports = []
    resistances = []
    for index, security_id in security_ids.items():
        current_prices.append(fetch_close_price(security_id))

        stock_name, df_history_data = load_history_data(security_id, start_date, end_date)
        if stock_name:
            turning_points, support_point, resistance_point = get_support_resistance(df_history_data)
            if support_point:
                support_point = df_history_data[col_close][support_point]

            if resistance_point:
                resistance_point = df_history_data[col_close][resistance_point]
        else:
            support_point = np.nan
            resistance_point = np.nan

        supports.append(support_point)
        resistances.append(resistance_point)

    series_prices = pd.Series(current_prices, name=col_current_price)
    df.update(series_prices)

    filter_na = df[col_buy_count].isna()
    df.loc[filter_na, col_buying_price] = df.loc[filter_na, col_current_price]

    series_supports = pd.Series(supports, name=col_support)
    df.update(series_supports)

    series_resistances = pd.Series(resistances, name=col_resistance)
    df.update(series_resistances)

    df.to_excel(excel_writer, sheet_name=sheet_name)

excel_writer.close()
