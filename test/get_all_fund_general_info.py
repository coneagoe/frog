import conf
from fund import *


conf.config = conf.parse_config()


if __name__ == '__main__':
    df = get_all_fund_general_info()
    print(get_fund_name(df, '000001'))
