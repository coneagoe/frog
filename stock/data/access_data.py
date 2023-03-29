import logging
import akshare as ak
from . access_general_info import get_stock_name, get_etf_name


def load_history_data(stock_id: str, start_date: str, end_date: str):
    stock_name = get_stock_name(stock_id)
    if stock_name:
        df = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust="")
        return stock_name, df

    etf_name = get_etf_name(stock_id)
    if etf_name:
        df = ak.fund_etf_hist_em(symbol=stock_id, period="daily",
                                 start_date=start_date, end_date=end_date,
                                 adjust="")
        return etf_name, df

    logging.warning(f"wrong stock id({stock_id}), please check.")
    return None, None
