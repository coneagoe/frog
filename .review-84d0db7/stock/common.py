# -*- coding: utf-8 -*-
import functools
import logging
import os

STOCK_GENERAL_INFO_FILE_NAME = "stock_general_info.csv"
STOCK_DELISTING_INFO_FILE_NAME = "stock_delisting_info.csv"
ETF_GENERAL_INFO_FILE_NAME = "etf_general_info.csv"
TRADING_BOOK_NAME = "trading book.xlsm"
HK_GGT_STOCK_GENERAL_INFO_FILE_NAME = "hk_ggt_stock_general_info.csv"


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
    return os.environ["stock_data_path"]


@check_path_exists
def get_stock_position_path() -> str:
    return os.environ["stock_data_path_position"]


def get_stock_general_info_path() -> str:
    return os.path.join(
        os.environ["stock_data_path_info"], STOCK_GENERAL_INFO_FILE_NAME
    )


def get_stock_delisting_info_path() -> str:
    return os.path.join(
        os.environ["stock_data_path_info"], STOCK_DELISTING_INFO_FILE_NAME
    )


def get_stock_300_ingredients_path() -> str:
    return os.environ["stock_data_path_300_ingredients"]


def get_stock_500_ingredients_path() -> str:
    return os.environ["stock_data_path_500_ingredients"]


def get_hk_ggt_stock_general_info_path() -> str:
    return os.path.join(
        os.environ["stock_data_path_info"], HK_GGT_STOCK_GENERAL_INFO_FILE_NAME
    )


def get_etf_general_info_path() -> str:
    return os.path.join(os.environ["stock_data_path_info"], ETF_GENERAL_INFO_FILE_NAME)


@check_path_exists
def get_stock_data_path_1d() -> str:
    return os.environ["stock_data_path_1d"]


@check_path_exists
def get_stock_data_path_1w() -> str:
    return os.environ["stock_data_path_1w"]


@check_path_exists
def get_stock_data_path_1M() -> str:
    return os.environ["stock_data_path_1M"]


@check_path_exists
def get_trading_book_path():
    return os.path.join(os.environ["stock_data_path"], TRADING_BOOK_NAME)
