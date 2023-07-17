# -*- coding: utf-8 -*-
import os.path
import sys
import time
from datetime import date, datetime
import pandas as pd
import swifter
import pandas_market_calendars as mcal
import conf
from stock import col_stock_id, col_current_price, fetch_close_price
from utility import send_email


col_reported = u'上报'
col_monitor_price = u'监控价格'


conf.config = conf.parse_config()

market_calendar = mcal.get_calendar('XSHG')
sleep_interval = 300


def is_market_open():
    today = date.today()
    start_date = today.strftime('%Y-%m-%d')
    end_date = (today + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    schedule = market_calendar.schedule(start_date=start_date, end_date=end_date)
    try:
        return market_calendar.open_at_time(schedule, pd.Timestamp.today())
    except ValueError:
        return False


def usage():
    print(f"{os.path.basename(__file__)} <stock.csv>")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage()
        exit()

    stock_csv = sys.argv[1]

    while True:
        if not is_market_open():
            print(f"{datetime.now()} market is not open")
            time.sleep(sleep_interval)
            continue

        df = pd.read_csv(stock_csv, encoding='GBK')
        df[col_stock_id] = df[col_stock_id].astype(str)
        df[col_stock_id] = df[col_stock_id].str.zfill(6)

        df0 = df[df[col_reported].isna()]
        df[col_current_price] = df0[col_stock_id].swifter.apply(fetch_close_price)

        df1 = df[df[col_reported].isna() & (df[col_monitor_price] >= df[col_current_price])]
        df.loc[df1.index, col_reported] = 1
        if not df1.empty:
            fallback_stock_output = f"fallback_stock_{date.today().strftime('%Y%m%d')}.csv"
            df1.to_csv(fallback_stock_output, encoding='GBK', index=False)
            send_email('fallback stock report', fallback_stock_output)

        df.to_csv(stock_csv, encoding='GBK', index=False)
        time.sleep(sleep_interval)
