from stock import *
import conf
from utility import *
import os


stocks_general_info = None


if __name__ == '__main__':
    conf.config = conf.parse_config()
    if is_older_than_n_days(os.path.join(get_stock_general_info_path(), )):
        download_stock_general_info()
