import os
import akshare as ak
from stock import get_stock_data_path


def download_history_etf(etf_id: str, start_date: str, end_date: str):
    output_file_name = os.path.join(get_stock_data_path(), f"{etf_id}.csv")

    df = ak.fund_etf_hist_em(symbol=etf_id, period="daily",
                             start_date=start_date, end_date=end_date,
                             adjust="")

    df.to_csv(output_file_name, encoding='utf_8_sig', index=False)
