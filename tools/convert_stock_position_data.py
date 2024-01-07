"""
This script is to convert the stock name or fund name as a full name
 according to the stock general info and fund general info.
"""

from os import walk
from os.path import join
# import logging
from fund import get_fund_name
from stock import (
    get_stock_name,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    get_stock_position_path,
    load_history_position
)
import conf


conf.parse_config()


def fetch_name(df):
    name = get_stock_name(df[COL_STOCK_ID])
    if name:
        return name

    name = get_fund_name(df[COL_STOCK_ID])
    if name:
        return name

    return df[COL_STOCK_NAME]


if __name__ == "__main__":
    filenames = next(walk(get_stock_position_path()), (None, None, []))[2]

    for i in filenames:
        file_path = join(get_stock_position_path(), i)
        df = load_history_position(file_path)
        # print(df)
        df.to_csv(file_path, encoding='utf_8_sig', index=False)
