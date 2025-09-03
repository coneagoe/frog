import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from fund import get_fund_name, load_all_fund_general_info  # noqa: E402

conf.parse_config()


if __name__ == "__main__":
    df = load_all_fund_general_info()
    print(get_fund_name("000001"))
