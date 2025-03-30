# -*- coding: utf-8 -*-
from datetime import date, datetime
import functools
import logging
import os
import pandas as pd
import pandas_market_calendars as mcal


STOCK_GENERAL_INFO_FILE_NAME = 'stock_general_info.csv'
STOCK_DELISTING_INFO_FILE_NAME = 'stock_delisting_info.csv'
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
    return os.path.join(os.environ['stock_data_path_info'], STOCK_GENERAL_INFO_FILE_NAME)


def get_stock_delisting_info_path() -> str:
    return os.path.join(os.environ['stock_data_path_info'], STOCK_DELISTING_INFO_FILE_NAME)


def get_stock_300_ingredients_path() -> str:
    return os.environ['stock_data_path_300_ingredients']


def get_stock_500_ingredients_path() -> str:
    return os.environ['stock_data_path_500_ingredients']


def get_hk_ggt_stock_general_info_path() -> str:
    return os.path.join(os.environ['stock_data_path_info'], HK_GGT_STOCK_GENERAL_INFO_FILE_NAME)


def get_etf_general_info_path() -> str:
    return os.path.join(os.environ['stock_data_path_info'], ETF_GENERAL_INFO_FILE_NAME)


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
    return os.path.join(os.environ['stock_data_path'], TRADING_BOOK_NAME)


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


def get_last_trading_day() -> str:
    """
    Get the last trading day.
    If today is a trading day, return today.
    Otherwise, return the most recent trading day.
    
    Returns:
        str: Date in format 'YYYY-MM-DD'
    """
    cal = mcal.get_calendar('XSHG')
    
    today = datetime.now().strftime('%Y-%m-%d')
    today_date = datetime.strptime(today, '%Y-%m-%d')
    
    start_date = (today_date - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
    
    trading_days = cal.valid_days(start_date=start_date, end_date=today)
    
    trading_days_str = [d.strftime('%Y-%m-%d') for d in trading_days]
    
    if len(trading_days_str) == 0:
        logging.error("No trading day found")
        exit(1)

    if today in trading_days_str:
        return today
    else:
        return trading_days_str[-1]
