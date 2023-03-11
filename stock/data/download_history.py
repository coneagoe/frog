import os
from stock import get_stock_general_info_path


def download_history(stock_id: str, start_date: str, end_date: str):
    output_file_name = os.path.join(get_stock_general_info_path(), f"{stock_id}.csv")
    # TODO
