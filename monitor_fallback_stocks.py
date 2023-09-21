# -*- coding: utf-8 -*-
import time
from datetime import date
import signal
import pandas as pd
import swifter
import sqlite3
import conf
from stock import col_stock_id, col_stock_name, col_current_price, \
    col_monitor_price, col_email, col_comment, col_mobile, col_pc, \
    fetch_close_price, is_market_open, get_yesterday_ma, database_name, \
    monitor_stock_table_name
from utility import send_email


test = False

col_period = 'period'

sleep_interval = 300
stock_csv = 'fallback_stocks.csv'

conn = sqlite3.connect(database_name)
cursor = conn.cursor()

conf.config = conf.parse_config()


def exit_handler():
    conn.close()


signal.signal(signal.SIGINT, exit_handler)
signal.signal(signal.SIGTERM, exit_handler)


if __name__ == '__main__':
    while True:
        if not test:
            if not is_market_open():
                time.sleep(sleep_interval)
                continue

        cursor.execute(f"SELECT * FROM {monitor_stock_table_name}")
        df = pd.DataFrame(cursor.fetchall(),
                          columns=[col_stock_id, col_stock_name,
                                   col_monitor_price, col_current_price,
                                   col_email, col_mobile, col_pc, col_comment])

        df[col_current_price] = df[col_stock_id].swifter.apply(fetch_close_price)

        df_tmp = df.copy()

        df_tmp[col_monitor_price] = df_tmp[col_monitor_price].astype(str)
        df0 = df_tmp[df_tmp[col_monitor_price].str.contains('ma')]
        if not df0.empty:
            df0[col_period] = \
                df0[col_monitor_price].str.extract('ma(\d+)').astype(int)

            df0[col_monitor_price] = \
                df0.swifter.apply(lambda row: get_yesterday_ma(row[col_stock_id],
                                                               row[col_period]),
                                  axis=1)

            df_tmp.loc[df0.index, col_monitor_price] = df0[col_monitor_price]

        df_tmp[col_monitor_price] = df_tmp[col_monitor_price].astype(float)

        df_output = df_tmp[df_tmp[col_email].isna() &
                           (df_tmp[col_monitor_price] >= df_tmp[col_current_price])]

        if not df_output.empty:
            df.loc[df_output.index, col_email] = 1
            fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
            df_output = df_output.loc[:, [col_stock_id, col_stock_name,
                                          col_monitor_price, col_current_price,
                                          col_comment]]
            df_output.to_csv(fallback_stock_output, encoding='GBK', index=False)
            if test:
                print(df_output)
            else:
                send_email('fallback stock report', fallback_stock_output)

        df.to_sql(monitor_stock_table_name, conn, if_exists='replace', index=False)

        if test:
            break

        time.sleep(sleep_interval)
