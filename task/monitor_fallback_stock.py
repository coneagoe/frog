# -*- coding: utf-8 -*-
from datetime import date, datetime
from celery_app import app
import pandas as pd

from stock import (
    COL_STOCK_ID, COL_STOCK_NAME, COL_CURRENT_PRICE,
    COL_MONITOR_PRICE, COL_COMMENT,
    fetch_close_price, is_a_market_open_today, get_yesterday_ma
)
from utility import send_email

col_period = 'period'
stock_csv = 'fallback_stocks.csv'


@app.task
def monitor_fallback_stock(test=False):
    """
    Celery task to monitor fallback stocks from a CSV file.
    """
    if not test and not is_a_market_open_today():
        return "Not a market open day. Skipping."

    current_time = datetime.now().strftime('%H:%M')
    if not (current_time >= '09:30' and current_time <= '15:00'):
        return f"{current_time} market is not open. Skipping."

    try:
        df = pd.read_csv(stock_csv, encoding='GBK')
    except FileNotFoundError:
        return

    df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].swifter.apply(fetch_close_price)

    df_tmp = df.copy()

    df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(str)
    df0 = df_tmp[df_tmp[COL_MONITOR_PRICE].str.contains('ma')]
    if not df0.empty:
        df0[col_period] = \
            df0[COL_MONITOR_PRICE].str.extract(r'ma(\d+)').astype(int)

        df0[COL_MONITOR_PRICE] = \
            df0.apply(lambda row: get_yesterday_ma(row[COL_STOCK_ID], row[col_period]),
                      axis=1)

        df_tmp.loc[df0.index, COL_MONITOR_PRICE] = df0[COL_MONITOR_PRICE]

    df_tmp[COL_MONITOR_PRICE] = pd.to_numeric(df_tmp[COL_MONITOR_PRICE], errors='coerce')
    df_tmp.dropna(subset=[COL_MONITOR_PRICE], inplace=True)


    df_output = df_tmp[df_tmp[COL_MONITOR_PRICE] >= df_tmp[COL_CURRENT_PRICE]]

    if not df_output.empty:
        fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
        df_output_final = df_output.loc[:, [COL_STOCK_ID, COL_STOCK_NAME,
                                      COL_MONITOR_PRICE, COL_CURRENT_PRICE,
                                      COL_COMMENT]]
        df_output_final.to_csv(fallback_stock_output, encoding='GBK', index=False)
        if test:
            print(df_output_final)
        else:
            send_email('fallback stock report', fallback_stock_output)
        return f"Fallback stock report generated: {fallback_stock_output}"
    
    return "No stocks met the fallback criteria."

