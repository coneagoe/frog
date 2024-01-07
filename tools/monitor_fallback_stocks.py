# -*- coding: utf-8 -*-
import time
from datetime import date
import signal
import pandas as pd
import swifter
import sqlite3
import conf
from stock import COL_STOCK_ID, COL_STOCK_NAME, COL_CURRENT_PRICE, \
    COL_MONITOR_PRICE, COL_EMAIL, COL_COMMENT, COL_MOBILE, COL_PC, \
    fetch_close_price, is_market_open, get_yesterday_ma, DATABASE_NAME, \
    monitor_stock_table_name
from utility import send_email


test = False

col_period = 'period'

sleep_interval = 300
stock_csv = 'fallback_stocks.csv'

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

conf.parse_config()


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
                          columns=[COL_STOCK_ID, COL_STOCK_NAME,
                                   COL_MONITOR_PRICE, COL_CURRENT_PRICE,
                                   COL_EMAIL, COL_MOBILE, COL_PC, COL_COMMENT])

        df[COL_CURRENT_PRICE] = df[COL_STOCK_ID].swifter.apply(fetch_close_price)

        df_tmp = df.copy()

        df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(str)
        df0 = df_tmp[df_tmp[COL_MONITOR_PRICE].str.contains('ma')]
        if not df0.empty:
            df0[col_period] = \
                df0[COL_MONITOR_PRICE].str.extract('ma(\d+)').astype(int)

            df0[COL_MONITOR_PRICE] = \
                df0.swifter.apply(lambda row: get_yesterday_ma(row[COL_STOCK_ID],
                                                               row[col_period]),
                                  axis=1)

            df_tmp.loc[df0.index, COL_MONITOR_PRICE] = df0[COL_MONITOR_PRICE]

        df_tmp[COL_MONITOR_PRICE] = df_tmp[COL_MONITOR_PRICE].astype(float)

        df_output = df_tmp[df_tmp[COL_EMAIL].isna() &
                           (df_tmp[COL_MONITOR_PRICE] >= df_tmp[COL_CURRENT_PRICE])]

        if not df_output.empty:
            df.loc[df_output.index, COL_EMAIL] = 1
            fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
            df_output = df_output.loc[:, [COL_STOCK_ID, COL_STOCK_NAME,
                                          COL_MONITOR_PRICE, COL_CURRENT_PRICE,
                                          COL_COMMENT]]
            df_output.to_csv(fallback_stock_output, encoding='GBK', index=False)
            if test:
                print(df_output)
            else:
                send_email('fallback stock report', fallback_stock_output)

        df.to_sql(monitor_stock_table_name, conn, if_exists='replace', index=False)

        if test:
            break

        time.sleep(sleep_interval)
