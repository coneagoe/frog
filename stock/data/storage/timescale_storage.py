import pandas as pd
from typing import Optional
import logging
from sqlalchemy import create_engine, text
from .base import DataStorage
from stock.const import COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME


class TimescaleDBStorage(DataStorage):
    """TimescaleDB存储实现"""
    
    def __init__(self, connection_string: str):
        self.engine = create_engine(connection_string)
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        """确保数据表存在"""
        create_stock_table_sql = """
        CREATE TABLE IF NOT EXISTS stock_data (
            time TIMESTAMPTZ NOT NULL,
            stock_id VARCHAR(10) NOT NULL,
            period VARCHAR(10) NOT NULL,
            adjust VARCHAR(10) NOT NULL,
            open_price DECIMAL,
            close_price DECIMAL,
            high_price DECIMAL,
            low_price DECIMAL,
            volume BIGINT
        );
        
        SELECT create_hypertable('stock_data', 'time', if_not_exists => TRUE);
        
        CREATE INDEX IF NOT EXISTS idx_stock_data_composite 
        ON stock_data (stock_id, period, adjust, time DESC);
        """
        
        create_general_info_table_sql = """
        CREATE TABLE IF NOT EXISTS general_info (
            id SERIAL PRIMARY KEY,
            info_type VARCHAR(20) NOT NULL,
            stock_id VARCHAR(10),
            stock_name VARCHAR(100),
            ipo_date DATE,
            delisting_date DATE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(info_type, stock_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_general_info_type ON general_info (info_type);
        """
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(create_stock_table_sql))
                conn.execute(text(create_general_info_table_sql))
                conn.commit()
        except Exception as e:
            logging.error(f"Failed to create tables: {e}")
    
    def save_stock_data(self, stock_id: str, data: pd.DataFrame, period: str, adjust: str = "qfq") -> bool:
        try:
            # 准备数据
            data_copy = data.copy()
            data_copy['stock_id'] = stock_id
            data_copy['period'] = period
            data_copy['adjust'] = adjust
            
            # 重命名列以匹配数据库表结构
            column_mapping = {
                COL_DATE: 'time',
                COL_OPEN: 'open_price',
                COL_CLOSE: 'close_price',
                COL_HIGH: 'high_price',
                COL_LOW: 'low_price',
                COL_VOLUME: 'volume'
            }
            
            # 只保留存在的列
            existing_columns = [col for col in column_mapping.keys() if col in data_copy.columns]
            data_copy = data_copy[existing_columns + ['stock_id', 'period', 'adjust']]
            data_copy = data_copy.rename(columns={k: v for k, v in column_mapping.items() if k in existing_columns})
            
            # 确保time列是datetime类型
            data_copy['time'] = pd.to_datetime(data_copy['time'])
            
            # 先删除已存在的数据（避免重复）
            delete_sql = """
            DELETE FROM stock_data 
            WHERE stock_id = :stock_id AND period = :period AND adjust = :adjust
            """
            
            with self.engine.connect() as conn:
                conn.execute(text(delete_sql), {
                    'stock_id': stock_id,
                    'period': period,
                    'adjust': adjust
                })
                
                # 写入数据库
                data_copy.to_sql('stock_data', conn, if_exists='append', index=False)
                conn.commit()
            
            return True
        except Exception as e:
            logging.error(f"Failed to save stock data: {e}")
            return False
    
    def load_stock_data(self, stock_id: str, period: str, adjust: str = "qfq") -> Optional[pd.DataFrame]:
        try:
            query = """
            SELECT time, open_price, close_price, high_price, low_price, volume
            FROM stock_data 
            WHERE stock_id = :stock_id AND period = :period AND adjust = :adjust
            ORDER BY time
            """
            df = pd.read_sql(query, self.engine, params={
                'stock_id': stock_id,
                'period': period,
                'adjust': adjust
            })
            
            if df.empty:
                return None
                
            # 重命名列回原来的格式
            column_mapping = {
                'time': COL_DATE,
                'open_price': COL_OPEN,
                'close_price': COL_CLOSE,
                'high_price': COL_HIGH,
                'low_price': COL_LOW,
                'volume': COL_VOLUME
            }
            df = df.rename(columns=column_mapping)
            df[COL_DATE] = pd.to_datetime(df[COL_DATE])
            return df
        except Exception as e:
            logging.error(f"Failed to load stock data: {e}")
            return None
    
    def get_latest_date(self, stock_id: str, period: str, adjust: str = "qfq") -> Optional[pd.Timestamp]:
        try:
            query = """
            SELECT MAX(time) as latest_date
            FROM stock_data 
            WHERE stock_id = :stock_id AND period = :period AND adjust = :adjust
            """
            result = pd.read_sql(query, self.engine, params={
                'stock_id': stock_id,
                'period': period,
                'adjust': adjust
            })
            
            if result.empty or pd.isna(result.iloc[0]['latest_date']):
                return None
            return pd.Timestamp(result.iloc[0]['latest_date'])
        except Exception as e:
            logging.error(f"Failed to get latest date: {e}")
            return None
    
    def data_exists(self, stock_id: str, period: str, adjust: str = "qfq") -> bool:
        try:
            query = """
            SELECT 1 FROM stock_data 
            WHERE stock_id = :stock_id AND period = :period AND adjust = :adjust
            LIMIT 1
            """
            result = pd.read_sql(query, self.engine, params={
                'stock_id': stock_id,
                'period': period,
                'adjust': adjust
            })
            return not result.empty
        except Exception as e:
            logging.error(f"Failed to check data existence: {e}")
            return False
    
    def save_general_info(self, data: pd.DataFrame, info_type: str) -> bool:
        try:
            # 清空该类型的旧数据
            delete_sql = "DELETE FROM general_info WHERE info_type = :info_type"
            
            with self.engine.connect() as conn:
                conn.execute(text(delete_sql), {'info_type': info_type})
                
                # 准备数据
                data_copy = data.copy()
                data_copy['info_type'] = info_type
                
                # 写入数据库
                data_copy.to_sql('general_info', conn, if_exists='append', index=False)
                conn.commit()
            
            return True
        except Exception as e:
            logging.error(f"Failed to save general info: {e}")
            return False
    
    def load_general_info(self, info_type: str) -> Optional[pd.DataFrame]:
        try:
            query = """
            SELECT stock_id, stock_name, ipo_date, delisting_date
            FROM general_info 
            WHERE info_type = :info_type
            ORDER BY stock_id
            """
            df = pd.read_sql(query, self.engine, params={'info_type': info_type})
            
            if df.empty:
                return None
            return df
        except Exception as e:
            logging.error(f"Failed to load general info: {e}")
            return None
