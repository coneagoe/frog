"""
This script is to convert the fund name as a full name according to the fund general info.
"""

from os import walk
from os.path import join
import logging
from fund import *
import conf


conf.config = conf.parse_config()

all_general_info = get_all_fund_general_info()


def fetch_fund_name(df):
    return get_fund_name(all_general_info, df[col_fund_id])


if __name__ == "__main__":
    filenames = next(walk(get_fund_position_path()), (None, None, []))[2]

    for i in filenames:
        file_path = join(get_fund_position_path(), i)
        df = pd.read_csv(file_path)
        df[col_fund_id] = df[col_fund_id].astype(str)
        df[col_fund_id] = df[col_fund_id].str.zfill(6)
        df[col_fund_name] = df.apply(fetch_fund_name, axis=1)
        df.to_csv(file_path, encoding='utf_8_sig', index=False)
