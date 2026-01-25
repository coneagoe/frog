from .downloader_akshare import (
    download_general_info_etf_ak,
    download_general_info_hk_ggt_stock_ak,
    download_general_info_stock_ak,
    download_history_data_etf_ak,
    download_history_data_stock_hk_ak,
    download_history_data_us_index_ak,
)
from .downloader_baostock import (
    download_history_data_stock_bs,
    download_ingredient_300,
    download_ingredient_500,
)
from .downloader_tushare import download_daily_basic_a_stock_ts, download_stk_limit


class Downloader:
    dl_general_info_stock = staticmethod(download_general_info_stock_ak)
    dl_general_info_etf = staticmethod(download_general_info_etf_ak)
    dl_general_info_hk_ggt_stock = staticmethod(download_general_info_hk_ggt_stock_ak)

    dl_history_data_etf = staticmethod(download_history_data_etf_ak)
    dl_history_data_us_index = staticmethod(download_history_data_us_index_ak)
    dl_history_data_stock = staticmethod(download_history_data_stock_bs)
    dl_history_data_stock_hk = staticmethod(download_history_data_stock_hk_ak)

    dl_ingredient_300 = staticmethod(download_ingredient_300)
    dl_ingredient_500 = staticmethod(download_ingredient_500)

    dl_daily_basic_a_stock = staticmethod(download_daily_basic_a_stock_ts)
    dl_stk_limit_a_stock = staticmethod(download_stk_limit)
