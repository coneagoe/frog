# -*- coding: utf-8 -*-
from pathlib import Path
from os.path import join, exists
import logging
import conf


general_info_file_name = 'general_info.csv'
trading_book_name = "trading book.xlsm"

# column name
col_stock_id = u'股票代码'
col_stock_name = u'股票名称'
col_position = u'持仓'
col_position_available = u'可用'
col_market_value = u'市值'
col_current_price = u'现价'
col_cost = u'成本'
col_profit = u'浮动盈亏'
col_profit_rate = u'盈亏(%)'
col_date = u'日期'
col_close = u'收盘'


def get_stock_data_path() -> Path:
    path = Path(conf.config['stock']['data_path'])
    if not path.exists():
        path.mkdir(parents=True)

    return path


def _get_stock_data_path(subdir: str) -> Path:
    path = Path(join(conf.config['stock']['data_path'], subdir))
    if not path.exists():
        path.mkdir(parents=True)

    return path


def get_stock_position_path() -> Path:
    return _get_stock_data_path('position')


def get_stock_general_info_path() -> str:
    return join(_get_stock_data_path('info'), general_info_file_name)


def get_stock_history_path() -> Path:
    return _get_stock_data_path('history')


def get_trading_book_path():
    trading_book_path = join(get_stock_data_path(), trading_book_name)
    if not exists(trading_book_path):
        logging.warning(f"{trading_book_path} does not exist.")
        exit()

    return trading_book_path
