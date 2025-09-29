import logging

from .download_status import force_run_task, get_today_status_summary, status_manager
from .downloader_akshare import (
    download_general_info_etf_ak,
    download_general_info_hk_ggt_stock_ak,
    download_general_info_stock_ak,
    download_history_data_etf_ak,
    download_history_data_stock_ak,
    download_history_data_us_index_ak,
)


class Downloader:
    dl_general_info_stock = download_general_info_stock_ak
    dl_general_info_etf = download_general_info_etf_ak
    dl_general_info_hk_ggt_stock = download_general_info_hk_ggt_stock_ak

    dl_history_data_etf = download_history_data_etf_ak
    dl_history_data_us_index = download_history_data_us_index_ak
    dl_history_data_stock = download_history_data_stock_ak

    @classmethod
    def download_all_basic_info(cls, force: bool = False):
        tasks = [
            ("stock_general_info", cls.dl_general_info_stock),
            ("etf_general_info", cls.dl_general_info_etf),
            ("hk_ggt_stock_general_info", cls.dl_general_info_hk_ggt_stock),
        ]

        if force:
            for task_name, _ in tasks:
                force_run_task(task_name)

        for task_name, task_func in tasks:
            try:
                task_func()
            except Exception as e:
                logging.error(f"Failed to execute {task_name}: {e}")

    @classmethod
    def get_status(cls):
        """获取今天的下载状态"""
        return get_today_status_summary()

    @classmethod
    def force_refresh_task(cls, task_name: str):
        """强制重新执行指定任务"""
        force_run_task(task_name)

    @classmethod
    def cleanup_old_status(cls, keep_days: int = 30):
        """清理旧的状态记录"""
        status_manager.cleanup_old_records(keep_days)
