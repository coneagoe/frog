import logging
import akshare as ak
import pandas as pd
from . access_general_info import get_stock_name, get_etf_name
from stock.common import *


def load_history_data(stock_id: str, start_date: str, end_date: str):
    stock_name = get_stock_name(stock_id)
    if stock_name:
        df = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust="")
        return stock_name, df

    etf_name = get_etf_name(stock_id)
    if etf_name:
        try:
            df = ak.fund_etf_hist_em(symbol=stock_id, period="daily",
                                     start_date=start_date, end_date=end_date,
                                     adjust="")
            return etf_name, df
        except KeyError:
            df = ak.fund_money_fund_info_em(stock_id)
            start_timestamp = pd.Timestamp(start_date)
            end_timestamp = pd.Timestamp(end_date)
            df[u'净值日期'] = pd.to_datetime(df[u'净值日期'])
            df = df[(df[u'净值日期'] >= start_timestamp) & (df[u'净值日期'] <= end_timestamp)]
            df = df.rename(columns={'净值日期': col_date, '每万份收益': col_close})
            df[col_close] = df[col_close].astype(float)
            df = df.set_index(col_date)
            df = df.sort_index(ascending=True)
            df = df.reset_index()

            return etf_name, df

    logging.warning(f"wrong stock id({stock_id}), please check.")
    return None, None
