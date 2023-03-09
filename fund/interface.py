from os.path import exists
import logging
# import asyncio
import pandas as pd
from fund import get_fund_general_info_path, col_fund_id, col_fund_name
# from utility import *


def get_all_fund_general_info():
    fund_general_info_path = get_fund_general_info_path()
    # if not exists(fund_general_info_path) or \
    #         is_older_than_a_month(fund_general_info_path):
    #     ttc = TianTianCrawler()
    #     loop = asyncio.get_event_loop()
    #     loop.run_until_complete(ttc.download_all_fund_general_info())

    if not exists(fund_general_info_path):
        logging.error(f"No {fund_general_info_path}")
        return None

    df = pd.read_csv(fund_general_info_path)
    df[col_fund_id] = df[col_fund_id].astype(str)
    df[col_fund_id] = df[col_fund_id].str.zfill(6)
    return df


def get_fund_name(df: pd.DataFrame, fund_id: str):
    """
    :param df: all fund general info
    :param fund_id:
    :return:
    """
    df = df.set_index(col_fund_id)
    return df.at[fund_id, col_fund_name]
