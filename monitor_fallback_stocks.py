# -*- coding: utf-8 -*-
import os.path
import sys
import time
from datetime import date
import pandas as pd
import swifter
import pandas_market_calendars as mcal
import conf
from stock import col_stock_id, col_current_price, fetch_close_price, is_market_open
from utility import send_email


col_email = 'email'
col_monitor_price = u'监控价格'
sleep_interval = 300
stock_csv = 'fallback_stocks.csv'


conf.config = conf.parse_config()

market_calendar = mcal.get_calendar('XSHG')


if __name__ == '__main__':
    while True:
        if not is_market_open():
            time.sleep(sleep_interval)
            continue

        df = pd.read_csv(stock_csv, encoding='GBK')
        df[col_stock_id] = df[col_stock_id].astype(str)
        df[col_stock_id] = df[col_stock_id].str.zfill(6)

        df0 = df[df[col_email].isna()]
        df[col_current_price] = df0[col_stock_id].swifter.apply(fetch_close_price)

        df1 = df[df[col_email].isna() & (df[col_monitor_price] >= df[col_current_price])]
        if not df1.empty:
            df.loc[df1.index, col_email] = 1
            fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
            df1.to_csv(fallback_stock_output, encoding='GBK', index=False)
            send_email('fallback stock report', fallback_stock_output)

        df.to_csv(stock_csv, encoding='GBK', index=False)
        time.sleep(sleep_interval)
