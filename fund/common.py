# -*- coding: utf-8 -*-
from pathlib import Path
from os.path import join
import conf


fund_general_info_file_name = 'fund_general_info.csv'

# column name
col_fund_id = u'基金代号'
col_fund_name = u'基金名'
col_asset = u'资产'
col_yesterday_earning = u'昨日收益'
col_profit = u'持仓收益'
col_profit_rate = u'持仓收益率(%)'
col_pinyin = u'拼音'
col_pinyin_abbreviation = u'拼音缩写'
col_fund_type = u'基金类型'
col_date = u'日期'


def get_fund_data_path(subdir: str) -> str:
    path = Path(join(conf.config['fund']['data_path'], subdir))
    if not path.exists():
        path.mkdir(parents=True)

    return str(path)


def get_fund_history_path() -> str:
    return get_fund_data_path('history_netvalue')


def get_fund_position_path() -> str:
    return get_fund_data_path('position')


def get_fund_general_info_path() -> str:
    return join(get_fund_data_path('info'), fund_general_info_file_name)
