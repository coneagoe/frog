# -*- coding: utf-8 -*-
from datetime import date, datetime
import functools
import logging
import os
from os.path import join, exists
from pathlib import Path


STOCK_GENERAL_INFO_FILE_NAME = 'stock_general_info.csv'
ETF_GENERAL_INFO_FILE_NAME = 'etf_general_info.csv'
TRADING_BOOK_NAME = 'trading book.xlsm'
HK_GGT_STOCK_GENERAL_INFO_FILE_NAME = 'hk_ggt_stock_general_info.csv'


def check_path_exists(func):
    @functools.wraps(func)
    def wrapper_check_path_exists(*args, **kwargs):
        path = func(*args, **kwargs)
        if not os.path.exists(path):
            logging.warning(f"{path} does not exist.")
            exit()
        return path
    return wrapper_check_path_exists


@check_path_exists
def get_stock_data_path() -> str:
    return os.environ['stock_data_path']


@check_path_exists
def get_stock_position_path() -> str:
    return os.environ['stock_data_path_position']


def get_stock_general_info_path() -> str:
    return join(os.environ['stock_data_path_info'], STOCK_GENERAL_INFO_FILE_NAME)


def get_hk_ggt_stock_general_info_path() -> str:
    return join(os.environ['stock_data_path_info'], HK_GGT_STOCK_GENERAL_INFO_FILE_NAME)


def get_etf_general_info_path() -> str:
    return join(os.environ['stock_data_path_info'], ETF_GENERAL_INFO_FILE_NAME)


@check_path_exists
def get_stock_data_path_1d() -> str:
    return os.environ['stock_data_path_1d']


@check_path_exists
def get_stock_data_path_1w() -> str:
    return os.environ['stock_data_path_1w']


@check_path_exists
def get_stock_data_path_1M() -> str:
    return os.environ['stock_data_path_1M']


@check_path_exists
def get_trading_book_path():
    return join(os.environ['stock_data_path'], TRADING_BOOK_NAME)


def is_testing():
    if os.getenv('TEST') in ['true', 'on', '1'] or \
            os.getenv('FROG_SERVER_CONFIG') in ['development', 'testing']:
        return True

    return False


def is_market_open():
    if is_testing():
        return True

    if date.today().weekday() >= 5:
        return False

    now = datetime.now()
    if (now.hour == 9 and now.minute >= 30) or (now.hour == 10) or \
            (now.hour == 11 and now.minute <= 30) or (now.hour == 13) or \
            (now.hour == 14) or (now.hour == 15 and now.minute <= 30):
        return True

    return False
