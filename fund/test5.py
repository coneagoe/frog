# -*- coding: utf-8 -*-

import pandas_market_calendars as mcal
import numpy as np
from datetime import datetime

# import akshare as ak

market = mcal.get_calendar('XSHG')
holidays = list(market.holidays().holidays)

start_date = '2021-01-01'
end_date = '2022-01-01'
sdate = datetime.strptime(start_date, '%Y-%m-%d')
edate = datetime.strptime(end_date, '%Y-%m-%d')
days = np.busday_count(sdate.date(), edate.date(), holidays=holidays)
print(days)
