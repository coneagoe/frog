from stock import *
from datetime import date
import conf


stocks_general_info = None


def is_data_older_than_a_week(data_file_path: str):
    modified_time = os.path.getmtime(data_file_path)
    today = date.today()
    pass


if __name__ == '__main__':
    conf.config = conf.parse_config()
    download_stock_general_info()
