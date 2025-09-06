import os
import pandas as pd
from typing import Optional
from .base import DataStorage
from stock.common import (
    get_stock_data_path_1d,
    get_stock_data_path_1w,
    get_stock_data_path_1M,
    get_stock_general_info_path,
    get_etf_general_info_path,
    get_hk_ggt_stock_general_info_path,
    get_stock_delisting_info_path,
)
from stock.const import COL_DATE


class CSVStorage(DataStorage):
    """CSV文件存储实现"""
    
    def _get_file_path(self, stock_id: str, period: str, adjust: str) -> str:
        file_name = f"{stock_id}_{adjust}.csv"
        if period == "daily":
            return os.path.join(get_stock_data_path_1d(), file_name)
        elif period == "week":
            return os.path.join(get_stock_data_path_1w(), file_name)
        else:
            return os.path.join(get_stock_data_path_1M(), file_name)
    
    def save_stock_data(self, stock_id: str, data: pd.DataFrame, period: str, adjust: str = "qfq") -> bool:
        try:
            file_path = self._get_file_path(stock_id, period, adjust)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            data.to_csv(file_path, encoding="utf_8_sig", index=False)
            return True
        except Exception:
            return False
    
    def load_stock_data(self, stock_id: str, period: str, adjust: str = "qfq") -> Optional[pd.DataFrame]:
        try:
            file_path = self._get_file_path(stock_id, period, adjust)
            if not os.path.exists(file_path):
                return None
            df = pd.read_csv(file_path, encoding="utf_8_sig")
            df[COL_DATE] = pd.to_datetime(df[COL_DATE])
            return df
        except Exception:
            return None
    
    def get_latest_date(self, stock_id: str, period: str, adjust: str = "qfq") -> Optional[pd.Timestamp]:
        df = self.load_stock_data(stock_id, period, adjust)
        if df is None or df.empty:
            return None
        return df[COL_DATE].iloc[-1]
    
    def data_exists(self, stock_id: str, period: str, adjust: str = "qfq") -> bool:
        file_path = self._get_file_path(stock_id, period, adjust)
        return os.path.exists(file_path)
    
    def save_general_info(self, data: pd.DataFrame, info_type: str) -> bool:
        try:
            if info_type == "stock":
                file_path = get_stock_general_info_path()
            elif info_type == "etf":
                file_path = get_etf_general_info_path()
            elif info_type == "hk_ggt":
                file_path = get_hk_ggt_stock_general_info_path()
            elif info_type == "delisting":
                file_path = get_stock_delisting_info_path()
            else:
                return False
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            data.to_csv(file_path, encoding="utf_8_sig", index=False)
            return True
        except Exception:
            return False
    
    def load_general_info(self, info_type: str) -> Optional[pd.DataFrame]:
        try:
            if info_type == "stock":
                file_path = get_stock_general_info_path()
            elif info_type == "etf":
                file_path = get_etf_general_info_path()
            elif info_type == "hk_ggt":
                file_path = get_hk_ggt_stock_general_info_path()
            elif info_type == "delisting":
                file_path = get_stock_delisting_info_path()
            else:
                return None
                
            if not os.path.exists(file_path):
                return None
            return pd.read_csv(file_path, encoding="utf_8_sig")
        except Exception:
            return None
