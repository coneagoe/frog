import logging

import akshare as ak
import pandas as pd
import requests
import retrying
from bs4 import BeautifulSoup

from common.const import COL_DELISTING_DATE, COL_IPO_DATE, COL_STOCK_ID, COL_STOCK_NAME
from stock.common import get_stock_delisting_info_path

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

