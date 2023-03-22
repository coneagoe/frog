import os
from stock import get_stock_data_path
import akshare as ak


def download_history_stock(stock_id: str, start_date: str, end_date: str):
    output_file_name = os.path.join(get_stock_data_path(), f"{stock_id}.csv")

    df = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                            start_date=start_date, end_date=end_date,
                            adjust="")

    df.to_csv(output_file_name, encoding='utf_8_sig', index=False)
