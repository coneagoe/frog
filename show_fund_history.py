import os
import sys
from conf import data_fund_path
import pandas_market_calendars as mcal
from datetime import datetime


market = mcal.get_calendar('XSHG')
holidays = list(market.holidays().holidays)

def usage():
    print(f"{os.path.basename(__file__)} <start_date> <end_date>")
    print("<start_date> <end_date>: yyyy-mm-dd")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        usage()
        exit()

    start_date, end_date = sys.argv[1], sys.argv[2]
    sdate = datetime.strptime(start_date, '%Y-%m-%d')
    edate = datetime.strptime(end_date, '%Y-%m-%d')
    days = np.busday_count(sdate.date(), edate.date(), holidays=holidays)
