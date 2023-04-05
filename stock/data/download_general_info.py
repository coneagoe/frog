import akshare as ak
from stock.common import *


pattern_stock_id = r'60|00|30|68'


# TODO
def is_st(stock_id: str):
    pass


def download_general_info_stock():
    df = ak.stock_info_a_code_name()
    df = df.loc[df['code'].str.match(pattern_stock_id)]
    df = df.rename(columns={'code': col_stock_id, 'name': col_stock_name})
    df.to_csv(get_stock_general_info_path(), encoding='utf_8_sig', index=False)


def download_general_info_etf():
    df = ak.fund_name_em()
    df.to_csv(get_etf_general_info_path(), encoding='utf_8_sig', index=False)
