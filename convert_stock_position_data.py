"""
This script is to convert the stock name or fund name as a full name
 according to the stock general info and fund general info.
"""

from os import walk
from os.path import join
# import logging
from fund import *
from stock import *
import conf


conf.config = conf.parse_config()

all_fund_general_info = get_all_fund_general_info()

all_stock_general_info = get_all_stock_general_info()


def fetch_name(df):
    name = get_stock_name(all_stock_general_info, df[col_stock_id])
    if name:
        return name

    name = get_fund_name(all_fund_general_info, df[col_stock_id])
    if name:
        return name

    return df[col_stock_name]


if __name__ == "__main__":
    filenames = next(walk(get_stock_position_path()), (None, None, []))[2]

    for i in filenames:
        file_path = join(get_stock_position_path(), i)
        df = load_history_position(file_path)
        print(df)
        # df.to_csv(file_path, encoding='utf_8_sig', index=False)
