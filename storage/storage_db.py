import logging
import os
import textwrap
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Literal, Optional, Set, cast

import pandas as pd
import psycopg2
from psycopg2.extensions import connection, cursor
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from common.const import (
    COL_ACT_ENT_TYPE,
    COL_ACT_NAME,
    COL_AMOUNT,
    COL_ANN_DATE,
    COL_AREA,
    COL_CHANGE,
    COL_CHANGE_RATE,
    COL_CIRC_MV,
    COL_CLOSE,
    COL_CN_SPELL,
    COL_CURR_TYPE,
    COL_CUSTOD_NAME,
    COL_DATE,
    COL_DELISTING_DATE,
    COL_DOWN_LIMIT,
    COL_DV_RATIO,
    COL_DV_TTM,
    COL_END_DATE,
    COL_ENNAME,
    COL_ETF_EXT_NAME,
    COL_ETF_ID,
    COL_ETF_NAME,
    COL_ETF_TYPE,
    COL_EXCHANGE,
    COL_FLOAT_HOLDER_HOLD_AMOUNT,
    COL_FLOAT_HOLDER_HOLD_CHANGE,
    COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
    COL_FLOAT_HOLDER_TYPE,
    COL_FLOAT_SHARE,
    COL_FREE_SHARE,
    COL_FULLNAME,
    COL_HIGH,
    COL_HOLDER_NUM,
    COL_INDEX_CODE,
    COL_INDEX_NAME,
    COL_INDUSTRY,
    COL_IPO_DATE,
    COL_IS_HS,
    COL_LIST_STATUS,
    COL_LOW,
    COL_MARKET,
    COL_MGR_NAME,
    COL_MGT_FEE,
    COL_OPEN,
    COL_PB,
    COL_PE,
    COL_PE_TTM,
    COL_PRE_CLOSE,
    COL_PS,
    COL_PS_TTM,
    COL_SETUP_DATE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_SUSPEND_TIMING,
    COL_SUSPEND_TYPE,
    COL_TOTAL_MV,
    COL_TOTAL_SHARE,
    COL_TURNOVER_RATE,
    COL_TURNOVER_RATE_F,
    COL_UP_LIMIT,
    COL_VOLUME,
    COL_VOLUME_RATIO,
    AdjustType,
    PeriodType,
    SecurityType,
)

from .config import StorageConfig
from .model import (
    Base,
    tb_name_a_stock_basic,
    tb_name_daily_basic_a_stock,
    tb_name_etf_basic,
    tb_name_etf_daily,
    tb_name_general_info_etf,
    tb_name_general_info_ggt,
    tb_name_general_info_stock,
    tb_name_history_data_daily_a_stock_hfq,
    tb_name_history_data_daily_a_stock_qfq,
    tb_name_history_data_daily_etf_hfq,
    tb_name_history_data_daily_etf_qfq,
    tb_name_history_data_daily_fund,
    tb_name_history_data_daily_hk_stock_hfq,
    tb_name_history_data_monthly_hk_stock_hfq,
    tb_name_history_data_weekly_a_stock_hfq,
    tb_name_history_data_weekly_a_stock_qfq,
    tb_name_history_data_weekly_etf_hfq,
    tb_name_history_data_weekly_etf_qfq,
    tb_name_history_data_weekly_hk_stock_hfq,
    tb_name_ingredient_300,
    tb_name_ingredient_500,
    tb_name_ssf_change_signal,
    tb_name_stk_holdernumber,
    tb_name_stk_limit_a_stock,
    tb_name_suspend_d_a_stock,
    tb_name_top10_floatholders,
)

logger = logging.getLogger(__name__)

SSF_CHANGE_SIGNAL_STATUS_SIGNAL = "signal"
SSF_CHANGE_SIGNAL_STATUS_NO_SIGNAL = "no_signal"


COL_MAP_DAILY_BASIC = {
    "ts_code": COL_STOCK_ID,
    "trade_date": COL_DATE,
    "close": COL_CLOSE,
    "turnover_rate": COL_TURNOVER_RATE,
    "turnover_rate_f": COL_TURNOVER_RATE_F,
    "volume_ratio": COL_VOLUME_RATIO,
    "pe": COL_PE,
    "pe_ttm": COL_PE_TTM,
    "pb": COL_PB,
    "ps": COL_PS,
    "ps_ttm": COL_PS_TTM,
    "dv_ratio": COL_DV_RATIO,
    "dv_ttm": COL_DV_TTM,
    "total_share": COL_TOTAL_SHARE,
    "float_share": COL_FLOAT_SHARE,
    "free_share": COL_FREE_SHARE,
    "total_mv": COL_TOTAL_MV,
    "circ_mv": COL_CIRC_MV,
}


COL_MAP_STK_LIMIT = {
    "trade_date": COL_DATE,
    "ts_code": COL_STOCK_ID,
    "pre_close": COL_PRE_CLOSE,
    "up_limit": COL_UP_LIMIT,
    "down_limit": COL_DOWN_LIMIT,
}


COL_MAP_SUSPEND_D = {
    "ts_code": COL_STOCK_ID,
    "trade_date": COL_DATE,
    "suspend_timing": COL_SUSPEND_TIMING,
    "suspend_type": COL_SUSPEND_TYPE,
}


COL_MAP_STK_HOLDERNUMBER = {
    "ts_code": COL_STOCK_ID,
    "ann_date": COL_ANN_DATE,
    "end_date": COL_END_DATE,
    "holder_num": COL_HOLDER_NUM,
}


COL_MAP_TOP10_FLOATHOLDERS = {
    "ts_code": COL_STOCK_ID,
    "ann_date": COL_ANN_DATE,
    "end_date": COL_END_DATE,
    "holder_name": COL_FLOAT_HOLDER_NAME,
    "hold_amount": COL_FLOAT_HOLDER_HOLD_AMOUNT,
    "hold_ratio": COL_FLOAT_HOLDER_HOLD_RATIO,
    "hold_float_ratio": COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    "hold_change": COL_FLOAT_HOLDER_HOLD_CHANGE,
    "holder_type": COL_FLOAT_HOLDER_TYPE,
}


COL_MAP_STOCK_BASIC = {
    "ts_code": COL_STOCK_ID,
    "name": COL_STOCK_NAME,
    "area": COL_AREA,
    "industry": COL_INDUSTRY,
    "fullname": COL_FULLNAME,
    "enname": COL_ENNAME,
    "cnspell": COL_CN_SPELL,
    "market": COL_MARKET,
    "exchange": COL_EXCHANGE,
    "curr_type": COL_CURR_TYPE,
    "list_status": COL_LIST_STATUS,
    "list_date": COL_IPO_DATE,
    "delist_date": COL_DELISTING_DATE,
    "is_hs": COL_IS_HS,
    "act_name": COL_ACT_NAME,
    "act_ent_type": COL_ACT_ENT_TYPE,
}


COL_MAP_FUND_DAILY = {
    "ts_code": COL_ETF_ID,
    "trade_date": COL_DATE,
    "open": COL_OPEN,
    "high": COL_HIGH,
    "low": COL_LOW,
    "close": COL_CLOSE,
    "pre_close": COL_PRE_CLOSE,
    "change": COL_CHANGE,
    "pct_chg": COL_CHANGE_RATE,
    "vol": COL_VOLUME,
    "amount": COL_AMOUNT,
}


COL_MAP_ETF_BASIC = {
    "ts_code": COL_ETF_ID,
    "csname": COL_ETF_NAME,
    "extname": COL_ETF_EXT_NAME,
    "cname": COL_FULLNAME,
    "index_code": COL_INDEX_CODE,
    "index_name": COL_INDEX_NAME,
    "setup_date": COL_SETUP_DATE,
    "list_date": COL_IPO_DATE,
    "list_status": COL_LIST_STATUS,
    "exchange": COL_EXCHANGE,
    "mgr_name": COL_MGR_NAME,
    "custod_name": COL_CUSTOD_NAME,
    "mgt_fee": COL_MGT_FEE,
    "etf_type": COL_ETF_TYPE,
}


COL_MAP_ETF_DAILY = {
    "ts_code": COL_ETF_ID,
    "trade_date": COL_DATE,
    "open": COL_OPEN,
    "high": COL_HIGH,
    "low": COL_LOW,
    "close": COL_CLOSE,
    "pre_close": COL_PRE_CLOSE,
    "change": COL_CHANGE,
    "pct_chg": COL_CHANGE_RATE,
    "vol": COL_VOLUME,
    "amount": COL_AMOUNT,
}


