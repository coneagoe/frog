from os.path import exists
import logging
import pandas as pd
from fund import get_fund_general_info_path, col_fund_id, col_fund_name


g_df_funds = None


def load_all_fund_general_info():
    global g_df_funds
    if g_df_funds is not None:
        return g_df_funds

    fund_general_info_path = get_fund_general_info_path()
    if not exists(fund_general_info_path):
        logging.error(f"No {fund_general_info_path}")
        return None

    g_df_funds = pd.read_csv(fund_general_info_path)
    g_df_funds[col_fund_id] = g_df_funds[col_fund_id].astype(str)
    g_df_funds[col_fund_id] = g_df_funds[col_fund_id].str.zfill(6)
    return g_df_funds


def get_fund_name(fund_id: str):
    """
    :param df: all fund general info
    :param fund_id:
    :return:
    """
    global g_df_funds

    if g_df_funds is None:
        g_df_funds = load_all_fund_general_info()

    try:
        return g_df_funds.loc[g_df_funds[col_fund_id] == fund_id][col_fund_name].iloc[0]
    except IndexError:
        return None
