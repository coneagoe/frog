import conf
from stock import download_general_info_stock, get_stock_general_info_path
from utility import is_older_than_a_week

conf.parse_config()


stocks_general_info = None


if __name__ == "__main__":
    if is_older_than_a_week(get_stock_general_info_path()):
        download_general_info_stock()
