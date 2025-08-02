# -*- coding: utf-8 -*-
import os
from os.path import join
from pathlib import Path

fund_general_info_file_name = "fund_general_info.csv"

# column name
COL_FUND_ID = "fund_id"
COL_FUND_NAME = "fund_name"
COL_ASSET = "资产"
COL_YESTERDAY_EARNING = "昨日收益"
COL_PROFIT = "持仓收益"
COL_PROFIT_RATE = "持仓收益率(%)"
COL_PINYIN = "拼音"
COL_PINYIN_ABBREVIATION = "拼音缩写"
COL_FUND_TYPE = "基金类型"
COL_DATE = "日期"


def get_fund_data_path(subdir: str) -> str:
    path = Path(join(os.environ["fund_data_path"], subdir))
    if not path.exists():
        path.mkdir(parents=True)

    return str(path)


def get_fund_history_path() -> str:
    return get_fund_data_path("history_netvalue")


def get_fund_position_path() -> str:
    return get_fund_data_path("position")


def get_fund_general_info_path() -> str:
    return join(get_fund_data_path("info"), fund_general_info_file_name)
