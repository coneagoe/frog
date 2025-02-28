import logging
from datetime import date
import os
import sys
from tqdm import tqdm
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf
# import pandas as pd
# import pandas_market_calendars as mcal
from stock import (
    load_all_hk_ggt_stock_general_info,
    download_history_data_stock_hk,
    COL_STOCK_ID,
)


conf.parse_config()


# def get_latest_trading_day():
#     cal = mcal.get_calendar("XSHG")
#     today = pd.Timestamp.now(tz="Asia/Shanghai").normalize()
#     schedule = cal.schedule(start_date=today - pd.Timedelta(days=7),
#                             end_date=today + pd.Timedelta(days=7))
#     if today in schedule.index:
#         return today.strftime('%Y-%m-%d')
# 
#     prev_day = schedule.index[schedule.index < today][-1]
#     next_day = schedule.index[schedule.index > today][0]
#     dist_prev = abs((today - prev_day).days)
#     dist_next = abs((next_day - today).days)
#     return prev_day.strftime('%Y-%m-%d') if dist_prev <= dist_next else next_day.strftime('%Y-%m-%d')


def download_all_hk_ggt_stock_data(period: str = 'daily', adjust: str = 'qfq'):
    start_date = '2010-01-01'
    end_date = date.today().strftime('%Y-%m-%d')

    hk_ggt_stocks_df = load_all_hk_ggt_stock_general_info()
    
    stock_ids = hk_ggt_stocks_df[COL_STOCK_ID].tolist()
    
    for stock_id in tqdm(stock_ids, desc="Downloading HK GGT stock data"):
        try:
            download_history_data_stock_hk(stock_id, period, start_date, end_date, adjust)
        except Exception as e:
            logging.warning(f"Failed to download data for stock {stock_id}: {e}")


if __name__ == "__main__":
    download_all_hk_ggt_stock_data(period='daily', adjust='qfq')
