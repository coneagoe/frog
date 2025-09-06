from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional


class DataStorage(ABC):
    """数据存储抽象基类"""
    
    @abstractmethod
    def save_stock_data(self, stock_id: str, data: pd.DataFrame, period: str, adjust: str = "qfq") -> bool:
        """保存股票数据"""
        pass
    
    @abstractmethod
    def load_stock_data(self, stock_id: str, period: str, adjust: str = "qfq") -> Optional[pd.DataFrame]:
        """加载股票数据"""
        pass
    
    @abstractmethod
    def get_latest_date(self, stock_id: str, period: str, adjust: str = "qfq") -> Optional[pd.Timestamp]:
        """获取最新数据日期"""
        pass
    
    @abstractmethod
    def data_exists(self, stock_id: str, period: str, adjust: str = "qfq") -> bool:
        """检查数据是否存在"""
        pass
    
    @abstractmethod
    def save_general_info(self, data: pd.DataFrame, info_type: str) -> bool:
        """保存基本信息数据"""
        pass
    
    @abstractmethod
    def load_general_info(self, info_type: str) -> Optional[pd.DataFrame]:
        """加载基本信息数据"""
        pass
