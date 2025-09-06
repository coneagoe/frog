import logging
import pandas as pd
from datetime import datetime
from typing import Optional

from .storage.base import DataStorage
from .downloader.base import DataDownloader
from stock.const import COL_DATE


class DownloadManager:
    """数据下载管理器"""
    
    def __init__(self, downloader: DataDownloader, storage: DataStorage):
        self.downloader = downloader
        self.storage = storage
    
    def download_and_save_stock_data(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: str = "qfq") -> bool:
        """下载并保存股票数据"""
        
        # 检查是否已有数据
        if not self.storage.data_exists(stock_id, period, adjust):
            # 全量下载
            df = self.downloader.download_stock_history(stock_id, period, start_date, end_date, adjust)
            if df is None or df.empty:
                logging.warning(f"Failed to download data for {stock_id}")
                return False
            
            return self.storage.save_stock_data(stock_id, df, period, adjust)
        else:
            # 增量更新
            return self._incremental_update_stock(stock_id, period, start_date, end_date, adjust)
    
    def download_and_save_etf_data(self, etf_id: str, period: str, start_date: str, end_date: str, adjust: str = "qfq") -> bool:
        """下载并保存ETF数据"""
        
        # 检查是否已有数据
        if not self.storage.data_exists(etf_id, period, adjust):
            # 全量下载
            df = self.downloader.download_etf_history(etf_id, period, start_date, end_date, adjust)
            if df is None or df.empty:
                logging.warning(f"Failed to download ETF data for {etf_id}")
                return False
            
            return self.storage.save_stock_data(etf_id, df, period, adjust)
        else:
            # 增量更新
            return self._incremental_update_etf(etf_id, period, start_date, end_date, adjust)
    
    def download_and_save_hk_stock_data(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: str = "hfq") -> bool:
        """下载并保存港股数据"""
        
        # 检查是否已有数据
        if not self.storage.data_exists(stock_id, period, adjust):
            # 全量下载
            df = self.downloader.download_hk_stock_history(stock_id, period, start_date, end_date, adjust)
            if df is None or df.empty:
                logging.warning(f"Failed to download HK stock data for {stock_id}")
                return False
            
            return self.storage.save_stock_data(stock_id, df, period, adjust)
        else:
            # 增量更新
            return self._incremental_update_hk_stock(stock_id, period, start_date, end_date, adjust)
    
    def download_and_save_general_info(self, info_type: str) -> bool:
        """下载并保存基本信息"""
        
        if info_type == "stock":
            df = self.downloader.download_stock_info()
        elif info_type == "etf":
            df = self.downloader.download_etf_info()
        elif info_type == "hk_ggt":
            df = self.downloader.download_hk_ggt_stock_info()
        elif info_type == "delisting":
            df = self.downloader.download_delisted_stock_info()
        else:
            logging.error(f"Unsupported info type: {info_type}")
            return False
        
        if df is None or df.empty:
            logging.warning(f"Failed to download {info_type} info")
            return False
        
        return self.storage.save_general_info(df, info_type)
    
    def _incremental_update_stock(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: str) -> bool:
        """增量更新股票数据"""
        end_date_ts = pd.Timestamp(end_date)
        latest_date = self.storage.get_latest_date(stock_id, period, adjust)
        
        if latest_date is None or end_date_ts <= latest_date:
            return True
        
        # 下载新数据
        start_date_new = (latest_date + pd.Timedelta(days=1)).strftime("%Y%m%d")
        end_date_new = pd.Timestamp(datetime.today().strftime("%Y-%m-%d")).strftime("%Y%m%d")
        
        new_df = self.downloader.download_stock_history(stock_id, period, start_date_new, end_date_new, adjust)
        if new_df is None or new_df.empty:
            logging.warning(f"No new data for {stock_id}")
            return True
        
        # 合并并保存数据
        existing_df = self.storage.load_stock_data(stock_id, period, adjust)
        if existing_df is not None:
            new_df[COL_DATE] = pd.to_datetime(new_df[COL_DATE])
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.sort_values(by=[COL_DATE], ascending=True)
            combined_df = combined_df.drop_duplicates(subset=[COL_DATE])
        else:
            combined_df = new_df
        
        return self.storage.save_stock_data(stock_id, combined_df, period, adjust)
    
    def _incremental_update_etf(self, etf_id: str, period: str, start_date: str, end_date: str, adjust: str) -> bool:
        """增量更新ETF数据"""
        end_date_ts = pd.Timestamp(end_date)
        latest_date = self.storage.get_latest_date(etf_id, period, adjust)
        
        if latest_date is None or end_date_ts <= latest_date:
            return True
        
        # 下载新数据
        start_date_new = (latest_date + pd.Timedelta(days=1)).strftime("%Y%m%d")
        end_date_new = pd.Timestamp(datetime.today().strftime("%Y-%m-%d")).strftime("%Y%m%d")
        
        new_df = self.downloader.download_etf_history(etf_id, period, start_date_new, end_date_new, adjust)
        if new_df is None or new_df.empty:
            logging.warning(f"No new ETF data for {etf_id}")
            return True
        
        # 合并并保存数据
        existing_df = self.storage.load_stock_data(etf_id, period, adjust)
        if existing_df is not None:
            new_df[COL_DATE] = pd.to_datetime(new_df[COL_DATE])
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.sort_values(by=[COL_DATE], ascending=True)
            combined_df = combined_df.drop_duplicates(subset=[COL_DATE])
        else:
            combined_df = new_df
        
        return self.storage.save_stock_data(etf_id, combined_df, period, adjust)
    
    def _incremental_update_hk_stock(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: str) -> bool:
        """增量更新港股数据"""
        end_date_ts = pd.Timestamp(end_date)
        latest_date = self.storage.get_latest_date(stock_id, period, adjust)
        
        if latest_date is None or end_date_ts <= latest_date:
            return True
        
        # 下载新数据
        start_date_new = (latest_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        end_date_new = datetime.today().strftime("%Y-%m-%d")
        
        new_df = self.downloader.download_hk_stock_history(stock_id, period, start_date_new, end_date_new, adjust)
        if new_df is None or new_df.empty:
            logging.warning(f"No new HK stock data for {stock_id}")
            return True
        
        # 合并并保存数据
        existing_df = self.storage.load_stock_data(stock_id, period, adjust)
        if existing_df is not None:
            new_df[COL_DATE] = pd.to_datetime(new_df[COL_DATE])
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.sort_values(by=[COL_DATE], ascending=True)
            combined_df = combined_df.drop_duplicates(subset=[COL_DATE])
        else:
            combined_df = new_df
        
        return self.storage.save_stock_data(stock_id, combined_df, period, adjust)
