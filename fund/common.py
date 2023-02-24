# -*- coding: utf-8 -*-
from pathlib import Path
import os
import conf


# path
fund_data_path = 'data/fund'
all_general_info_csv = 'data/fund/all_general_info.csv'

# column name
col_fund_id = '基金代号'
col_fund_name = '基金名'
col_asset = '资产'
col_yesterday_earning = '昨日收益'
col_position_income = '持仓收益'
col_position_yield = '持仓收益率(%)'
col_pinyin = '拼音'
col_pinyin_abbreviation = '拼音缩写'
col_fund_type = '基金类型'


def get_fund_data_path(subdir: str) -> str:
    path = Path(os.path.join(conf.config['fund']['data_path'], subdir))
    if not path.exists():
        path.mkdir(parents=True)

    return str(path)


def get_fund_history_path() -> str:
    return get_fund_data_path('history_netvalue')


def get_fund_position_path() -> str:
    return get_fund_data_path('position')
