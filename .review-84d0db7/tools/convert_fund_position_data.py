"""
This script is to convert the fund name as a full name
according to the fund general info.
"""

import os
import sys
from os import walk
from os.path import join

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from fund import get_fund_position_path, load_history_position  # noqa: E402

conf.parse_config()


if __name__ == "__main__":
    filenames = next(walk(get_fund_position_path()), (None, None, []))[2]

    for i in filenames:
        file_path = join(get_fund_position_path(), i)
        df = load_history_position(file_path)
        if df:
            df.to_csv(file_path, encoding="utf_8_sig", index=False)
