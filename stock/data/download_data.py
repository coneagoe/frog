import logging
import os
from datetime import datetime

import akshare as ak
import baostock as bs
import pandas as pd
import requests
import retrying
from bs4 import BeautifulSoup

from stock.common import (
    get_stock_300_ingredients_path,
    get_stock_500_ingredients_path,
    get_stock_delisting_info_path,
)
from stock.const import COL_DELISTING_DATE, COL_IPO_DATE, COL_STOCK_ID, COL_STOCK_NAME

pattern_stock_id = r"60|00|30|68"


# TODO
# def is_st(stock_id: str):
#     pass


def download_delisted_stock_info():
    df = ak.stock_info_sh_delist(symbol="全部")
    df.columns = [COL_STOCK_ID, COL_STOCK_NAME, COL_IPO_DATE, COL_DELISTING_DATE]

    df0 = ak.stock_info_sz_delist(symbol="终止上市公司")
    df0.columns = [COL_STOCK_ID, COL_STOCK_NAME, COL_IPO_DATE, COL_DELISTING_DATE]

    df = pd.concat([df, df0])
    df.to_csv(get_stock_delisting_info_path(), encoding="utf_8_sig", index=False)


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
def download_general_info_index():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:107.0) Gecko/20100101 Firefox/107.0"  # noqa: E501
    }

    url = "http://quote.eastmoney.com/center/gridlist.html#index_sh"

    try:
        resp = requests.get(url, headers=headers)
    except requests.exceptions.ConnectionError as e:
        logging.error(e.args)
        raise e

    if resp.status_code != requests.codes.ok:
        logging.error(f"download index fail: {resp.status_code}")
        return False

    bs = BeautifulSoup(resp.content, "lxml")
    print(bs.prettify())

    # df.to_csv(get_stock_general_info_path(), encoding='utf_8_sig', index=False)


def download_baostock_ingredients(query_func, path_func):
    start_date = datetime(2010, 1, 1)
    end_date = datetime.today()

    lg = bs.login()
    if lg.error_code != "0":
        logging.error(f"baostock login fail: {lg.error_msg}")
        return

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        file_path = os.path.join(path_func(), f"{date_str}.csv")
        if not os.path.exists(file_path):
            rs = query_func(date=date_str)
            rows = []
            while rs.next():
                if rs.error_code != "0":
                    logging.error(f"query fail({rs.error_code}): {rs.error_msg}")
                    exit(1)

                rows.append(rs.get_row_data())

            # while (rs.error_code == '0') & rs.next():
            #     rows.append(rs.get_row_data())

            df = pd.DataFrame(rows, columns=rs.fields)
            df.rename(
                columns={"code": COL_STOCK_ID, "code_name": COL_STOCK_NAME},
                inplace=True,
            )
            df[COL_STOCK_ID] = (
                df[COL_STOCK_ID].str.replace("sh.", "").str.replace("sz.", "")
            )
            df.to_csv(file_path, encoding="utf_8_sig", index=False)

        if current_date.month == 1 and current_date.day == 1:
            current_date = datetime(current_date.year, 7, 1)
        else:
            current_date = datetime(current_date.year + 1, 1, 1)

    bs.logout()


def download_300_ingredients():
    download_baostock_ingredients(bs.query_hs300_stocks, get_stock_300_ingredients_path)


def download_500_ingredients():
    download_baostock_ingredients(bs.query_zz500_stocks, get_stock_500_ingredients_path)


# 新的基于架构的便捷函数
def download_stock_with_timescale(stock_id: str, period: str = "daily", start_date: str = "20200101", end_date: str = "20231231", adjust: str = "qfq"):
    """使用TimescaleDB下载股票数据的便捷函数"""
    from .factory import download_stock_data_with_timescale
    return download_stock_data_with_timescale(stock_id, period, start_date, end_date, adjust)


def download_etf_with_timescale(etf_id: str, period: str = "daily", start_date: str = "20200101", end_date: str = "20231231", adjust: str = "qfq"):
    """使用TimescaleDB下载ETF数据的便捷函数"""
    from .factory import create_download_manager
    manager = create_download_manager(storage_type="timescale")
    return manager.download_and_save_etf_data(etf_id, period, start_date, end_date, adjust)


def download_hk_stock_with_timescale(stock_id: str, period: str = "daily", start_date: str = "2020-01-01", end_date: str = "2023-12-31", adjust: str = "hfq"):
    """使用TimescaleDB下载港股数据的便捷函数"""
    from .factory import create_download_manager
    manager = create_download_manager(storage_type="timescale")
    return manager.download_and_save_hk_stock_data(stock_id, period, start_date, end_date, adjust)


def download_general_info_with_storage(info_type: str, storage_type: str = "csv", **kwargs):
    """使用指定存储方式下载基本信息的便捷函数"""
    from .factory import create_download_manager
    manager = create_download_manager(storage_type=storage_type, **kwargs)
    return manager.download_and_save_general_info(info_type)
