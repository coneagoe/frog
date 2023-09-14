# -*- coding: utf-8 -*-
import time
from datetime import date
import pandas as pd
import swifter
import pandas_market_calendars as mcal
import conf
from stock import col_stock_id, col_stock_name, col_current_price, \
    fetch_close_price, is_market_open, calculate_ma
from utility import send_email


test = False

col_email = 'email'
col_monitor_price = u'监控价格'
col_comment = 'comment'
col_period = 'period'

sleep_interval = 300
stock_csv = 'fallback_stocks.csv'


conf.config = conf.parse_config()

market_calendar = mcal.get_calendar('XSHG')


if __name__ == '__main__':
    while True:
        if not test:
            if not is_market_open():
                time.sleep(sleep_interval)
                continue

        df = pd.read_csv(stock_csv, encoding='GBK')
        df[col_stock_id] = df[col_stock_id].astype(str)
        df[col_stock_id] = df[col_stock_id].str.zfill(6)

        df[col_current_price] = df[col_stock_id].swifter.apply(fetch_close_price)

        df_tmp = df.copy()

        df_tmp[col_monitor_price] = df_tmp[col_monitor_price].astype(str)
        df0 = df_tmp[df_tmp[col_monitor_price].str.contains('ma')]
        if not df0.empty:
            df0[col_period] = \
                df0[col_monitor_price].str.extract('ma(\d+)').astype(int)

            df0[col_monitor_price] = \
                df0.apply(lambda row: calculate_ma(row[col_stock_id],
                                                   row[col_period]), axis=1)

            df_tmp.loc[df0.index, col_monitor_price] = df0[col_monitor_price]

        df_tmp[col_monitor_price] = df_tmp[col_monitor_price].astype(float)

        df_output = df_tmp[df_tmp[col_email].isna() &
                           (df_tmp[col_monitor_price] >= df_tmp[col_current_price])]

        if not df_output.empty:
            df.loc[df_output.index, col_email] = 1
            fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
            df_output = df_output.loc[:, [col_stock_id, col_stock_name,
                                          col_monitor_price, col_current_price, col_comment]]
            df_output.to_csv(fallback_stock_output, encoding='GBK', index=False)
            if test:
                print(df_output)
            else:
                send_email('fallback stock report', fallback_stock_output)

        df.to_csv(stock_csv, encoding='GBK', index=False)

        if test:
            break

        time.sleep(sleep_interval)

