from stock import *
import conf
from utility import *


stocks_general_info = None


if __name__ == '__main__':
    conf.config = conf.parse_config()
    if is_older_than_a_week(get_stock_general_info_path()):
        download_general_info_stock()
