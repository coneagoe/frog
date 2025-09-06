import pandas as pd
import akshare as ak
import retrying
import re
import logging
from typing import Optional
from .base import DataDownloader
from . import AdjustType
from stock.const import (
    COL_CLOSE,
    COL_DATE,
    COL_DELISTING_DATE,
    COL_HIGH,
    COL_IPO_DATE,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_VOLUME,
)

pattern_stock_id = r"60|00|30|68"


class AkshareDownloader(DataDownloader):
    """AkShare数据下载器"""
    
    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_stock_history(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: AdjustType = AdjustType.QFQ) -> Optional[pd.DataFrame]:
        try:
            assert re.match(r"\d{6}", stock_id)
            assert period in ["daily", "week", "month"]
            
            df = ak.stock_zh_a_hist(symbol=stock_id, period=period, adjust=adjust.value[0])
            if df.empty:
                logging.warning(f"download history data {stock_id} fail, please check")
                return None
            return df
        except Exception as e:
            logging.error(f"Failed to download stock history for {stock_id}: {e}")
            return None
    
    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_etf_history(self, etf_id: str, period: str, start_date: str, end_date: str, adjust: AdjustType = AdjustType.QFQ) -> Optional[pd.DataFrame]:
        try:
            assert period in ["daily", "week", "month"]
            
            try:
                df = ak.fund_etf_hist_em(symbol=etf_id, period=period, adjust=adjust.value[0])
                if df.empty:
                    raise KeyError("ETF data not found")
                return df
            except KeyError:
                # 尝试货币基金数据
                df = ak.fund_money_fund_info_em(etf_id)
                if df.empty:
                    logging.warning(f"download history data {etf_id} fail, please check")
                    return None
                
                # 为回测调整数据
                df = df.rename(columns={"净值日期": COL_DATE, "每万份收益": COL_CLOSE})
                df[COL_OPEN] = df[COL_CLOSE]
                df[COL_HIGH] = df[COL_CLOSE]
                df[COL_LOW] = df[COL_CLOSE]
                df[COL_VOLUME] = 0
                df = df[[COL_DATE, COL_CLOSE, COL_OPEN, COL_HIGH, COL_LOW, COL_VOLUME]]
                return df
        except Exception as e:
            logging.error(f"Failed to download ETF history for {etf_id}: {e}")
            return None
    

    @retrying.retry(wait_fixed=5000, stop_max_attempt_number=5)
    def download_hk_stock_history(self, stock_id: str, period: str, start_date: str, end_date: str, adjust: AdjustType = AdjustType.HFQ) -> Optional[pd.DataFrame]:
        try:
            assert re.match(r"\d{5}", stock_id)
            assert period in ["daily", "week", "month"]
            
            df = ak.stock_hk_hist(
                symbol=stock_id,
                period=period,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=adjust.value[0],
            )
            
            if df.empty:
                logging.warning(f"download history data {stock_id} fail, please check")
                return None
                
            df = df.rename(
                columns={
                    "日期": COL_DATE,
                    "开盘": COL_OPEN,
                    "收盘": COL_CLOSE,
                    "最高": COL_HIGH,
                    "最低": COL_LOW,
                    "成交量": COL_VOLUME,
                }
            )
            df[COL_DATE] = pd.to_datetime(df[COL_DATE])
            return df
        except Exception as e:
            logging.error(f"Failed to download HK stock history for {stock_id}: {e}")
            return None
    

    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_us_index_history(self, index: str, period: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        try:
            assert index in [".IXIC", ".DJI", ".INX"]
            assert period in ["daily", "week", "month"]
            
            df = ak.index_us_stock_sina(symbol=index)
            if df.empty:
                logging.warning(f"download history data {index} fail, please check")
                return None
                
            df = df.rename(columns={"date": COL_DATE, "close": COL_CLOSE})
            return df
        except Exception as e:
            logging.error(f"Failed to download US index history for {index}: {e}")
            return None
    

    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_a_index_history(self, index: str, period: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        try:
            assert period in ["daily", "week", "month"]
            
            df = ak.stock_zh_index_daily_em(symbol=index)
            if df.empty:
                logging.warning(f"download history data {index} fail, please check")
                return None
                
            df = df.iloc[:, :6]
            df.columns = [COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME]
            return df
        except Exception as e:
            logging.error(f"Failed to download A-share index history for {index}: {e}")
            return None
    
    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_stock_info(self) -> Optional[pd.DataFrame]:
        try:
            df = ak.stock_info_a_code_name()
            df = df.loc[df["code"].str.match(pattern_stock_id)]
            df = df.rename(columns={"code": COL_STOCK_ID, "name": COL_STOCK_NAME})
            return df
        except Exception as e:
            logging.error(f"Failed to download stock info: {e}")
            return None
    
    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_etf_info(self) -> Optional[pd.DataFrame]:
        try:
            df = ak.fund_name_em()
            return df
        except Exception as e:
            logging.error(f"Failed to download ETF info: {e}")
            return None
    
    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_hk_ggt_stock_info(self) -> Optional[pd.DataFrame]:
        try:
            df = ak.stock_hk_ggt_components_em()
            df = df.loc[:, ["代码", "名称"]]
            df = df.rename(columns={"代码": COL_STOCK_ID, "名称": COL_STOCK_NAME})
            return df
        except Exception as e:
            logging.error(f"Failed to download HK GGT stock info: {e}")
            return None
    
    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
    def download_delisted_stock_info(self) -> Optional[pd.DataFrame]:
        try:
            df = ak.stock_info_sh_delist(symbol="全部")
            df.columns = [COL_STOCK_ID, COL_STOCK_NAME, COL_IPO_DATE, COL_DELISTING_DATE]

            df0 = ak.stock_info_sz_delist(symbol="终止上市公司")
            df0.columns = [COL_STOCK_ID, COL_STOCK_NAME, COL_IPO_DATE, COL_DELISTING_DATE]

            df = pd.concat([df, df0])
            return df
        except Exception as e:
            logging.error(f"Failed to download delisted stock info: {e}")
            return None
