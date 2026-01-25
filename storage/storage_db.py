import logging
import os
import textwrap
from functools import wraps
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import psycopg2
from psycopg2.extensions import connection, cursor
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.const import (
    COL_DATE,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    AdjustType,
    PeriodType,
    SecurityType,
)
from download.dl.downloader_tushare import _TS_TO_INTERNAL_COL_MAP

from .config import StorageConfig
from .model import (
    Base,
    tb_name_daily_basic_a_stock,
    tb_name_general_info_etf,
    tb_name_general_info_ggt,
    tb_name_general_info_stock,
    tb_name_history_data_daily_a_stock_hfq,
    tb_name_history_data_daily_a_stock_qfq,
    tb_name_history_data_daily_etf_hfq,
    tb_name_history_data_daily_etf_qfq,
    tb_name_history_data_daily_hk_stock_hfq,
    tb_name_history_data_monthly_hk_stock_hfq,
    tb_name_history_data_weekly_a_stock_hfq,
    tb_name_history_data_weekly_a_stock_qfq,
    tb_name_history_data_weekly_etf_hfq,
    tb_name_history_data_weekly_etf_qfq,
    tb_name_history_data_weekly_hk_stock_hfq,
    tb_name_ingredient_300,
    tb_name_ingredient_500,
    tb_name_stk_limit_a_stock,
    tb_name_suspend_d_a_stock,
)

logger = logging.getLogger(__name__)

# PID-scoped singleton: one StorageDb instance per process to avoid connection explosion
_storage_instances: Dict[int, "StorageDb"] = {}
# Track which PIDs have already run metadata.create_all() to avoid repeated DDL checks
_metadata_initialized_pids: Set[int] = set()


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

    def save_history_data_stock(
        self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType
    ) -> bool:
        if period == PeriodType.DAILY:
            if adjust == AdjustType.QFQ:
                table_name = tb_name_history_data_daily_a_stock_qfq
            elif adjust == AdjustType.HFQ:
                table_name = tb_name_history_data_daily_a_stock_hfq
        elif period == PeriodType.WEEKLY:
            if adjust == AdjustType.QFQ:
                table_name = tb_name_history_data_weekly_a_stock_qfq
            elif adjust == AdjustType.HFQ:
                table_name = tb_name_history_data_weekly_a_stock_hfq

        df.to_sql(
            table_name,
            self.engine,
            if_exists="append",
            index=False,
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
            # 根据周期选择对应的港股表名（港股只支持后复权）
            if period == PeriodType.DAILY:
                table_name = tb_name_history_data_daily_hk_stock_hfq
            elif period == PeriodType.WEEKLY:
                table_name = tb_name_history_data_weekly_hk_stock_hfq
            elif period == PeriodType.MONTHLY:
                table_name = tb_name_history_data_monthly_hk_stock_hfq
            else:
                logger.error(f"不支持的港股数据周期: {period}")
                return False

            # 保存数据到对应的港股历史数据表
            df.to_sql(
                table_name,
                self.engine,
                if_exists="append",
                index=False,
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
            # 根据周期和复权类型选择对应的ETF表名
            if period == PeriodType.DAILY:
                if adjust == AdjustType.QFQ:
                    table_name = tb_name_history_data_daily_etf_qfq
                elif adjust == AdjustType.HFQ:
                    table_name = tb_name_history_data_daily_etf_hfq
                else:
                    logger.error(f"不支持的ETF复权类型: {adjust}")
                    return False
            elif period == PeriodType.WEEKLY:
                if adjust == AdjustType.QFQ:
                    table_name = tb_name_history_data_weekly_etf_qfq
                elif adjust == AdjustType.HFQ:
                    table_name = tb_name_history_data_weekly_etf_hfq
                else:
                    logger.error(f"不支持的ETF复权类型: {adjust}")
                    return False
            else:
                logger.error(f"不支持的ETF数据周期: {period}")
                return False

            # 保存数据到对应的ETF历史数据表
            df.to_sql(
                table_name,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

            logger.info(f"ETF历史数据保存成功: {table_name}, 数据条数: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"保存ETF历史数据失败: {str(e)}")
            return False

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

            if stock_id:
                sql = textwrap.dedent(
                    f"""\
                SELECT * FROM {table_name}
                WHERE "{COL_STOCK_ID}" = %s
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
        table_name = tb_name_daily_basic_a_stock

        try:
            # Rename columns from tushare names to internal names
            df_renamed = df.rename(columns=_TS_TO_INTERNAL_COL_MAP)
            df_renamed.to_sql(
                table_name,
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
        table_name = tb_name_stk_limit_a_stock

        try:
            # Rename columns from tushare names to internal names
            df_renamed = df.rename(columns=_TS_TO_INTERNAL_COL_MAP)
            df_renamed.to_sql(
                table_name,
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
        table_name = tb_name_suspend_d_a_stock

        try:
            # Rename columns from tushare names to internal names
            df_renamed = df.rename(columns=_TS_TO_INTERNAL_COL_MAP)
            df_renamed.to_sql(
                table_name,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )

            return True

        except Exception as e:
            logger.error(f"保存停复牌数据失败: {str(e)}")
            return False


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
