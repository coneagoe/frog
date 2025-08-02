import logging
import os
import sys
import time
from datetime import date

from tqdm import tqdm

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from stock import (  # noqa: E402
    COL_STOCK_ID,
    download_history_data_stock_hk,
    load_all_hk_ggt_stock_general_info,
)

conf.parse_config()


def download_all_hk_ggt_stock_data(
    period: str = "daily",
    adjust: str = "hfq",
    batch_size: int = 50,
    sleep_seconds: int = 2,
):
    start_date = "2025-01-16"
    end_date = date.today().strftime("%Y-%m-%d")

    hk_ggt_stocks_df = load_all_hk_ggt_stock_general_info()

    stock_ids = hk_ggt_stocks_df[COL_STOCK_ID].tolist()

    for i, stock_id in enumerate(tqdm(stock_ids, desc="Downloading HK GGT stock data")):
        try:
            download_history_data_stock_hk(
                stock_id, period, start_date, end_date, adjust
            )
        except Exception as e:
            logging.warning(f"Failed to download data for stock {stock_id}: {e}")

        # if (i + 1) % batch_size == 0 and (i + 1) < len(stock_ids):
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    download_all_hk_ggt_stock_data()
