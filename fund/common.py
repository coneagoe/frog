# -*- coding: utf-8 -*-
from pathlib import Path
import os
from os.path import join


fund_general_info_file_name = 'fund_general_info.csv'

# column name
COL_FUND_ID = u'基金代号'
COL_FUND_NAME = u'基金名'
COL_ASSET = u'资产'
COL_YESTERDAY_EARNING = u'昨日收益'
COL_PROFIT = u'持仓收益'
COL_PROFIT_RATE = u'持仓收益率(%)'
COL_PINYIN = u'拼音'
COL_PINYIN_ABBREVIATION = u'拼音缩写'
COL_FUND_TYPE = u'基金类型'
COL_DATE = u'日期'


def get_fund_data_path(subdir: str) -> str:
    path = Path(join(os.environ['fund_data_path'], subdir))
    if not path.exists():
        path.mkdir(parents=True)

    return str(path)


def get_fund_history_path() -> str:
    return get_fund_data_path('history_netvalue')


def get_fund_position_path() -> str:
    return get_fund_data_path('position')


def get_fund_general_info_path() -> str:
    return join(get_fund_data_path('info'), fund_general_info_file_name)