# PID-scoped singleton: one StorageDb instance per process to avoid connection explosion
_storage_instances: Dict[int, "StorageDb"] = {}
# Track which PIDs have already run metadata.create_all() to avoid repeated DDL checks
_metadata_initialized_pids: Set[int] = set()

# Tables keyed by ETF/fund code instead of stock code.
ETF_ID_TABLES: Set[str] = {
    tb_name_etf_daily,
    tb_name_history_data_daily_fund,
}


def get_table_name(
    security_type: SecurityType, period: PeriodType, adjust: AdjustType
) -> str:
    if security_type == SecurityType.STOCK:
        if period == PeriodType.DAILY:
            if adjust == AdjustType.QFQ:
                return tb_name_history_data_daily_a_stock_qfq
            elif adjust == AdjustType.HFQ:
                return tb_name_history_data_daily_a_stock_hfq
        elif period == PeriodType.WEEKLY:
            if adjust == AdjustType.QFQ:
                return tb_name_history_data_weekly_a_stock_qfq
            elif adjust == AdjustType.HFQ:
                return tb_name_history_data_weekly_a_stock_hfq
    elif security_type == SecurityType.ETF:
        if period == PeriodType.DAILY:
            if adjust == AdjustType.QFQ:
                return tb_name_history_data_daily_etf_qfq
            elif adjust == AdjustType.HFQ:
                return tb_name_history_data_daily_etf_hfq
        elif period == PeriodType.WEEKLY:
            if adjust == AdjustType.QFQ:
                return tb_name_history_data_weekly_etf_qfq
            elif adjust == AdjustType.HFQ:
                return tb_name_history_data_weekly_etf_hfq
    elif security_type == SecurityType.HK_GGT_STOCK:
        if period == PeriodType.DAILY and adjust == AdjustType.HFQ:
            return tb_name_history_data_daily_hk_stock_hfq
        elif period == PeriodType.WEEKLY and adjust == AdjustType.HFQ:
            return tb_name_history_data_weekly_hk_stock_hfq
        elif period == PeriodType.MONTHLY and adjust == AdjustType.HFQ:
            return tb_name_history_data_monthly_hk_stock_hfq

    raise ValueError(f"Unsupported combination: {security_type}, {period}, {adjust}")


def reset_storage() -> None:
    """
    重置当前进程的 StorageDb 单例实例（主要用于测试）
    """
    global _storage_instances, _metadata_initialized_pids
    pid = os.getpid()
    if pid in _storage_instances:
        _storage_instances[pid].disconnect()
        del _storage_instances[pid]
        _metadata_initialized_pids.discard(pid)
        logger.info(f"Reset StorageDb singleton instance for PID {pid}")


