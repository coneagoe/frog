# -*- coding: utf-8 -*-
from datetime import date
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd     # noqa: E402
import numpy as np      # noqa: E402

import conf    # noqa: E402
from stock import (
    get_trading_book_path,
    COL_STOCK_ID,
    COL_CLOSE,
    COL_SUPPORT,
    COL_RESISTANCE,
    load_history_data,
    get_support_resistance
)   # noqa: E402


sheet_names = [u"交易计划(1d)", u"持仓"]
OUTPUT_BOOK_NAME = "tmp.xlsx"


conf.parse_config()

trading_book_path = get_trading_book_path()

excel_writer = pd.ExcelWriter(OUTPUT_BOOK_NAME, engine='xlsxwriter')

n = 360
end_date = date.today()
start_date = end_date - pd.Timedelta(days=n)
start_date = start_date.strftime('%Y%m%d')
end_date = end_date.strftime('%Y%m%d')

for sheet_name in sheet_names:
    df = pd.read_excel(trading_book_path, sheet_name=sheet_name, dtype={COL_STOCK_ID: str})
    security_ids = df[COL_STOCK_ID]
    supports = []
    resistances = []
    for index, security_id in security_ids.items():
        stock_name, df_history_data = load_history_data(security_id, start_date, end_date)
        # turning_points, support_point, resistance_point = get_support_resistance(df)
        if stock_name:
            turning_points, support_point, resistance_point = get_support_resistance(df_history_data)
            if support_point:
                support_point = df_history_data[COL_CLOSE][support_point]

            if resistance_point:
                resistance_point = df_history_data[COL_CLOSE][resistance_point]
        else:
            support_point = np.nan
            resistance_point = np.nan

        supports.append(support_point)
        resistances.append(resistance_point)

    series_supports = pd.Series(supports, name=COL_SUPPORT)
    series_resistances = pd.Series(resistances, name=COL_RESISTANCE)

    df.update(series_supports)
    df.update(series_resistances)

    df.to_excel(excel_writer, sheet_name=sheet_name)

excel_writer.close()
