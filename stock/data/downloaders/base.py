from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional


class DataDownloader(ABC):
    """数据下载器抽象基类"""
    
    @abstractmethod
    def download_stock_history(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """下载股票历史数据"""
        pass
    
    @abstractmethod
    def download_etf_history(self, etf_id: str, period: str, start_date: str, end_date: str, adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """下载ETF历史数据"""
        pass
    
    @abstractmethod
    def download_hk_stock_history(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: str = "hfq") -> Optional[pd.DataFrame]:
        """下载港股历史数据"""
        pass
    
    @abstractmethod
    def download_us_index_history(self, index: str, period: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """下载美股指数历史数据"""
        pass
    
    @abstractmethod
    def download_a_index_history(self, index: str, period: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """下载A股指数历史数据"""
        pass
    
    @abstractmethod
    def download_stock_info(self) -> Optional[pd.DataFrame]:
        """下载股票基本信息"""
        pass
    
    @abstractmethod
    def download_etf_info(self) -> Optional[pd.DataFrame]:
        """下载ETF基本信息"""
        pass
    
    @abstractmethod
    def download_hk_ggt_stock_info(self) -> Optional[pd.DataFrame]:
        """下载港股通股票基本信息"""
        pass
    
    @abstractmethod
    def download_delisted_stock_info(self) -> Optional[pd.DataFrame]:
        """下载退市股票信息"""
        pass