def connect_once(func):
    """
    一次性连接装饰器：connect → 执行函数 → disconnect
    适用于短期操作，自动管理连接生命周期
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # 记录原始连接状态
        was_connected = self.connection is not None and self.cursor is not None

        try:
            # 如果没有连接，则建立连接
            if not was_connected:
                if not self.connect():
                    raise ConnectionError("无法建立数据库连接")

            # 执行函数
            result = func(self, *args, **kwargs)

            return result

        finally:
            # 如果最初没有连接，则断开连接（一次性模式）
            if not was_connected:
                self.disconnect()

    return wrapper


class StorageError(Exception):
    pass


class ConnectionError(StorageError):
    pass


class DataNotFoundError(StorageError):
    pass


class StorageDb:
    def __init__(self, config: StorageConfig):
        self.config = config

        self.host = self.config.get_db_host()
        self.port = self.config.get_db_port()
        self.database = self.config.get_db_name()
        self.username = self.config.get_db_username()
        self.password = self.config.get_db_password()

        self.connection: Optional[connection] = None
        self.cursor: Optional[cursor] = None
        self.Session = None

        sqlalchemy_url = f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

        # Pool settings to prevent connection explosion under concurrent Airflow tasks.
        # Read overrides from env vars; defaults are very conservative (1 conn per process).
        pool_size = int(os.getenv("STORAGE_DB_POOL_SIZE", "1"))
        max_overflow = int(os.getenv("STORAGE_DB_MAX_OVERFLOW", "0"))
        pool_recycle = int(os.getenv("STORAGE_DB_POOL_RECYCLE", "1800"))
        pool_pre_ping = os.getenv("STORAGE_DB_POOL_PRE_PING", "true").lower() in (
            "true",
            "1",
            "yes",
        )

        self.engine = create_engine(
            sqlalchemy_url,
            echo=False,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
        )

        self.Session = sessionmaker(bind=self.engine)

        # Run DDL/table creation only once per process to avoid repeated checks
        pid = os.getpid()
        if pid not in _metadata_initialized_pids:
            Base.metadata.create_all(self.engine)
            _metadata_initialized_pids.add(pid)

    def connect(self) -> bool:
        try:
            connection_string = (
                f"host={self.host} "
                f"port={self.port} "
                f"dbname={self.database} "
                f"user={self.username} "
                f"password={self.password}"
            )

            self.connection = psycopg2.connect(connection_string)
            assert self.connection is not None  # Type checking assertion
            self.cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            return True

        except Exception as e:
            logger.error(f"fail to connect DB: {str(e)}")
            self.connection = None
            self.cursor = None
            return False

    def disconnect(self) -> bool:
        try:
            if self.cursor is not None:
                self.cursor.close()

            if self.connection is not None:
                self.connection.close()

            self.cursor = None
            self.connection = None

            return True

        except Exception as e:
            logger.error(f"fail to disconnect DB: {str(e)}")
            return False

    def _require_engine(self):
        if self.engine is None:
            raise ConnectionError("SQLAlchemy引擎未初始化")
        return self.engine

    def _normalize_code_column(
        self, df: pd.DataFrame, code_column: Optional[str]
    ) -> pd.DataFrame:
        if code_column and code_column in df.columns:
            df[code_column] = (
                df[code_column].astype("string").str.split(".", n=1).str[0]
            )
        return df

    def _normalize_date_columns(
        self,
        df: pd.DataFrame,
        date_columns: dict[str, str],
    ) -> pd.DataFrame:
        for column, output in date_columns.items():
            converted = pd.to_datetime(df[column], format="%Y%m%d", errors="coerce")
            if output == "date":
                df[column] = converted.dt.date
            else:
                df[column] = converted.dt.strftime("%Y-%m-%d")
        return df

    def _prepare_dataframe_for_save(
        self,
        df: pd.DataFrame,
        *,
        column_map: dict[str, str],
        code_column: Optional[str] = None,
        date_columns: Optional[dict[str, str]] = None,
        optional_columns: Optional[list[str]] = None,
        output_columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        prepared = df.rename(columns=column_map).copy()
        for column in optional_columns or []:
            if column not in prepared.columns:
                prepared[column] = pd.NA
        prepared = self._normalize_code_column(prepared, code_column)
        ordered_columns = output_columns or list(column_map.values())
        prepared = prepared[ordered_columns]
        if date_columns:
            prepared = self._normalize_date_columns(prepared, date_columns)
        return prepared

    def _write_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        *,
        if_exists: Literal["append", "replace"],
        method: Optional[Literal["multi"]] = None,
    ) -> None:
        engine = self._require_engine()
        if method is None:
            df.to_sql(table_name, engine, if_exists=if_exists, index=False)
            return

        df.to_sql(
            table_name,
            engine,
            if_exists=if_exists,
            index=False,
            method=method,
        )

    def _get_history_table_name(
        self, security_type: SecurityType, period: PeriodType, adjust: AdjustType
    ) -> str:
        return get_table_name(security_type, period, adjust)

    def _build_code_date_range_query(
        self,
        *,
        table_name: str,
        code_column: str,
        code_value: str,
        date_column: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        order: str = "ASC",
    ) -> tuple[str, tuple[Any, ...]]:
        sql_lines = [
            f"SELECT * FROM {table_name}",
            f'WHERE "{code_column}" = %s',
        ]
        params: list[Any] = [code_value]

        if start_date:
            sql_lines.append(f'AND "{date_column}" >= %s')
            params.append(start_date)
        if end_date:
            sql_lines.append(f'AND "{date_column}" <= %s')
            params.append(end_date)

        sql_lines.append(f'ORDER BY "{date_column}" {order}')
        return "\n".join(sql_lines), tuple(params)

    def save_history_data_stock(
        self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType
    ) -> bool:
        table_name = self._get_history_table_name(SecurityType.STOCK, period, adjust)
        self._write_dataframe(
            df,
            table_name,
            if_exists="append",
            method="multi",
        )

        return True

    def save_history_data_hk_stock(
        self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType
    ) -> bool:
        """
        保存港股历史数据到对应的数据库表

        Args:
            df: 港股历史数据DataFrame
            period: 数据周期（日/周/月）
            adjust: 复权类型（默认后复权）

        Returns:
            bool: 保存是否成功
        """
        try:
            try:
                table_name = self._get_history_table_name(
                    SecurityType.HK_GGT_STOCK, period, AdjustType.HFQ
                )
            except ValueError:
                logger.error(f"不支持的港股数据周期: {period}")
                return False

            self._write_dataframe(
                df,
                table_name,
                if_exists="append",
                method="multi",
            )

            logger.info(f"港股历史数据保存成功: {table_name}, 数据条数: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"保存港股历史数据失败: {str(e)}")
            return False

    def save_history_data_etf(
        self,
        df: pd.DataFrame,
        period: PeriodType,
        adjust: AdjustType,
    ) -> bool:
        """
        保存ETF历史数据到对应的数据库表

        Args:
            df: ETF历史数据DataFrame
            period: 数据周期（日/周）
            adjust: 复权类型（前复权/后复权）

        Returns:
            bool: 保存是否成功
        """
        try:
            if period not in {PeriodType.DAILY, PeriodType.WEEKLY}:
                logger.error(f"不支持的ETF数据周期: {period}")
                return False

            try:
                table_name = self._get_history_table_name(
                    SecurityType.ETF, period, adjust
                )
            except ValueError:
                logger.error(f"不支持的ETF复权类型: {adjust}")
                return False

            self._write_dataframe(
                df,
                table_name,
                if_exists="append",
                method="multi",
            )

            logger.info(f"ETF历史数据保存成功: {table_name}, 数据条数: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"保存ETF历史数据失败: {str(e)}")
            return False

    def save_history_data_fund(self, df: pd.DataFrame) -> bool:
        """
        保存基金/ETF日线行情数据到对应的数据库表 (Tushare fund_daily 接口)

        Args:
            df: 基金日线行情数据DataFrame

        Returns:
            bool: 保存是否成功
        """
        try:
            prepared = self._prepare_dataframe_for_save(
                df,
                column_map=COL_MAP_FUND_DAILY,
                code_column=COL_ETF_ID,
                date_columns={COL_DATE: "str"},
                output_columns=list(COL_MAP_FUND_DAILY.values()),
            )

            self._write_dataframe(
                prepared,
                tb_name_history_data_daily_fund,
                if_exists="append",
                method="multi",
            )

            logger.info(
                f"基金日线行情数据保存成功: {tb_name_history_data_daily_fund}, 数据条数: {len(prepared)}"
            )
            return True

        except Exception as e:
            logger.error(f"保存基金日线行情数据失败: {str(e)}")
            return False

    def load_history_data_fund(
        self,
        fund_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载基金/ETF日线行情数据

        Args:
            fund_id: 基金代码
            start_date: 开始日期（可选，格式：YYYY-MM-DD）
            end_date: 结束日期（可选，格式：YYYY-MM-DD）

        Returns:
            pd.DataFrame: 基金日线行情数据，如果表不存在或加载失败则返回空DataFrame
        """
        try:
            sql, sql_params = self._build_code_date_range_query(
                table_name=tb_name_history_data_daily_fund,
                code_column=COL_ETF_ID,
                code_value=fund_id,
                date_column=COL_DATE,
                start_date=start_date,
                end_date=end_date,
            )
            df = pd.read_sql(sql, self.engine, params=sql_params)
            logger.info(f"基金日线行情数据加载成功: {fund_id}, 数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载基金日线行情数据失败: {fund_id}, 错误: {str(e)}")
            return pd.DataFrame()

    def save_general_info_stock(self, df: pd.DataFrame) -> bool:
        df.to_sql(
            tb_name_general_info_stock, self.engine, if_exists="replace", index=False
        )
        return True

    def load_general_info_stock(self) -> pd.DataFrame:
        """
        加载股票基本信息数据，过滤掉北交所股票

        Returns:
            pd.DataFrame: 股票基本信息数据（不含北交所股票）。如果表不存在或加载失败则返回空DataFrame
        """

        table_name = tb_name_general_info_stock

        try:
            sql = f"""
            SELECT * FROM {table_name}
            WHERE {COL_STOCK_ID} NOT LIKE '8%%'
            AND {COL_STOCK_ID} NOT LIKE '4%%'
            AND {COL_STOCK_ID} NOT LIKE '920%%'
            """

            df = pd.read_sql(sql, self.engine)
            return df

        except Exception as e:
            logger.error(f"加载股票基本信息数据失败: {str(e)}")
            return pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

    def save_general_info_etf(
        self, df: pd.DataFrame, table_name: str = tb_name_general_info_etf
    ) -> bool:
        """
        保存ETF基本信息

        Args:
            df: ETF数据DataFrame
            table_name: 表名，默认为ETF基本信息表

        Returns:
            bool: 保存是否成功
        """
        try:
            if self.engine is None:
                raise ConnectionError("SQLAlchemy引擎未初始化")

            df.to_sql(table_name, self.engine, if_exists="replace", index=False)
            return True

        except Exception as e:
            logger.error(f"保存ETF基本信息失败: {str(e)}")
            return False

    def load_general_info_etf(
        self, table_name: str = tb_name_general_info_etf
    ) -> pd.DataFrame:
        """
        加载ETF基本信息数据

        Returns:
            pd.DataFrame: ETF基本信息数据。如果表不存在或加载失败则返回空DataFrame
        """
        try:
            sql = f"""
            SELECT * FROM {table_name}
            """

            df = pd.read_sql(sql, self.engine)
            return df

        except Exception as e:
            logger.error(f"加载ETF基本信息数据失败: {str(e)}")
            return pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

    def save_general_info_hk_ggt(self, df: pd.DataFrame) -> bool:
        df.to_sql(
            tb_name_general_info_ggt, self.engine, if_exists="replace", index=False
        )
        return True

    def save_ingredient_300(self, df: pd.DataFrame) -> bool:
        """
        保存沪深300成分股数据

        Args:
            df: 沪深300成分股数据DataFrame

        Returns:
            bool: 保存是否成功
        """
        try:
            if self.engine is None:
                raise ConnectionError("SQLAlchemy引擎未初始化")

            df.to_sql(
                tb_name_ingredient_300, self.engine, if_exists="replace", index=False
            )
            logger.info(f"沪深300成分股数据保存成功，数据条数: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"保存沪深300成分股数据失败: {str(e)}")
            return False

    def save_ingredient_500(self, df: pd.DataFrame) -> bool:
        """
        保存中证500成分股数据

        Args:
            df: 中证500成分股数据DataFrame

        Returns:
            bool: 保存是否成功
        """
        try:
            if self.engine is None:
                raise ConnectionError("SQLAlchemy引擎未初始化")

            df.to_sql(
                tb_name_ingredient_500, self.engine, if_exists="replace", index=False
            )
            logger.info(f"中证500成分股数据保存成功，数据条数: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"保存中证500成分股数据失败: {str(e)}")
            return False

    def load_ingredient_300(self) -> pd.DataFrame:
        """
        加载沪深300成分股数据

        Returns:
            pd.DataFrame: 沪深300成分股数据。如果表不存在或加载失败则返回空DataFrame
        """
        try:
            sql = f"""
            SELECT * FROM {tb_name_ingredient_300}
            """

            df = pd.read_sql(sql, self.engine)
            logger.info(f"沪深300成分股数据加载成功，数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载沪深300成分股数据失败: {str(e)}")
            return pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

    def load_ingredient_500(self) -> pd.DataFrame:
        """
        加载中证500成分股数据

        Returns:
            pd.DataFrame: 中证500成分股数据。如果表不存在或加载失败则返回空DataFrame
        """
        try:
            sql = f"""
            SELECT * FROM {tb_name_ingredient_500}
            """

            df = pd.read_sql(sql, self.engine)
            logger.info(f"中证500成分股数据加载成功，数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载中证500成分股数据失败: {str(e)}")
            return pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

    def load_general_info_hk_ggt(self) -> pd.DataFrame:
        """
        加载港股通成分股基本信息数据

        Returns:
            pd.DataFrame: 港股通成分股基本信息数据。如果表不存在或加载失败则返回空DataFrame
        """
        try:
            sql = f"""
            SELECT * FROM {tb_name_general_info_ggt}
            """

            df = pd.read_sql(sql, self.engine)
            return df

        except Exception as e:
            logger.error(f"加载港股通成分股基本信息数据失败: {str(e)}")
            return pd.DataFrame(columns=[COL_STOCK_ID, COL_STOCK_NAME])

    def load_history_data_stock(
        self,
        stock_id: str,
        period: PeriodType,
        adjust: AdjustType,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载股票历史数据

        Args:
            stock_id: 股票代码
            period: 数据周期（日/周/月）
            adjust: 复权类型（前复权/后复权）
            start_date: 开始日期（可选，格式：YYYY-MM-DD）
            end_date: 结束日期（可选，格式：YYYY-MM-DD）

        Returns:
            pd.DataFrame: 股票历史数据，如果表不存在或加载失败则返回空DataFrame
        """
        try:
            # 根据周期和复权类型选择对应的表名
            if period == PeriodType.DAILY:
                if adjust == AdjustType.QFQ:
                    table_name = tb_name_history_data_daily_a_stock_qfq
                elif adjust == AdjustType.HFQ:
                    table_name = tb_name_history_data_daily_a_stock_hfq
                else:
                    logger.error(f"不支持的复权类型: {adjust}")
                    return pd.DataFrame()
            elif period == PeriodType.WEEKLY:
                if adjust == AdjustType.QFQ:
                    table_name = tb_name_history_data_weekly_a_stock_qfq
                elif adjust == AdjustType.HFQ:
                    table_name = tb_name_history_data_weekly_a_stock_hfq
                else:
                    logger.error(f"不支持的复权类型: {adjust}")
                    return pd.DataFrame()
            else:
                logger.error(f"不支持的数据周期: {period}")
                return pd.DataFrame()

            # 构建SQL查询
            sql = f"""
            SELECT * FROM {table_name}
            WHERE "{COL_STOCK_ID}" = %s
            """

            params: List[Any] = [stock_id]

            # 添加日期范围条件
            if start_date:
                sql += f' AND "{COL_DATE}" >= %s'
                params.append(start_date)
            if end_date:
                sql += f' AND "{COL_DATE}" <= %s'
                params.append(end_date)

            sql += f' ORDER BY "{COL_DATE}" ASC'

            # Convert list to tuple for pandas read_sql compatibility
            sql_params = tuple(params) if params else None
            df = pd.read_sql(sql, self.engine, params=sql_params)
            logger.info(
                f"股票历史数据加载成功: {stock_id}, 周期: {period}, 复权: {adjust}, 数据条数: {len(df)}"
            )
            return df

        except Exception as e:
            logger.error(
                f"加载股票历史数据失败: {stock_id}, 周期: {period}, 复权: {adjust}, 错误: {str(e)}"
            )
            return pd.DataFrame()

    def load_history_data_stock_hk_ggt(
        self,
        stock_id: str,
        period: PeriodType,
        adjust: AdjustType,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载港股通成分股历史数据

        Args:
            stock_id: 港股通股票代码
            period: 数据周期（日/周/月）
            adjust: 复权类型（港股通只支持后复权）
            start_date: 开始日期（可选，格式：YYYY-MM-DD）
            end_date: 结束日期（可选，格式：YYYY-MM-DD）

        Returns:
            pd.DataFrame: 港股通成分股历史数据，如果表不存在或加载失败则返回空DataFrame
        """
        try:
            # 港股通只支持后复权，检查复权类型
            if adjust != AdjustType.HFQ:
                logger.error(f"港股通只支持后复权，不支持复权类型: {adjust}")
                return pd.DataFrame()

            # 根据周期选择对应的港股表名（港股通使用与港股相同的表）
            if period == PeriodType.DAILY:
                table_name = tb_name_history_data_daily_hk_stock_hfq
            elif period == PeriodType.WEEKLY:
                table_name = tb_name_history_data_weekly_hk_stock_hfq
            elif period == PeriodType.MONTHLY:
                table_name = tb_name_history_data_monthly_hk_stock_hfq
            else:
                logger.error(f"不支持的港股通数据周期: {period}")
                return pd.DataFrame()

            # 构建SQL查询
            sql = f"""
            SELECT * FROM {table_name}
            WHERE "{COL_STOCK_ID}" = %s
            """

            params: List[Any] = [stock_id]

            # 添加日期范围条件
            if start_date:
                sql += f' AND "{COL_DATE}" >= %s'
                params.append(start_date)
            if end_date:
                sql += f' AND "{COL_DATE}" <= %s'
                params.append(end_date)

            sql += f' ORDER BY "{COL_DATE}" ASC'

            # Convert list to tuple for pandas read_sql compatibility
            sql_params = tuple(params) if params else None
            df = pd.read_sql(sql, self.engine, params=sql_params)
            logger.info(
                f"港股通成分股历史数据加载成功: {stock_id}, 周期: {period}, 复权: {adjust}, 数据条数: {len(df)}"
            )
            return df

        except Exception as e:
            logger.error(
                f"加载港股通成分股历史数据失败: {stock_id}, 周期: {period}, 复权: {adjust}, 错误: {str(e)}"
            )
            return pd.DataFrame()

    def load_history_data_etf(
        self,
        etf_id: str,
        period: PeriodType,
        adjust: AdjustType,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载ETF历史数据

        Args:
            etf_id: ETF代码
            period: 数据周期（日/周）
            adjust: 复权类型（前复权/后复权）
            start_date: 开始日期（可选，格式：YYYY-MM-DD）
            end_date: 结束日期（可选，格式：YYYY-MM-DD）

        Returns:
            pd.DataFrame: ETF历史数据，如果表不存在或加载失败则返回空DataFrame
        """
        try:
            # 根据周期和复权类型选择对应的ETF表名
            if period == PeriodType.DAILY:
                if adjust == AdjustType.QFQ:
                    table_name = tb_name_history_data_daily_etf_qfq
                elif adjust == AdjustType.HFQ:
                    table_name = tb_name_history_data_daily_etf_hfq
                else:
                    logger.error(f"不支持的ETF复权类型: {adjust}")
                    return pd.DataFrame()
            elif period == PeriodType.WEEKLY:
                if adjust == AdjustType.QFQ:
                    table_name = tb_name_history_data_weekly_etf_qfq
                elif adjust == AdjustType.HFQ:
                    table_name = tb_name_history_data_weekly_etf_hfq
                else:
                    logger.error(f"不支持的ETF复权类型: {adjust}")
                    return pd.DataFrame()
            else:
                logger.error(f"不支持的ETF数据周期: {period}")
                return pd.DataFrame()

            # 构建SQL查询
            sql = f"""
            SELECT * FROM {table_name}
            WHERE "{COL_STOCK_ID}" = %s
            """

            params: List[Any] = [etf_id]

            # 添加日期范围条件
            if start_date:
                sql += f' AND "{COL_DATE}" >= %s'
                params.append(start_date)
            if end_date:
                sql += f' AND "{COL_DATE}" <= %s'
                params.append(end_date)

            sql += f' ORDER BY "{COL_DATE}" ASC'

            # Convert list to tuple for pandas read_sql compatibility
            sql_params = tuple(params) if params else None
            df = pd.read_sql(sql, self.engine, params=sql_params)
            logger.info(
                f"ETF历史数据加载成功: {etf_id}, 周期: {period}, 复权: {adjust}, 数据条数: {len(df)}"
            )
            return df

        except Exception as e:
            logger.error(
                f"加载ETF历史数据失败: {etf_id}, 周期: {period}, 复权: {adjust}, 错误: {str(e)}"
            )
            return pd.DataFrame()

    @connect_once
    def query(self, sql: str, params: Optional[dict] = None) -> Optional[list]:
        """
        通用查询方法（一次性连接）

        Args:
            sql: SQL查询语句，可以使用:parameter_name格式的命名参数
            params: 参数字典，例如{'parameter_name': value}

        Returns:
            list: 查询结果列表，每个元素是字典格式的行数据，失败返回None

        Example:
            # 简单查询
            result = storage.query("SELECT * FROM users WHERE age = %s", {'age': 18})

            # 复杂参数查询
            result = storage.query(
                "SELECT * FROM stock_data WHERE code = %s AND date = %s",
                {'code': '600000', 'date': '2024-01-01'}
            )
        """
        try:
            # The @connect_once decorator ensures cursor is not None
            assert self.cursor is not None, "Database cursor should not be None"

            if params is None:
                self.cursor.execute(sql)
            else:
                # 将字典转换为元组按位置传递参数
                sql_params = tuple(params.values())
                self.cursor.execute(sql, sql_params)

            results = self.cursor.fetchall()

            # 转换结果为列表字典格式
            result_list = []
            if results:
                for row in results:
                    result_list.append(dict(row))

            return result_list

        except Exception as e:
            logger.error(f"fail to query: {str(e)}")
            return None

    def data_exist(self, table_name: str, conditions: str) -> bool:
        """
        检查数据是否存在

        Args:
            table_name: 表名
            conditions: SQL条件语句（不含WHERE）

        Returns:
            bool: 数据是否存在
        """
        sql = f"SELECT EXISTS(SELECT 1 FROM {table_name} WHERE {conditions}) AS exist_flag;"

        result = self.query(sql)
        if result and len(result) > 0:
            return bool(result[0].get("exist_flag", False))

        return False

    def has_history_data(self, table_name: str, code: str) -> bool:
        """
        检查历史数据是否存在

        Args:
            table_name: 表名
            code: 股票代码

        Returns:
            bool: 历史数据是否存在
        """
        conditions = f"code = '{code}'"
        return self.data_exist(table_name, conditions)

    @connect_once
    def drop_table(self, table_name: str):
        """
        删除指定表中的所有记录

        Args:
            table_name: 表名
        """
        try:
            assert self.cursor is not None, "Database cursor should not be None"
            assert self.connection is not None, "Database connection should not be None"

            sql = f"DELETE FROM {table_name}"
            self.cursor.execute(sql)
            self.connection.commit()

        except Exception as e:
            logger.error(f"删除表 {table_name} 中的记录失败: {str(e)}")
            if self.connection:
                self.connection.rollback()

    @connect_once
    def get_last_record(
        self, table_name: str, stock_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        获取指定股票在指定表中的最新一条记录

        Args:
            table_name: 表名
            stock_id: 股票代码，如果为None则获取表中所有记录的最新一条

        Returns:
            dict: 最新记录的字段值字典，如果不存在则返回None
        """
        try:
            assert self.cursor is not None, "Database cursor should not be None"

            id_column = COL_ETF_ID if table_name in ETF_ID_TABLES else COL_STOCK_ID

            if stock_id:
                sql = textwrap.dedent(
                    f"""\
                SELECT * FROM {table_name}
                WHERE "{id_column}" = %s
                ORDER BY "{COL_DATE}" DESC
                LIMIT 1
                """
                ).replace("\n", "\n" + " " * 12)
                sql = "\n" + " " * 12 + sql
                self.cursor.execute(sql, (stock_id,))
            else:
                sql = textwrap.dedent(
                    f"""\
                SELECT * FROM {table_name}
                ORDER BY "{COL_DATE}" DESC
                LIMIT 1
                """
                ).replace("\n", "\n" + " " * 12)
                sql = "\n" + " " * 12 + sql
                self.cursor.execute(sql)

            result = self.cursor.fetchone()

            if result:
                return dict(result)
            else:
                return None

        except Exception as e:
            logger.error(
                f"获取最新记录失败 - 表名: {table_name}, 股票代码: {stock_id}, 错误: {str(e)}"
            )
            return None

    def save_daily_basic_a_stock(self, df: pd.DataFrame) -> bool:
        """
        保存每日基础数据到对应的数据库表

        Args:
            df: 每日基础数据DataFrame

        Returns:
            bool: 保存是否成功
        """

        try:
            df.rename(columns=COL_MAP_DAILY_BASIC, inplace=True)
            df[COL_STOCK_ID] = df[COL_STOCK_ID].str.split(".").str[0]
            df = df[list(COL_MAP_DAILY_BASIC.values())]
            # 转换日期为 YYYY-MM-DD 格式
            df[COL_DATE] = pd.to_datetime(
                df[COL_DATE], format="%Y%m%d", errors="coerce"
            ).dt.strftime("%Y-%m-%d")
            df.to_sql(
                tb_name_daily_basic_a_stock,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

            return True

        except Exception as e:
            logger.error(f"保存每日基础数据失败: {str(e)}")
            return False

    def save_stk_limit_a_stock(self, df: pd.DataFrame) -> bool:
        """
        保存涨跌停价格数据到对应的数据库表

        Args:
            df: 涨跌停价格数据DataFrame

        Returns:
            bool: 保存是否成功
        """

        try:
            df = df.rename(columns=COL_MAP_STK_LIMIT)
            df[COL_STOCK_ID] = df[COL_STOCK_ID].str.split(".").str[0]
            df = df[list(COL_MAP_STK_LIMIT.values())]
            # 转换日期为 YYYY-MM-DD 格式
            df[COL_DATE] = pd.to_datetime(
                df[COL_DATE], format="%Y%m%d", errors="coerce"
            ).dt.strftime("%Y-%m-%d")
            df.to_sql(
                tb_name_stk_limit_a_stock,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

            return True

        except Exception as e:
            logger.error(f"保存涨跌停价格数据失败: {str(e)}")
            return False

    def save_suspend_d_a_stock(self, df: pd.DataFrame) -> bool:
        """
        保存停复牌数据到对应的数据库表

        Args:
            df: 停复牌数据DataFrame

        Returns:
            bool: 保存是否成功
        """

        try:
            df.rename(columns=COL_MAP_SUSPEND_D, inplace=True)
            df[COL_STOCK_ID] = df[COL_STOCK_ID].str.split(".").str[0]
            df = df[list(COL_MAP_SUSPEND_D.values())]
            # 转换停复牌日期为 YYYY-MM-DD 格式
            df[COL_DATE] = pd.to_datetime(
                df[COL_DATE], format="%Y%m%d", errors="coerce"
            ).dt.strftime("%Y-%m-%d")
            df.to_sql(
                tb_name_suspend_d_a_stock,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

            return True

        except Exception as e:
            logger.error(f"保存停复牌数据失败: {str(e)}")
            return False

    def save_stk_holdernumber(self, df: pd.DataFrame) -> bool:
        """
        保存股东人数数据到对应的数据库表

        Args:
            df: 股东人数数据DataFrame（来自TuShare stk_holdernumber接口）

        Returns:
            bool: 保存是否成功
        """
        try:
            prepared = self._prepare_dataframe_for_save(
                df,
                column_map=COL_MAP_STK_HOLDERNUMBER,
                code_column=COL_STOCK_ID,
                date_columns={COL_ANN_DATE: "str", COL_END_DATE: "str"},
                output_columns=list(COL_MAP_STK_HOLDERNUMBER.values()),
            )

            self._write_dataframe(
                prepared,
                tb_name_stk_holdernumber,
                if_exists="append",
                method="multi",
            )
            return True

        except Exception as e:
            logger.error(f"保存股东人数数据失败: {str(e)}")
            return False

    def save_top10_floatholders(self, df: pd.DataFrame) -> bool:
        """
        保存前十大流通股东数据到对应的数据库表

        Args:
            df: 前十大流通股东数据DataFrame（来自TuShare top10_floatholders接口）

        Returns:
            bool: 保存是否成功
        """
        try:
            df = df.rename(columns=COL_MAP_TOP10_FLOATHOLDERS)
            df[COL_STOCK_ID] = df[COL_STOCK_ID].str.split(".").str[0]
            for optional_col in [
                COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
                COL_FLOAT_HOLDER_HOLD_CHANGE,
                COL_FLOAT_HOLDER_TYPE,
            ]:
                if optional_col not in df.columns:
                    df[optional_col] = pd.NA
            df = df[list(COL_MAP_TOP10_FLOATHOLDERS.values())]
            for col in [COL_ANN_DATE, COL_END_DATE]:
                df[col] = pd.to_datetime(
                    df[col], format="%Y%m%d", errors="coerce"
                ).dt.date

            if self.engine is None:
                raise ConnectionError("SQLAlchemy引擎未初始化")

            table = Base.metadata.tables[tb_name_top10_floatholders]
            records = df.to_dict(orient="records")
            if not records:
                return True

            primary_keys = list(table.primary_key.columns.keys())
            if self.engine.dialect.name == "postgresql":
                stmt = (
                    pg_insert(table)
                    .values(records)
                    .on_conflict_do_nothing(index_elements=primary_keys)
                )
            elif self.engine.dialect.name == "sqlite":
                stmt = (
                    sqlite_insert(table)
                    .values(records)
                    .on_conflict_do_nothing(index_elements=primary_keys)
                )
            else:
                raise ConnectionError(
                    f"Unsupported database dialect: {self.engine.dialect.name}"
                )

            with self.engine.begin() as conn:
                conn.execute(stmt)

            return True

        except Exception as e:
            logger.error(f"保存前十大流通股东数据失败: {str(e)}")
            return False

    @connect_once
    def get_last_stk_holdernumber_ann_date(self, stock_id: str) -> Optional[str]:
        """
        获取指定股票在 stk_holdernumber 表中最新的公告日期

        Args:
            stock_id: 股票代码（不含交易所后缀）

        Returns:
            日期字符串（YYYY-MM-DD），无记录时返回 None
        """
        try:
            assert self.cursor is not None, "Database cursor should not be None"
            sql = textwrap.dedent(
                f"""\
            SELECT "{COL_ANN_DATE}" FROM {tb_name_stk_holdernumber}
            WHERE "{COL_STOCK_ID}" = %s
            ORDER BY "{COL_ANN_DATE}" DESC
            LIMIT 1
            """
            )
            self.cursor.execute(sql, (stock_id,))
            result = self.cursor.fetchone()
            if result:
                return str(result[0])
            return None

        except Exception as e:
            logger.error(
                f"获取股东人数最新公告日期失败 - 股票代码: {stock_id}, 错误: {e}"
            )
            return None

    @connect_once
    def get_last_top10_floatholders_ann_date(self, stock_id: str) -> Optional[str]:
        """
        获取指定股票在 top10_floatholders 表中最新的公告日期

        Args:
            stock_id: 股票代码（不含交易所后缀）

        Returns:
            日期字符串（YYYY-MM-DD），无记录时返回 None
        """
        try:
            assert self.cursor is not None, "Database cursor should not be None"
            sql = textwrap.dedent(
                f"""\
            SELECT "{COL_ANN_DATE}" FROM {tb_name_top10_floatholders}
            WHERE "{COL_STOCK_ID}" = %s
            ORDER BY "{COL_ANN_DATE}" DESC
            LIMIT 1
            """
            )
            self.cursor.execute(sql, (stock_id,))
            result = self.cursor.fetchone()
            if result:
                return str(result[0])
            return None

        except Exception as e:
            logger.error(
                f"获取前十大流通股东最新公告日期失败 - 股票代码: {stock_id}, 错误: {e}"
            )
            return None

    def save_a_stock_basic(self, df: pd.DataFrame) -> bool:
        """
        保存A股基础信息数据到对应的数据库表

        Args:
            df: A股基础信息数据DataFrame (from TuShare stock_basic接口)

        Returns:
            bool: 保存是否成功
        """

        try:
            df.rename(columns=COL_MAP_STOCK_BASIC, inplace=True)
            df[COL_STOCK_ID] = df[COL_STOCK_ID].str.split(".").str[0]
            df = df[list(COL_MAP_STOCK_BASIC.values())]
            # 转换上市日期和退市日期为 date 类型
            df[COL_IPO_DATE] = pd.to_datetime(
                df[COL_IPO_DATE], format="%Y%m%d", errors="coerce"
            ).dt.date
            df[COL_DELISTING_DATE] = pd.to_datetime(
                df[COL_DELISTING_DATE], format="%Y%m%d", errors="coerce"
            ).dt.date
            df.to_sql(
                tb_name_a_stock_basic,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

            return True

        except Exception as e:
            logger.error(f"保存A股基础信息数据失败: {str(e)}")
            return False

    def load_daily_basic(self, date: str, stock_ids: list[str]) -> pd.DataFrame:
        """加载指定日期的daily_basic数据（PB, PE, 市值等）

        Args:
            date: 日期(YYYY-MM-DD)
            stock_ids: 股票代码列表

        Returns:
            pd.DataFrame: 包含PB, PE, 市值等数据的DataFrame
        """
        sql = f"""
        SELECT * FROM "{tb_name_daily_basic_a_stock}"
        WHERE "{COL_DATE}" = %s
        AND "{COL_STOCK_ID}" = ANY(%s)
        """

        df = pd.read_sql(sql, self.engine, params=(date, stock_ids))  # type: ignore[arg-type]
        return df

    def load_stock_basic(self, stock_ids: list[str]) -> pd.DataFrame:
        """加载股票基本信息（用于获取上市日期）

        Args:
            stock_ids: 股票代码列表

        Returns:
            pd.DataFrame: 包含上市日期等信息的DataFrame，上市日期已转换为datetime类型
        """
        sql = f"""
        SELECT "{COL_STOCK_ID}", "{COL_IPO_DATE}" FROM "{tb_name_a_stock_basic}"
        WHERE "{COL_STOCK_ID}" = ANY(%s)
        """

        df = pd.read_sql(sql, self.engine, params=(stock_ids,))  # type: ignore[arg-type]
        # df[COL_IPO_DATE] = pd.to_datetime(df[COL_IPO_DATE], format="%Y%m%d")
        return df

    def save_etf_basic(self, df: pd.DataFrame) -> bool:
        """
        保存ETF基础信息数据到对应的数据库表

        Args:
            df: ETF基础信息数据DataFrame (from TuShare etf_basic接口)

        Returns:
            bool: 保存是否成功
        """
        try:
            df = df.rename(columns=COL_MAP_ETF_BASIC)
            # 提取ETF代码（去掉 .SH/.SZ 后缀）
            df[COL_ETF_ID] = df[COL_ETF_ID].str.split(".").str[0]
            df = df[list(COL_MAP_ETF_BASIC.values())]
            # 转换日期为 date 类型
            df[COL_SETUP_DATE] = pd.to_datetime(
                df[COL_SETUP_DATE], format="%Y%m%d", errors="coerce"
            ).dt.date
            df[COL_IPO_DATE] = pd.to_datetime(
                df[COL_IPO_DATE], format="%Y%m%d", errors="coerce"
            ).dt.date
            df.to_sql(
                tb_name_etf_basic,
                self.engine,
                if_exists="replace",
                index=False,
                method="multi",
            )
            logger.info(f"ETF基础信息数据保存成功，数据条数: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"保存ETF基础信息数据失败: {str(e)}")
            return False

    def load_etf_basic(self) -> pd.DataFrame:
        """
        加载ETF基础信息数据

        Returns:
            pd.DataFrame: ETF基础信息数据。如果表不存在或加载失败则返回空DataFrame
        """
        try:
            sql = f"""
            SELECT * FROM {tb_name_etf_basic}
            """

            df = pd.read_sql(sql, self.engine)
            logger.info(f"ETF基础信息数据加载成功，数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载ETF基础信息数据失败: {str(e)}")
            return pd.DataFrame(columns=[COL_ETF_ID, COL_ETF_NAME])

    def save_etf_daily(self, df: pd.DataFrame) -> bool:
        """
        保存ETF日线数据到数据库

        Args:
            df: ETF日线数据DataFrame，包含以下列：
                - ts_code: 基金代码
                - trade_date: 交易日期
                - open: 开盘价
                - high: 最高价
                - low: 最低价
                - close: 收盘价
                - pre_close: 昨日收盘价
                - change: 涨跌额
                - pct_chg: 涨跌幅
                - vol: 成交量
                - amount: 成交额

        Returns:
            bool: 保存是否成功
        """
        try:
            df = df.rename(columns=COL_MAP_ETF_DAILY)
            # 去除ETF代码的后缀（如 .SH, .SZ）
            df[COL_ETF_ID] = df[COL_ETF_ID].str.split(".").str[0]
            # 转换日期格式
            df[COL_DATE] = pd.to_datetime(df[COL_DATE], format="%Y%m%d").dt.date

            df.to_sql(
                tb_name_etf_daily,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )
            logger.info(
                f"ETF日线数据保存成功: {tb_name_etf_daily}, 数据条数: {len(df)}"
            )
            return True

        except Exception as e:
            logger.error(f"保存ETF日线数据失败: {str(e)}")
            return False

    def load_etf_daily(
        self,
        etf_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载ETF日线数据

        Args:
            start_date: 开始日期 (YYYY-MM-DD格式)
            end_date: 结束日期 (YYYY-MM-DD格式)

        Returns:
            pd.DataFrame: ETF日线数据
        """
        try:
            sql, sql_params = self._build_code_date_range_query(
                table_name=tb_name_etf_daily,
                code_column=COL_ETF_ID,
                code_value=etf_id,
                date_column=COL_DATE,
                start_date=start_date,
                end_date=end_date,
            )
            df = pd.read_sql(sql, self.engine, params=sql_params)
            logger.info(f"ETF日线数据加载成功，数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载ETF日线数据失败: {str(e)}")
            return pd.DataFrame()

    def ensure_ssf_change_signals_table(self) -> None:
        """建表（若不存在），供 SSF 变动信号流程初始化使用。"""
        from .model.ssf_change_signal import SSFChangeSignal  # noqa: F401

        SSFChangeSignal.__table__.create(self.engine, checkfirst=True)
        self._ensure_ssf_change_signals_status_column()

    def _ensure_ssf_change_signals_status_column(self) -> None:
        assert self.engine is not None
        columns = {
            column["name"]
            for column in inspect(self.engine).get_columns(tb_name_ssf_change_signal)
        }
        if "status" in columns:
            return

        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    ALTER TABLE {tb_name_ssf_change_signal}
                    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'signal'
                    """
                )
            )

    def list_ssf_change_signal_candidates(self) -> List[tuple[str, str]]:
        """列出尚未生成 SSF 变动信号的最新公告股票列表。"""
        sql = textwrap.dedent(
            f"""\
            SELECT DISTINCT t."{COL_STOCK_ID}" AS stock_id, t."{COL_ANN_DATE}" AS ann_date
            FROM {tb_name_top10_floatholders} t
            JOIN (
                SELECT "{COL_STOCK_ID}" AS stock_id, MAX("{COL_ANN_DATE}") AS ann_date
                FROM {tb_name_top10_floatholders}
                GROUP BY "{COL_STOCK_ID}"
            ) latest
              ON t."{COL_STOCK_ID}" = latest.stock_id
             AND t."{COL_ANN_DATE}" = latest.ann_date
            LEFT JOIN {tb_name_ssf_change_signal} s
              ON s.stock_id = latest.stock_id
             AND s.ann_date = latest.ann_date
            WHERE s.id IS NULL
            ORDER BY ann_date DESC, stock_id
            """
        )
        assert self.engine is not None
        df = pd.read_sql(sql, self.engine)
        return [
            (row["stock_id"], pd.Timestamp(row["ann_date"]).strftime("%Y-%m-%d"))
            for _, row in df.iterrows()
        ]

    def load_top10_floatholders_history(
        self, stock_id: str, limit_ann_dates: int = 2
    ) -> pd.DataFrame:
        sql = textwrap.dedent(
            f"""\
            SELECT *
            FROM {tb_name_top10_floatholders}
            WHERE "{COL_STOCK_ID}" = :stock_id
              AND "{COL_ANN_DATE}" IN (
                  SELECT DISTINCT "{COL_ANN_DATE}"
                  FROM {tb_name_top10_floatholders}
                  WHERE "{COL_STOCK_ID}" = :stock_id
                  ORDER BY "{COL_ANN_DATE}" DESC
                  LIMIT :limit_ann_dates
              )
            ORDER BY "{COL_ANN_DATE}" DESC, "{COL_FLOAT_HOLDER_NAME}"
            """
        )
        assert self.engine is not None
        params: dict[str, str | int] = {
            "stock_id": stock_id,
            "limit_ann_dates": limit_ann_dates,
        }
        df = pd.read_sql(
            text(sql),
            self.engine,
            params=params,
        )
        if COL_ANN_DATE in df.columns:
            df[COL_ANN_DATE] = pd.to_datetime(df[COL_ANN_DATE])
        return df

    def save_ssf_change_signals(self, records: List[Dict[str, Any]]) -> List[int]:
        """保存 SSF 变动信号，已存在的 `(stock_id, ann_date)` 记录会跳过。"""
        normalized_records = []
        for payload in records:
            normalized_payload = dict(payload)
            normalized_payload["status"] = SSF_CHANGE_SIGNAL_STATUS_SIGNAL
            normalized_records.append(normalized_payload)
        return self._save_ssf_change_signal_records(normalized_records)

    def mark_ssf_change_candidates_processed(
        self, records: List[Dict[str, Any]]
    ) -> List[int]:
        normalized_records = []
        for payload in records:
            normalized_records.append(
                {
                    "stock_id": payload["stock_id"],
                    "ann_date": payload["ann_date"],
                    "prev_ann_date": payload.get("prev_ann_date")
                    or payload["ann_date"],
                    "status": SSF_CHANGE_SIGNAL_STATUS_NO_SIGNAL,
                    "event_types": [],
                    "score": 0.0,
                    "detail_json": {"holders": []},
                    "alert_sent_at": datetime.now(timezone.utc),
                }
            )
        return self._save_ssf_change_signal_records(normalized_records)

    def _save_ssf_change_signal_records(
        self, records: List[Dict[str, Any]]
    ) -> List[int]:
        from .model.ssf_change_signal import SSFChangeSignal

        assert self.engine is not None
        table = SSFChangeSignal.__table__
        if self.engine.dialect.name == "postgresql":
            insert_fn = pg_insert
        elif self.engine.dialect.name == "sqlite":
            insert_fn = sqlite_insert
        else:
            raise ConnectionError(
                f"Unsupported database dialect: {self.engine.dialect.name}"
            )

        inserted: List[int] = []
        optional_fields = [
            "status",
            "ssf_holder_count_now",
            "ssf_holder_count_prev",
            "ssf_holder_count_change",
            "ssf_total_hold_ratio_now",
            "ssf_total_hold_ratio_prev",
            "ssf_total_hold_ratio_change",
            "alert_sent_at",
        ]
        for payload in records:
            try:
                signal_payload = {
                    "stock_id": payload["stock_id"],
                    "ann_date": pd.to_datetime(payload["ann_date"]).date(),
                    "prev_ann_date": pd.to_datetime(payload["prev_ann_date"]).date(),
                    "event_types": payload["event_types"],
                    "score": payload["score"],
                    "detail_json": payload["detail_json"],
                }
                for field in optional_fields:
                    if field in payload:
                        signal_payload[field] = payload[field]

                stmt = (
                    insert_fn(table)
                    .values(**signal_payload)
                    .on_conflict_do_nothing(index_elements=["stock_id", "ann_date"])
                    .returning(table.c.id)
                )
                with self.engine.begin() as conn:
                    inserted_id = conn.execute(stmt).scalar_one_or_none()
                if inserted_id is not None:
                    inserted.append(cast(int, inserted_id))
            except (AttributeError, KeyError, TypeError, ValueError, SQLAlchemyError):
                logger.exception(
                    "Failed to persist SSF change signal for stock %s",
                    payload.get("stock_id"),
                )

        return inserted

    def list_pending_ssf_change_signals(self) -> List[Any]:
        """查询尚未发送汇总提醒的 SSF 变动信号。"""
        from .model.ssf_change_signal import SSFChangeSignal

        assert self.Session is not None
        session = self.Session()
        try:
            return cast(
                List[Any],
                session.query(SSFChangeSignal)
                .filter(SSFChangeSignal.status == SSF_CHANGE_SIGNAL_STATUS_SIGNAL)
                .filter(SSFChangeSignal.alert_sent_at.is_(None))
                .order_by(SSFChangeSignal.score.desc(), SSFChangeSignal.stock_id.asc())
                .all(),
            )
        finally:
            session.close()

    def mark_ssf_change_signals_alerted(self, ids: List[int]) -> None:
        """将指定 SSF 变动信号标记为已发送提醒。"""
        from .model.ssf_change_signal import SSFChangeSignal

        if not ids:
            return

        assert self.Session is not None
        session = self.Session()
        try:
            session.query(SSFChangeSignal).filter(SSFChangeSignal.id.in_(ids)).update(
                {"alert_sent_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_monitor_targets(
        self, frequency: Optional[str] = None, enabled: Optional[bool] = None
    ) -> List[Any]:
        """
        查询监控目标列表。

        Args:
            frequency: 可选，按频率过滤 ('daily' 或 'intraday')。
            enabled: 可选，按启用状态过滤。
        Returns:
            StockMonitorTarget 对象列表。
        """
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            query = session.query(StockMonitorTarget)
            if enabled is not None:
                query = query.filter_by(enabled=enabled)
            if frequency:
                query = query.filter_by(frequency=frequency)
            return cast(List[Any], query.order_by(StockMonitorTarget.id.asc()).all())
        finally:
            session.close()

    def get_monitor_target(self, target_id: int) -> Optional[Any]:
        """按 ID 查询单个监控目标。"""
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            return session.query(StockMonitorTarget).filter_by(id=target_id).first()
        finally:
            session.close()

    def create_monitor_target(
        self,
        stock_code: str,
        market: str,
        condition: Dict[str, Any],
        note: Optional[str] = None,
        frequency: str = "daily",
        reset_mode: str = "auto",
        enabled: bool = True,
        last_state: bool = False,
    ) -> Any:
        """创建监控目标。"""
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            target = StockMonitorTarget(
                stock_code=stock_code,
                market=market,
                condition=condition,
                note=note,
                frequency=frequency,
                reset_mode=reset_mode,
                enabled=enabled,
                last_state=last_state,
            )
            session.add(target)
            session.commit()
            session.refresh(target)
            return target
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_monitor_target(self, target_id: int, **updates: Any) -> Optional[Any]:
        """更新监控目标。目标不存在时返回 None。"""
        from .model.stock_monitor_target import StockMonitorTarget

        allowed_fields = {
            "stock_code",
            "market",
            "condition",
            "note",
            "frequency",
            "reset_mode",
            "enabled",
            "last_state",
            "triggered_at",
        }
        invalid_fields = set(updates) - allowed_fields
        if invalid_fields:
            raise ValueError(f"不支持更新字段: {sorted(invalid_fields)}")

        assert self.Session is not None
        session = self.Session()
        try:
            target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
            if target is None:
                return None
            for key, value in updates.items():
                setattr(target, key, value)
            session.commit()
            session.refresh(target)
            return target
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_monitor_target(self, target_id: int) -> bool:
        """删除监控目标。删除成功返回 True，目标不存在返回 False。"""
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
            if target is None:
                return False
            session.delete(target)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_monitor_targets(self, frequency: Optional[str] = None) -> List[Any]:
        """
        加载所有启用的监控目标。

        Args:
            frequency: 可选，按频率过滤 ('daily' 或 'intraday')；None 则返回全部。
        Returns:
            StockMonitorTarget 对象列表。
        """
        return self.list_monitor_targets(frequency=frequency, enabled=True)

    def update_monitor_target_state(
        self,
        target_id: int,
        last_state: bool,
        triggered_at: Optional[datetime] = None,
    ) -> None:
        """
        更新监控目标的状态（边沿触发字段）。

        Args:
            target_id: 目标 ID
            last_state: 本次条件是否成立
            triggered_at: 触发时间（条件刚触发时传入，否则为 None）
        """
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
            if target is None:
                return
            target.last_state = last_state
            if triggered_at is not None:
                target.triggered_at = triggered_at
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ensure_monitor_targets_table(self) -> None:
        """建表（若不存在）。在 DAG 启动时调用一次。"""
        from .model.stock_monitor_target import StockMonitorTarget  # noqa: F401

        StockMonitorTarget.__table__.create(self.engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Blackroom record CRUD
    # ------------------------------------------------------------------

    def create_blackroom_record(
        self,
        stock_code: str,
        market: str = "A",
        ban_days: Optional[int] = None,
        start_at: Optional[datetime] = None,
        expire_at: Optional[datetime] = None,
        source: str = "manual",
        note: Optional[str] = None,
        enabled: bool = True,
    ) -> Any:
        """创建黑名单记录。

        expire_at 优先使用显式传入值；若未传入且提供了 ban_days，
        则自动计算为 (start_at 或当前时间) + ban_days 天。
        """
        from .model.blackroom_record import BlackroomRecord

        effective_start = start_at or datetime.now(timezone.utc)
        if expire_at is None and ban_days is not None:
            expire_at = effective_start + timedelta(days=ban_days)

        assert self.Session is not None
        session = self.Session()
        try:
            record = BlackroomRecord(
                stock_code=stock_code,
                market=market,
                ban_days=ban_days,
                start_at=effective_start,
                expire_at=expire_at,
                source=source,
                note=note,
                enabled=enabled,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_blackroom_record(self, record_id: int) -> Optional[Any]:
        """按 ID 查询单条黑名单记录。"""
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            return session.query(BlackroomRecord).filter_by(id=record_id).first()
        finally:
            session.close()

    def list_blackroom_records(
        self,
        market: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> List[Any]:
        """
        查询黑名单记录列表（不过滤到期时间）。

        Args:
            market: 可选，按市场过滤 ('A' / 'HK' / 'ETF')。
            enabled: 可选，按启用状态过滤。
        Returns:
            BlackroomRecord 对象列表。
        """
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            query = session.query(BlackroomRecord)
            if market is not None:
                query = query.filter_by(market=market)
            if enabled is not None:
                query = query.filter_by(enabled=enabled)
            return cast(List[Any], query.order_by(BlackroomRecord.id.asc()).all())
        finally:
            session.close()

    def list_active_blackroom_records(self, market: Optional[str] = None) -> List[Any]:
        """
        查询当前有效的黑名单记录。

        有效条件：enabled=True 且 expire_at > 当前时间。

        Args:
            market: 可选，按市场过滤。
        Returns:
            BlackroomRecord 对象列表。
        """
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            now = datetime.now(timezone.utc)
            query = (
                session.query(BlackroomRecord)
                .filter_by(enabled=True)
                .filter(BlackroomRecord.expire_at > now)
            )
            if market is not None:
                query = query.filter_by(market=market)
            return cast(List[Any], query.order_by(BlackroomRecord.id.asc()).all())
        finally:
            session.close()

    def update_blackroom_record(self, record_id: int, **updates: Any) -> Optional[Any]:
        """更新黑名单记录。记录不存在时返回 None。

        若更新包含 ban_days 或 start_at（且未显式提供 expire_at），
        则自动重新计算 expire_at = start_at + ban_days。
        """
        from .model.blackroom_record import BlackroomRecord

        allowed_fields = {
            "stock_code",
            "market",
            "ban_days",
            "start_at",
            "expire_at",
            "source",
            "note",
            "enabled",
        }
        invalid_fields = set(updates) - allowed_fields
        if invalid_fields:
            raise ValueError(f"不支持更新字段: {sorted(invalid_fields)}")

        assert self.Session is not None
        session = self.Session()
        try:
            record = session.query(BlackroomRecord).filter_by(id=record_id).first()
            if record is None:
                return None
            for key, value in updates.items():
                setattr(record, key, value)
            if (
                "ban_days" in updates or "start_at" in updates
            ) and "expire_at" not in updates:
                current_start = record.start_at
                current_ban_days = record.ban_days
                if current_start is not None and current_ban_days is not None:
                    record.expire_at = current_start + timedelta(days=current_ban_days)
                else:
                    # One or both recompute inputs are now NULL; clear stale expire_at.
                    record.expire_at = None
            session.commit()
            session.refresh(record)
            return record
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_blackroom_record(self, record_id: int) -> bool:
        """删除黑名单记录。删除成功返回 True，记录不存在返回 False。"""
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            record = session.query(BlackroomRecord).filter_by(id=record_id).first()
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ensure_blackroom_records_table(self) -> None:
        """建表（若不存在）。在 DAG 启动时调用一次。"""
        from .model.blackroom_record import BlackroomRecord  # noqa: F401

        BlackroomRecord.__table__.create(self.engine, checkfirst=True)


def get_storage(config: Optional[StorageConfig] = None) -> StorageDb:
    """
    获取当前进程的 StorageDb 单例实例(PID-scoped singleton）。

    每个进程维护自己的 StorageDb 实例和 SQLAlchemy 连接池，避免：
    1) 多进程共享连接导致的冲突
    2) 每次调用都创建新引擎/连接池导致的连接爆炸（"too many clients already"）

    Args:
        config: 可选的 StorageConfig；如果不传则使用默认配置。
                注意：如果当前进程已有实例，此参数会被忽略。
    """
    global _storage_instances
    pid = os.getpid()

    if pid not in _storage_instances:
        if config is None:
            config = StorageConfig()
        _storage_instances[pid] = StorageDb(config)
        logger.debug(f"Created new StorageDb instance for PID {pid}")

    return _storage_instances[pid]
