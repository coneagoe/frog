# -*- coding: utf-8 -*-
from pathlib import Path
import os
from os.path import join, exists
import logging
from datetime import date, datetime
from . const import *


def get_stock_data_path() -> Path:
    path = Path(os.environ['stock_data_path'])
    if not path.exists():
        path.mkdir(parents=True)

    return path


def _get_stock_data_path(subdir: str) -> Path:
    path = Path(join(os.environ['stock_data_path'], subdir))
    if not path.exists():
        path.mkdir(parents=True)

    return path


def get_stock_position_path() -> Path:
    return _get_stock_data_path('position')


def get_stock_general_info_path() -> str:
    return join(_get_stock_data_path('info'), stock_general_info_file_name)


def get_etf_general_info_path() -> str:
    return join(_get_stock_data_path('info'), etf_general_info_file_name)


def get_stock_history_path() -> Path:
    return _get_stock_data_path('history')


def get_stock_1d_path():
    history_path = get_stock_history_path()
    _1d_path = join(history_path, '1d')
    if not exists(_1d_path):
        Path(_1d_path).mkdir(parents=True)

    return _1d_path


def get_trading_book_path():
    trading_book_path = join(get_stock_data_path(), trading_book_name)
    if not exists(trading_book_path):
        logging.warning(f"{trading_book_path} does not exist.")
        exit()

    return trading_book_path


def is_market_open():
    if date.today().weekday() >= 5:
        return False

    now = datetime.now()
    if (now.hour == 9 and now.minute >= 30) or (now.hour == 10) or \
            (now.hour == 11 and now.minute <= 30) or (now.hour == 13) or \
            (now.hour == 14) or (now.hour == 15 and now.minute <= 30):
        return True

    return False
