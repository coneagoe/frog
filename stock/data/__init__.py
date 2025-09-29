from .access_data import (
    drop_delisted_stocks,
    drop_low_price_stocks,
    drop_st,
    drop_suspended_stocks,
    get_etf_name,
    get_security_name,
    get_stock_name,
    is_a_index,
    is_etf,
    is_hk_ggt_stock,
    is_st,
    is_stock,
    is_us_index,
    load_300_ingredients,
    load_500_ingredients,
    load_all_etf_general_info,
    load_all_hk_ggt_stock_general_info,
    load_all_stock_general_info,
    load_history_data,
    load_history_data_a_index,
    load_history_data_etf,
    load_history_data_stock,
    load_history_data_stock_hk,
    load_history_data_us_index,
)
from .download_data import (
    download_300_ingredients,
    download_500_ingredients,
    download_general_info_etf,
    download_general_info_hk_ggt_stock,
    download_general_info_stock,
    download_history_data_a_index,
    download_history_data_etf,
    download_history_data_stock,
    download_history_data_stock_hk,
    download_history_data_us_index,
)
from .download_manager import DownloadManager
from .downloader import DataDownloader
from .eastmoney import fetch_close_price
from .factory import create_download_manager
from .moving_average import get_today_ma, get_yesterday_ma

__all__ = [
    "drop_delisted_stocks",
    "drop_low_price_stocks",
    "drop_st",
    "drop_suspended_stocks",
    "get_etf_name",
    "get_security_name",
    "get_stock_name",
    "is_a_index",
    "is_etf",
    "is_hk_ggt_stock",
    "is_st",
    "is_stock",
    "is_us_index",
    "load_300_ingredients",
    "load_500_ingredients",
    "load_all_etf_general_info",
    "load_all_hk_ggt_stock_general_info",
    "load_all_stock_general_info",
    "load_history_data",
    "load_history_data_a_index",
    "load_history_data_etf",
    "load_history_data_stock",
    "load_history_data_stock_hk",
    "load_history_data_us_index",
    "download_300_ingredients",
    "download_500_ingredients",
    "download_general_info_etf",
    "download_general_info_hk_ggt_stock",
    "download_general_info_stock",
    "download_history_data_a_index",
    "download_history_data_etf",
    "download_history_data_stock",
    "download_history_data_stock_hk",
    "download_history_data_us_index",
    "fetch_close_price",
    "get_today_ma",
    "get_yesterday_ma",
    "DownloadManager",
    "DataDownloader",
    "create_download_manager",
]

# 新的架构组件
from .factory import (
    create_download_manager,
    download_stock_data_with_csv,
    download_stock_data_with_timescale,
    download_general_info_with_csv,
    download_general_info_with_timescale,
)
from .download_manager import DownloadManager
from .storage import DataStorage, CSVStorage, TimescaleDBStorage
from .downloader import DataDownloader, AkshareDownloader

# 新的便捷函数
from .download_data import (
    download_stock_with_timescale,
    download_etf_with_timescale,
    download_hk_stock_with_timescale,
    download_general_info_with_storage,
)
