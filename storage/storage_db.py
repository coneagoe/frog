import json
import logging
import os
import re
import textwrap
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import wraps
from typing import Any, Callable, Dict, List, Literal, Optional, Set, cast
from uuid import UUID, uuid4

import pandas as pd
import psycopg2
from psycopg2.extensions import connection, cursor
from psycopg2.extras import RealDictCursor
from sqlalchemy import MetaData, Numeric, Table, and_, bindparam, create_engine, func, inspect, or_, text
from sqlalchemy.dialects.postgresql import Insert as PostgreSQLInsert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

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
    COL_ETF_ESTIMATED_TRADED_PRICE,
    COL_ETF_EXT_NAME,
    COL_ETF_ID,
    COL_ETF_NAME,
    COL_ETF_NET_FLOW_AMOUNT,
    COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    COL_ETF_NET_SHARE_CHANGE,
    COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    COL_ETF_TOTAL_SHARE,
    COL_ETF_TOTAL_SIZE,
    COL_ETF_TYPE,
    COL_EXCHANGE,
    COL_FLOAT_HOLDER_HOLD_AMOUNT,
    COL_FLOAT_HOLDER_HOLD_CHANGE,
    COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
    COL_FLOAT_HOLDER_TYPE,
    COL_FLOAT_SHARE,
    COL_FORECAST_CHANGE_MAX,
    COL_FORECAST_CHANGE_MIN,
    COL_FORECAST_TYPE,
    COL_FREE_SHARE,
    COL_FULLNAME,
    COL_HIGH,
    COL_HOLDER_NUM,
    COL_INDEX_CODE,
    COL_INDEX_NAME,
    COL_INDEX_TURNOVER_AMOUNT,
    COL_INDUSTRY,
    COL_IPO_DATE,
    COL_IS_HS,
    COL_LIST_STATUS,
    COL_LOW,
    COL_MARKET,
    COL_MGR_NAME,
    COL_MGT_FEE,
    COL_NAV,
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
from monitor.condition_validation import validate_condition
from monitor.domain_enums import (
    ForecastSSFCandidateState,
    MonitorEvaluationErrorKind,
    MonitorFrequency,
    MonitorMarket,
    MonitorResetMode,
    NotificationDeliveryState,
)
from monitor.monitor_health import sanitize_error_detail

from .config import StorageConfig
from .domain_enums import ForecastSnapshotStatus, SSFChangeSignalStatus, validate_ssf_event_types
from .model import (
    AuthToken,
    Base,
    ETFBasic,
    ETFNetFlow,
    ETFShareSize,
    ForecastSnapshotRecord,
    ForecastSnapshotRun,
    IndexDailyTurnover,
    MonitorNotification,
    User,
    tb_name_a_stock_basic,
    tb_name_blackroom_record,
    tb_name_daily_bar_diagnostics,
    tb_name_daily_basic_a_stock,
    tb_name_etf_basic,
    tb_name_etf_daily,
    tb_name_etf_net_flow,
    tb_name_etf_share_size,
    tb_name_forecast,
    tb_name_forecast_snapshot_record,
    tb_name_forecast_snapshot_run,
    tb_name_forecast_ssf_candidate,
    tb_name_general_info_etf,
    tb_name_general_info_ggt,
    tb_name_general_info_stock,
    tb_name_history_data_daily_a_stock_bfq,
    tb_name_history_data_daily_a_stock_hfq,
    tb_name_history_data_daily_a_stock_qfq,
    tb_name_history_data_daily_etf_hfq,
    tb_name_history_data_daily_etf_qfq,
    tb_name_history_data_daily_fund,
    tb_name_history_data_daily_hk_stock_bfq,
    tb_name_history_data_daily_hk_stock_hfq,
    tb_name_history_data_monthly_hk_stock_hfq,
    tb_name_history_data_weekly_a_stock_hfq,
    tb_name_history_data_weekly_a_stock_qfq,
    tb_name_history_data_weekly_etf_hfq,
    tb_name_history_data_weekly_etf_qfq,
    tb_name_history_data_weekly_hk_stock_hfq,
    tb_name_index_daily_turnover,
    tb_name_ingredient_300,
    tb_name_ingredient_500,
    tb_name_paper_account_snapshots,
    tb_name_paper_accounts,
    tb_name_paper_cash_ledger,
    tb_name_paper_corporate_actions,
    tb_name_paper_etf_eligibility,
    tb_name_paper_ledger_rebuilds,
    tb_name_paper_matching_runs,
    tb_name_paper_order_events,
    tb_name_paper_orders,
    tb_name_paper_pending_settlement,
    tb_name_paper_position_lots,
    tb_name_paper_position_round_trips,
    tb_name_paper_positions,
    tb_name_paper_trade_validity_checks,
    tb_name_paper_trades,
    tb_name_paper_valuation_gaps,
    tb_name_ssf_change_signal,
    tb_name_stk_holdernumber,
    tb_name_stk_limit_a_stock,
    tb_name_stock_monitor_target,
    tb_name_suspend_d_a_stock,
    tb_name_top10_floatholders,
)


def __getattr__(name: str) -> Any:
    """Lazily expose paper-trading collaborators without an import cycle."""
    if name == "ETFEligibilityService":
        from paper_trading.services.etf_eligibility_service import ETFEligibilityService

        return ETFEligibilityService
    if name == "PaperTradingRepository":
        from paper_trading.storage.repository import PaperTradingRepository

        return PaperTradingRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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

COL_MAP_FORECAST = {
    "ts_code": COL_STOCK_ID,
    "ann_date": COL_ANN_DATE,
    "end_date": COL_END_DATE,
    "type": COL_FORECAST_TYPE,
    "p_change_min": COL_FORECAST_CHANGE_MIN,
    "p_change_max": COL_FORECAST_CHANGE_MAX,
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


COL_MAP_ETF_SHARE_SIZE = {
    "ts_code": COL_ETF_ID,
    "trade_date": COL_DATE,
    "close": COL_CLOSE,
    "nav": COL_NAV,
    "total_share": COL_ETF_TOTAL_SHARE,
    "total_size": COL_ETF_TOTAL_SIZE,
}


COL_MAP_INDEX_DAILY_TURNOVER = {
    "ts_code": COL_INDEX_CODE,
    "trade_date": COL_DATE,
    "close": COL_CLOSE,
    "amount": COL_AMOUNT,
}


COL_MAP_ETF_NET_FLOW = {
    "ts_code": COL_ETF_ID,
    "trade_date": COL_DATE,
    "total_share": COL_ETF_TOTAL_SHARE,
    "prev_effective_total_share": COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    "net_share_change": COL_ETF_NET_SHARE_CHANGE,
    "estimated_traded_price": COL_ETF_ESTIMATED_TRADED_PRICE,
    "net_flow_amount": COL_ETF_NET_FLOW_AMOUNT,
    "index_code": COL_INDEX_CODE,
    "index_turnover_amount": COL_INDEX_TURNOVER_AMOUNT,
    "net_flow_to_index_turnover_ratio": COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
}


# PID-scoped singleton: one StorageDb instance per process to avoid connection explosion
_storage_instances: Dict[int, "StorageDb"] = {}
# Track which PIDs have already run metadata.create_all() to avoid repeated DDL checks
_metadata_initialized_pids: Set[int] = set()


_ENUM_GOVERNED_PAPER_TRADING_TABLES = {
    tb_name_paper_accounts,
    tb_name_paper_cash_ledger,
    tb_name_paper_corporate_actions,
    tb_name_paper_positions,
    tb_name_paper_position_lots,
    tb_name_paper_orders,
    tb_name_paper_order_events,
    tb_name_paper_trades,
    tb_name_paper_position_round_trips,
    tb_name_paper_matching_runs,
    tb_name_paper_trade_validity_checks,
    tb_name_paper_pending_settlement,
    tb_name_paper_ledger_rebuilds,
    tb_name_paper_etf_eligibility,
    tb_name_blackroom_record,
    tb_name_daily_bar_diagnostics,
    tb_name_forecast_snapshot_record,
    tb_name_forecast_snapshot_run,
    tb_name_ssf_change_signal,
    tb_name_stock_monitor_target,
    tb_name_forecast_ssf_candidate,
}

_PAPER_TRADING_TABLES_WITH_GOVERNED_FOREIGN_KEYS = {
    tb_name_paper_account_snapshots,
    tb_name_paper_valuation_gaps,
    tb_name_paper_order_events,
}
_PAPER_SNAPSHOT_SERIES_LOCK_KEY = "paper_account_snapshots.nav_series"
_PAPER_SNAPSHOT_NAV_COLUMNS = {
    "net_asset_value": "NUMERIC(30, 12)",
    "share_count": "NUMERIC(30, 12)",
    "cumulative_deposit": "NUMERIC(30, 12)",
    "cumulative_withdrawal": "NUMERIC(30, 12)",
    "net_cash_flow": "NUMERIC(30, 12)",
    "pending_settlement": "NUMERIC(30, 12) NOT NULL DEFAULT 0",
}
_SQLITE_PAPER_SNAPSHOT_SERIES_COLUMNS = {
    "point_type": "VARCHAR(20) NOT NULL DEFAULT 'trading'",
    "event_at": "DATETIME",
    "quality_status": "VARCHAR(20) NOT NULL DEFAULT 'valid'",
    "invalid_reason": "TEXT",
}
_PAPER_ACCOUNT_REPAIR_REASON_TYPE = "paper_account_migration_repair_reason"
_PAPER_ACCOUNT_REPAIR_REASON_COLUMN = "migration_repair_reason"
_SQLITE_PAPER_ACCOUNT_REPAIR_REASON_DDL = "VARCHAR(40)"
_SQLITE_PAPER_REPLAY_PROVENANCE_TABLES = (
    tb_name_paper_cash_ledger,
    tb_name_paper_trades,
    tb_name_paper_corporate_actions,
    tb_name_paper_account_snapshots,
)
_PAPER_ACCOUNT_ACCOUNTING_COLUMNS = (
    "initial_cash",
    "share_count",
    "net_asset_value",
    "cumulative_deposit",
    "cumulative_withdrawal",
    "realized_pnl",
)
_PAPER_SQLITE_PRECISION_COLUMNS = {
    tb_name_paper_accounts: _PAPER_ACCOUNT_ACCOUNTING_COLUMNS,
    tb_name_paper_cash_ledger: ("amount", "net_asset_value", "share_delta", "rounding_residual"),
    tb_name_paper_corporate_actions: (
        "cash_delta",
        "quantity_delta",
        "before_quantity",
        "after_quantity",
        "before_cost_amount",
        "after_cost_amount",
        "before_cash_available",
        "after_cash_available",
    ),
    tb_name_paper_positions: ("cost_amount", "realized_pnl"),
    tb_name_paper_position_lots: ("cost_price",),
    tb_name_paper_orders: ("limit_price", "frozen_cash"),
    tb_name_paper_trade_validity_checks: (
        "input_price",
        "daily_low",
        "daily_high",
        "limit_up_price",
        "limit_down_price",
    ),
    tb_name_paper_trades: ("price", "amount", "fees"),
    tb_name_paper_position_round_trips: ("entry_amount", "exit_amount", "fees", "realized_pnl", "return_pct"),
    tb_name_paper_pending_settlement: ("amount",),
    tb_name_paper_account_snapshots: (
        "cash_available",
        "cash_frozen",
        "market_value",
        "total_assets",
        "realized_pnl",
        "unrealized_pnl",
        "net_asset_value",
        "share_count",
        "cumulative_deposit",
        "cumulative_withdrawal",
        "net_cash_flow",
        "pending_settlement",
    ),
}
_NUMERIC_TYPE_RE = re.compile(r"numeric\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE)


def _numeric_precision_scale(type_sql: str) -> tuple[int, int]:
    match = _NUMERIC_TYPE_RE.fullmatch(type_sql.strip())
    if match is None:
        raise ValueError(f"unsupported numeric type: {type_sql}")
    return int(match.group(1)), int(match.group(2))


_PAPER_SNAPSHOT_ACCOUNTING_COLUMNS = (
    "cash_available",
    "cash_frozen",
    "market_value",
    "total_assets",
    "realized_pnl",
    "unrealized_pnl",
    "net_asset_value",
    "share_count",
    "cumulative_deposit",
    "cumulative_withdrawal",
    "net_cash_flow",
    "pending_settlement",
)
_LEGACY_CHRONOLOGY_SOURCES = (
    (tb_name_paper_account_snapshots, ("event_at", "created_at"), ("trade_date",)),
    (tb_name_paper_cash_ledger, ("occurred_at",), ("trade_date",)),
    (tb_name_paper_trades, ("trade_time",), ("trade_date",)),
    (tb_name_paper_corporate_actions, ("event_at",), ("affected_start_date", "affected_end_date")),
    (tb_name_paper_orders, ("created_at",), ("trade_date",)),
    (tb_name_paper_position_lots, (), ("buy_trade_date",)),
    (tb_name_paper_position_round_trips, (), ("open_trade_date", "close_trade_date")),
    (tb_name_paper_matching_runs, (), ("trade_date",)),
    (tb_name_paper_trade_validity_checks, (), ("trade_date",)),
)


def _non_enum_governed_paper_trading_tables(dialect: Any) -> list[Any]:
    tables = list(Base.metadata.sorted_tables)
    if dialect.name != "postgresql":
        return tables

    excluded_tables = _ENUM_GOVERNED_PAPER_TRADING_TABLES | _PAPER_TRADING_TABLES_WITH_GOVERNED_FOREIGN_KEYS
    return [table for table in tables if table.name not in excluded_tables]


def _has_current_schema_table(bind: Any, table_name: str) -> bool:
    if getattr(bind, "dialect", None) is not None and bind.dialect.name != "postgresql":
        return cast(bool, inspect(bind).has_table(table_name))
    statement = text(
        "SELECT EXISTS ("
        "SELECT 1 FROM pg_class AS c "
        "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE n.nspname = current_schema() AND c.relname = :table_name"
        ")"
    )
    if hasattr(bind, "execute"):
        return cast(bool, bind.execute(statement, {"table_name": table_name}).scalar_one())
    with bind.connect() as connection:
        return cast(bool, connection.execute(statement, {"table_name": table_name}).scalar_one())


def _current_schema_columns(bind: Any, table_name: str) -> set[str]:
    statement = text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :table_name"
    )
    if hasattr(bind, "execute"):
        return set(bind.execute(statement, {"table_name": table_name}).scalars())
    with bind.connect() as connection:
        return set(connection.execute(statement, {"table_name": table_name}).scalars())


def _has_paper_account_owner_foreign_key(bind: Any) -> bool:
    if bind.dialect.name != "postgresql":
        return False
    inspector = inspect(bind)
    return any(
        foreign_key["constrained_columns"] == ["owner_user_id"] and foreign_key["referred_table"] == "users"
        for foreign_key in inspector.get_foreign_keys(tb_name_paper_accounts)
    )


def _has_verified_auth_user(bind: Any) -> bool:
    if not _has_current_schema_table(bind, "users"):
        return False
    statement = text("SELECT EXISTS (SELECT 1 FROM users WHERE email_verified_at IS NOT NULL)")
    if hasattr(bind, "execute"):
        return cast(bool, bind.execute(statement).scalar_one())
    with bind.connect() as connection:
        return cast(bool, connection.execute(statement).scalar_one())


# Tables keyed by ETF/fund code instead of stock code.
ETF_ID_TABLES: Set[str] = {
    tb_name_etf_daily,
    tb_name_history_data_daily_fund,
}


def get_table_name(security_type: SecurityType, period: PeriodType, adjust: AdjustType) -> str:
    if security_type == SecurityType.STOCK:
        if period == PeriodType.DAILY:
            if adjust == AdjustType.BFQ:
                return tb_name_history_data_daily_a_stock_bfq
            elif adjust == AdjustType.QFQ:
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
        if period == PeriodType.DAILY and adjust == AdjustType.BFQ:
            return tb_name_history_data_daily_hk_stock_bfq
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
            Base.metadata.create_all(self.engine, tables=_non_enum_governed_paper_trading_tables(self.engine.dialect))
            self.ensure_a_stock_basic_schema()
            self.ensure_blackroom_records_table()
            self.ensure_paper_trading_schema()
            _metadata_initialized_pids.add(pid)

    def ensure_a_stock_basic_schema(self) -> None:
        inspector = inspect(self.engine)
        if not inspector.has_table(tb_name_a_stock_basic):
            return

        columns = inspector.get_columns(tb_name_a_stock_basic)
        target_column = next((column for column in columns if column["name"] == COL_ACT_NAME), None)
        if target_column is None:
            return

        length = getattr(target_column["type"], "length", None)
        if length is None or length >= 100:
            return

        with self.engine.begin() as connection:
            connection.execute(
                text(f'ALTER TABLE "{tb_name_a_stock_basic}" ALTER COLUMN "{COL_ACT_NAME}" TYPE VARCHAR(100)')
            )

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

    def _normalize_code_column(self, df: pd.DataFrame, code_column: Optional[str]) -> pd.DataFrame:
        if code_column and code_column in df.columns:
            df[code_column] = df[code_column].astype("string").str.split(".", n=1).str[0]
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

    def _get_history_table_name(self, security_type: SecurityType, period: PeriodType, adjust: AdjustType) -> str:
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

    def save_history_data_stock(self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType) -> bool:
        table_name = self._get_history_table_name(SecurityType.STOCK, period, adjust)
        self._write_dataframe(
            df,
            table_name,
            if_exists="append",
            method="multi",
        )

        return True

    def save_history_data_hk_stock(self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType) -> bool:
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
                table_name = self._get_history_table_name(SecurityType.HK_GGT_STOCK, period, adjust)
            except ValueError:
                logger.error(f"不支持的港股数据周期或复权类型: period={period}, adjust={adjust}")
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
                table_name = self._get_history_table_name(SecurityType.ETF, period, adjust)
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

            logger.info(f"基金日线行情数据保存成功: {tb_name_history_data_daily_fund}, 数据条数: {len(prepared)}")
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
        df.to_sql(tb_name_general_info_stock, self.engine, if_exists="replace", index=False)
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

    def save_general_info_etf(self, df: pd.DataFrame, table_name: str = tb_name_general_info_etf) -> bool:
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

    def load_general_info_etf(self, table_name: str = tb_name_general_info_etf) -> pd.DataFrame:
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
        df.to_sql(tb_name_general_info_ggt, self.engine, if_exists="replace", index=False)
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

            df.to_sql(tb_name_ingredient_300, self.engine, if_exists="replace", index=False)
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

            df.to_sql(tb_name_ingredient_500, self.engine, if_exists="replace", index=False)
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
                if adjust == AdjustType.BFQ:
                    table_name = tb_name_history_data_daily_a_stock_bfq
                elif adjust == AdjustType.QFQ:
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
            logger.info(f"股票历史数据加载成功: {stock_id}, 周期: {period}, 复权: {adjust}, 数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载股票历史数据失败: {stock_id}, 周期: {period}, 复权: {adjust}, 错误: {str(e)}")
            return pd.DataFrame()

    def load_latest_history_data_stock(self, stock_id: str, adjust: AdjustType, end_date: Optional[str] = None):
        table_name = self._get_history_table_name(SecurityType.STOCK, PeriodType.DAILY, adjust)
        sql = f'SELECT * FROM {table_name} WHERE "{COL_STOCK_ID}" = %s'
        params: List[Any] = [stock_id]
        if end_date:
            sql += f' AND "{COL_DATE}" <= %s'
            params.append(end_date)
        sql += f' ORDER BY "{COL_DATE}" DESC LIMIT 1'
        df = pd.read_sql(sql, self.engine, params=tuple(params))
        return None if df.empty else df.iloc[0]

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
            adjust: 复权类型（日线支持BFQ/HFQ，周/月线仅支持HFQ）
            start_date: 开始日期（可选，格式：YYYY-MM-DD）
            end_date: 结束日期（可选，格式：YYYY-MM-DD）

        Returns:
            pd.DataFrame: 港股通成分股历史数据，如果表不存在或加载失败则返回空DataFrame
        """
        try:
            try:
                table_name = self._get_history_table_name(SecurityType.HK_GGT_STOCK, period, adjust)
            except ValueError:
                logger.error(f"不支持的港股通数据周期或复权类型: {period}, {adjust}")
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
            logger.error(f"加载港股通成分股历史数据失败: {stock_id}, 周期: {period}, 复权: {adjust}, 错误: {str(e)}")
            return pd.DataFrame()

    def load_latest_history_data_stock_hk_ggt(self, stock_id: str, adjust: AdjustType, end_date: Optional[str] = None):
        table_name = self._get_history_table_name(SecurityType.HK_GGT_STOCK, PeriodType.DAILY, adjust)
        sql = f'SELECT * FROM {table_name} WHERE "{COL_STOCK_ID}" = %s'
        params: List[Any] = [stock_id]
        if end_date:
            sql += f' AND "{COL_DATE}" <= %s'
            params.append(end_date)
        sql += f' ORDER BY "{COL_DATE}" DESC LIMIT 1'
        df = pd.read_sql(sql, self.engine, params=tuple(params))
        return None if df.empty else df.iloc[0]

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
            logger.info(f"ETF历史数据加载成功: {etf_id}, 周期: {period}, 复权: {adjust}, 数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载ETF历史数据失败: {etf_id}, 周期: {period}, 复权: {adjust}, 错误: {str(e)}")
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
    def get_last_record(self, table_name: str, stock_id: Optional[str] = None) -> Optional[dict]:
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
            logger.error(f"获取最新记录失败 - 表名: {table_name}, 股票代码: {stock_id}, 错误: {str(e)}")
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
            df[COL_DATE] = pd.to_datetime(df[COL_DATE], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
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
            df[COL_DATE] = pd.to_datetime(df[COL_DATE], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
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
            df[COL_DATE] = pd.to_datetime(df[COL_DATE], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
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
                df[col] = pd.to_datetime(df[col], format="%Y%m%d", errors="coerce").dt.date

            if self.engine is None:
                raise ConnectionError("SQLAlchemy引擎未初始化")

            table = Base.metadata.tables[tb_name_top10_floatholders]
            records = df.to_dict(orient="records")
            if not records:
                return True

            primary_keys = list(table.primary_key.columns.keys())
            stmt: PostgreSQLInsert | SQLiteInsert
            if self.engine.dialect.name == "postgresql":
                stmt = pg_insert(table).values(records).on_conflict_do_nothing(index_elements=primary_keys)
            elif self.engine.dialect.name == "sqlite":
                stmt = sqlite_insert(table).values(records).on_conflict_do_nothing(index_elements=primary_keys)
            else:
                raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")

            with self.engine.begin() as conn:
                conn.execute(stmt)

            return True

        except Exception as e:
            logger.error(f"保存前十大流通股东数据失败: {str(e)}")
            return False

    def ensure_forecasts_table(self) -> None:
        from .model.forecast import Forecast  # noqa: F401

        Forecast.__table__.create(self.engine, checkfirst=True)

    def ensure_forecast_ssf_candidates_table(self) -> None:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate  # noqa: F401

        ForecastSSFCandidate.__table__.create(self.engine, checkfirst=True)

    def ensure_forecast_snapshot_tables(self) -> None:
        if self.engine is None:
            raise ConnectionError("SQLAlchemy引擎未初始化")
        if self.engine.dialect.name == "postgresql":
            return
        ForecastSnapshotRun.__table__.create(self.engine, checkfirst=True)
        ForecastSnapshotRecord.__table__.create(self.engine, checkfirst=True)

    def acquire_forecast_snapshot_run(
        self,
        report_end_date: date,
        announcement_start_date: date,
        announcement_end_date: date,
    ) -> ForecastSnapshotRun:
        self.ensure_forecast_snapshot_tables()
        assert self.Session is not None

        completed_run_id: int | None = None
        try:
            with self.Session.begin() as session:
                self._lock_forecast_snapshot_range(
                    session, report_end_date, announcement_start_date, announcement_end_date
                )
                completed = self._get_completed_forecast_snapshot_run(
                    session, report_end_date, announcement_start_date, announcement_end_date
                )
                if completed is not None:
                    completed_run_id = run_id = completed.id
                else:
                    active_run = self._get_active_forecast_snapshot_run(
                        session, report_end_date, announcement_start_date, announcement_end_date
                    )
                    if active_run is not None:
                        raise StorageError("forecast snapshot is already running for requested range")
                    completed = self._get_completed_forecast_snapshot_run(
                        session, report_end_date, announcement_start_date, announcement_end_date
                    )
                    if completed is not None:
                        completed_run_id = run_id = completed.id
                    else:
                        max_attempt = (
                            session.query(func.max(ForecastSnapshotRun.attempt))
                            .filter_by(
                                report_end_date=report_end_date,
                                announcement_start_date=announcement_start_date,
                                announcement_end_date=announcement_end_date,
                            )
                            .scalar()
                        )
                        run = ForecastSnapshotRun(
                            report_end_date=report_end_date,
                            announcement_start_date=announcement_start_date,
                            announcement_end_date=announcement_end_date,
                            attempt=(max_attempt or 0) + 1,
                            status=ForecastSnapshotStatus.RUNNING.value,
                            requested_date_count=(announcement_end_date - announcement_start_date).days + 1,
                        )
                        session.add(run)
                        session.flush()
                        run_id = run.id
        except IntegrityError:
            completed = self.get_completed_forecast_snapshot_run(
                report_end_date, announcement_start_date, announcement_end_date
            )
            if completed is not None:
                return completed
            raise StorageError("forecast snapshot is already running for requested range") from None

        return self._get_forecast_snapshot_run(completed_run_id or run_id)

    def save_forecast_snapshot_records(
        self, run_id: int, records: list[dict[str, object]], counts: dict[str, int]
    ) -> None:
        self.ensure_forecast_snapshot_tables()
        assert self.Session is not None
        with self.Session.begin() as session:
            run = session.get(ForecastSnapshotRun, run_id)
            if run is None:
                raise DataNotFoundError(f"forecast snapshot run {run_id} not found")
            if run.status != ForecastSnapshotStatus.RUNNING.value:
                raise StorageError("forecast snapshot records can only be saved for a running run")
            if records:
                session.execute(
                    ForecastSnapshotRecord.__table__.insert(), [dict(record, run_id=run_id) for record in records]
                )
            self._set_forecast_snapshot_counts(run, counts)

    def complete_forecast_snapshot_run(self, run_id: int, counts: dict[str, int]) -> ForecastSnapshotRun:
        self.ensure_forecast_snapshot_tables()
        assert self.Session is not None
        with self.Session.begin() as session:
            run = session.get(ForecastSnapshotRun, run_id)
            if run is None:
                raise DataNotFoundError(f"forecast snapshot run {run_id} not found")
            self._lock_forecast_snapshot_range(
                session, run.report_end_date, run.announcement_start_date, run.announcement_end_date
            )
            if run.status != ForecastSnapshotStatus.RUNNING.value:
                raise StorageError("forecast snapshot run is not running")
            self._validate_forecast_snapshot_final_counts(counts)
            if counts["covered_date_count"] != run.requested_date_count:
                raise StorageError("forecast snapshot coverage does not match requested date count")
            self._set_forecast_snapshot_counts(run, counts)
            run.status = ForecastSnapshotStatus.COMPLETED.value
            run.completed_at = datetime.now(timezone.utc)

        return self._get_forecast_snapshot_run(run_id)

    def fail_forecast_snapshot_run(self, run_id: int, failure_detail: str) -> ForecastSnapshotRun:
        self.ensure_forecast_snapshot_tables()
        assert self.Session is not None
        with self.Session.begin() as session:
            run = session.get(ForecastSnapshotRun, run_id)
            if run is None:
                raise DataNotFoundError(f"forecast snapshot run {run_id} not found")
            self._lock_forecast_snapshot_range(
                session, run.report_end_date, run.announcement_start_date, run.announcement_end_date
            )
            if run.status != ForecastSnapshotStatus.RUNNING.value:
                raise StorageError("forecast snapshot run is not running")
            run.status = ForecastSnapshotStatus.FAILED.value
            run.failed_at = datetime.now(timezone.utc)
            run.failure_detail = failure_detail

        return self._get_forecast_snapshot_run(run_id)

    @staticmethod
    def _lock_forecast_snapshot_range(
        session: Any, report_end_date: date, announcement_start_date: date, announcement_end_date: date
    ) -> None:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:range_identity AS text), 0))"),
                {
                    "range_identity": (
                        f"{report_end_date.isoformat()}:{announcement_start_date.isoformat()}:"
                        f"{announcement_end_date.isoformat()}"
                    )
                },
            )

    def get_completed_forecast_snapshot_run(
        self,
        report_end_date: date,
        announcement_start_date: date,
        announcement_end_date: date,
    ) -> ForecastSnapshotRun | None:
        self.ensure_forecast_snapshot_tables()
        assert self.Session is not None
        with self.Session() as session:
            return self._get_completed_forecast_snapshot_run(
                session, report_end_date, announcement_start_date, announcement_end_date
            )

    def get_latest_completed_forecast_snapshot_run(self, as_of_date: date) -> ForecastSnapshotRun | None:
        self.ensure_forecast_snapshot_tables()
        assert self.Session is not None
        with self.Session() as session:
            return (
                session.query(ForecastSnapshotRun)
                .filter(
                    ForecastSnapshotRun.status == ForecastSnapshotStatus.COMPLETED.value,
                    ForecastSnapshotRun.announcement_end_date <= as_of_date,
                )
                .order_by(
                    ForecastSnapshotRun.announcement_end_date.desc(),
                    ForecastSnapshotRun.completed_at.desc(),
                    ForecastSnapshotRun.id.desc(),
                )
                .first()
            )

    def load_selected_forecast_snapshot_records(self, run_id: int, as_of_date: date) -> pd.DataFrame:
        self.ensure_forecast_snapshot_tables()
        columns = [
            COL_STOCK_ID,
            COL_END_DATE,
            COL_ANN_DATE,
            COL_FORECAST_TYPE,
            COL_FORECAST_CHANGE_MIN,
            COL_FORECAST_CHANGE_MAX,
            "source_order",
        ]
        sql = text(
            f"""
            WITH ranked AS (
                SELECT r.*, ROW_NUMBER() OVER (
                    PARTITION BY r.ts_code
                    ORDER BY r.announcement_date DESC, r.source_order DESC
                ) AS revision_rank
                FROM {tb_name_forecast_snapshot_record} r
                JOIN {tb_name_forecast_snapshot_run} run ON run.id = r.run_id
                WHERE r.run_id = :run_id
                  AND r.report_end_date = run.report_end_date
                  AND r.announcement_date <= :as_of_date
                  AND run.status = 'completed'
                  AND run.announcement_end_date <= :as_of_date
            )
            SELECT
                ts_code,
                report_end_date,
                announcement_date,
                forecast_type,
                growth_min,
                growth_max,
                source_order
            FROM ranked
            WHERE revision_rank = 1
            ORDER BY ts_code
            """
        )
        params: dict[str, int | date] = {"run_id": run_id, "as_of_date": as_of_date}
        records = pd.read_sql(sql, self.engine, params=params).rename(
            columns={
                "ts_code": COL_STOCK_ID,
                "report_end_date": COL_END_DATE,
                "announcement_date": COL_ANN_DATE,
                "forecast_type": COL_FORECAST_TYPE,
                "growth_min": COL_FORECAST_CHANGE_MIN,
                "growth_max": COL_FORECAST_CHANGE_MAX,
            }
        )
        records = records.reindex(columns=columns)
        records[COL_STOCK_ID] = records[COL_STOCK_ID].astype(str).str.split(".").str[0]
        for column in [COL_END_DATE, COL_ANN_DATE]:
            records[column] = pd.to_datetime(records[column], errors="raise").dt.date
        return records

    def list_forecast_snapshot_records(self, run_id: int) -> list[ForecastSnapshotRecord]:
        self.ensure_forecast_snapshot_tables()
        assert self.Session is not None
        with self.Session() as session:
            return (
                session.query(ForecastSnapshotRecord)
                .filter_by(run_id=run_id)
                .order_by(ForecastSnapshotRecord.announcement_date, ForecastSnapshotRecord.source_order)
                .all()
            )

    @staticmethod
    def _set_forecast_snapshot_counts(run: ForecastSnapshotRun, counts: dict[str, int]) -> None:
        for field in (
            "covered_date_count",
            "source_row_count",
            "record_count",
            "duplicate_record_count",
            "same_day_conflict_count",
        ):
            if field in counts:
                setattr(run, field, counts[field])

    @staticmethod
    def _validate_forecast_snapshot_final_counts(counts: dict[str, int]) -> None:
        required_fields = (
            "covered_date_count",
            "source_row_count",
            "record_count",
            "duplicate_record_count",
            "same_day_conflict_count",
        )
        missing_fields = [field for field in required_fields if field not in counts]
        if missing_fields:
            raise StorageError(f"forecast snapshot final counts are missing: {', '.join(missing_fields)}")

    @staticmethod
    def _get_completed_forecast_snapshot_run(
        session: Any, report_end_date: date, announcement_start_date: date, announcement_end_date: date
    ) -> ForecastSnapshotRun | None:
        return cast(
            ForecastSnapshotRun | None,
            session.query(ForecastSnapshotRun)
            .filter_by(
                report_end_date=report_end_date,
                announcement_start_date=announcement_start_date,
                announcement_end_date=announcement_end_date,
                status=ForecastSnapshotStatus.COMPLETED.value,
            )
            .order_by(ForecastSnapshotRun.completed_at.desc(), ForecastSnapshotRun.id.desc())
            .first(),
        )

    @staticmethod
    def _get_active_forecast_snapshot_run(
        session: Any, report_end_date: date, announcement_start_date: date, announcement_end_date: date
    ) -> ForecastSnapshotRun | None:
        return cast(
            ForecastSnapshotRun | None,
            session.query(ForecastSnapshotRun)
            .filter_by(
                report_end_date=report_end_date,
                announcement_start_date=announcement_start_date,
                announcement_end_date=announcement_end_date,
                status=ForecastSnapshotStatus.RUNNING.value,
            )
            .first(),
        )

    def _get_forecast_snapshot_run(self, run_id: int) -> ForecastSnapshotRun:
        assert self.Session is not None
        with self.Session() as session:
            run = session.get(ForecastSnapshotRun, run_id)
            if run is None:
                raise DataNotFoundError(f"forecast snapshot run {run_id} not found")
            return run

    def upsert_forecast_ssf_candidate(
        self,
        stock_code: str,
        market: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        monitor_target_id: int | None,
    ) -> Any:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate

        self._validate_monitor_enum_value(market, "market", MonitorMarket)
        self._validate_monitor_enum_value(state, "state", ForecastSSFCandidateState)
        assert self.engine is not None
        with self.engine.begin() as conn:
            self._upsert_forecast_ssf_candidate_in_transaction(
                conn,
                ForecastSSFCandidate.__table__,
                stock_code,
                market,
                report_end_date,
                state,
                state_reason,
                evidence,
                monitor_target_id,
            )

        assert self.Session is not None
        session = self.Session()
        try:
            return session.query(ForecastSSFCandidate).filter_by(stock_code=stock_code).one()
        finally:
            session.close()

    def _upsert_forecast_ssf_candidate_in_transaction(
        self,
        conn: Any,
        table: Any,
        stock_code: str,
        market: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        monitor_target_id: int | None,
    ) -> None:
        record = {
            "stock_code": stock_code,
            "market": market,
            "report_end_date": report_end_date,
            "state": state,
            "state_reason": state_reason,
            "evidence": evidence,
            "monitor_target_id": monitor_target_id,
        }
        update_fields = [
            "market",
            "report_end_date",
            "state",
            "state_reason",
            "evidence",
            "monitor_target_id",
        ]
        if self.engine.dialect.name == "postgresql":
            postgres_insert_stmt = pg_insert(table).values(record)
            stmt: PostgreSQLInsert | SQLiteInsert = postgres_insert_stmt.on_conflict_do_update(
                index_elements=["stock_code"],
                set_={field: getattr(postgres_insert_stmt.excluded, field) for field in update_fields}
                | {"updated_at": func.now()},
            )
        elif self.engine.dialect.name == "sqlite":
            sqlite_insert_stmt = sqlite_insert(table).values(record)
            stmt = sqlite_insert_stmt.on_conflict_do_update(
                index_elements=["stock_code"],
                set_={field: getattr(sqlite_insert_stmt.excluded, field) for field in update_fields}
                | {"updated_at": func.now()},
            )
        else:
            raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")
        conn.execute(stmt)

    def list_forecast_ssf_candidates(self) -> list[Any]:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate

        assert self.Session is not None
        session = self.Session()
        try:
            return cast(list[Any], session.query(ForecastSSFCandidate).order_by(ForecastSSFCandidate.stock_code).all())
        finally:
            session.close()

    def get_forecast_ssf_candidate_for_target(self, target_id: int) -> Any | None:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate

        assert self.Session is not None
        session = self.Session()
        try:
            matches = session.query(ForecastSSFCandidate).filter_by(monitor_target_id=target_id).all()
        finally:
            session.close()
        if len(matches) > 1:
            raise ValueError(f"multiple candidates found for monitor_target_id={target_id}")
        return matches[0] if matches else None

    def load_a_stock_listing_status(self, stock_codes: list[str]) -> pd.DataFrame:
        columns = [COL_STOCK_ID, COL_STOCK_NAME, COL_LIST_STATUS, COL_DELISTING_DATE]
        if not stock_codes:
            return pd.DataFrame(columns=columns)
        stmt = text(
            f'SELECT "{COL_STOCK_ID}", "{COL_STOCK_NAME}", "{COL_LIST_STATUS}", "{COL_DELISTING_DATE}" '
            f'FROM {tb_name_a_stock_basic} WHERE "{COL_STOCK_ID}" IN :stock_codes'
        ).bindparams(bindparam("stock_codes", expanding=True))
        return pd.read_sql(stmt, self.engine, params={"stock_codes": stock_codes})  # type: ignore[arg-type]

    def save_forecasts(self, df: pd.DataFrame) -> bool:
        prepared = df.rename(columns=COL_MAP_FORECAST).copy()
        required = [
            COL_STOCK_ID,
            COL_ANN_DATE,
            COL_END_DATE,
            COL_FORECAST_TYPE,
            COL_FORECAST_CHANGE_MIN,
            COL_FORECAST_CHANGE_MAX,
        ]
        missing = set(required) - set(prepared.columns)
        if missing:
            raise ValueError(f"forecast 缺少字段: {sorted(missing)}")
        prepared = prepared[required]
        prepared[COL_STOCK_ID] = prepared[COL_STOCK_ID].astype(str).str.split(".").str[0]
        for column in [COL_ANN_DATE, COL_END_DATE]:
            prepared[column] = pd.to_datetime(prepared[column], errors="raise").dt.date
        for column in [COL_FORECAST_CHANGE_MIN, COL_FORECAST_CHANGE_MAX]:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

        from .model.forecast import Forecast

        table = Forecast.__table__
        records = prepared.to_dict(orient="records")
        if not records:
            return True
        stmt: PostgreSQLInsert | SQLiteInsert
        if self.engine.dialect.name == "postgresql":
            postgres_insert = pg_insert(table).values(records)
            stmt = postgres_insert.on_conflict_do_update(
                index_elements=list(table.primary_key.columns.keys()),
                set_={column.name: getattr(postgres_insert.excluded, column.name) for column in table.columns},
            )
        elif self.engine.dialect.name == "sqlite":
            sqlite_insert_stmt = sqlite_insert(table).values(records)
            stmt = sqlite_insert_stmt.on_conflict_do_update(
                index_elements=list(table.primary_key.columns.keys()),
                set_={column.name: getattr(sqlite_insert_stmt.excluded, column.name) for column in table.columns},
            )
        else:
            raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")
        with self.engine.begin() as conn:
            conn.execute(stmt)
        return True

    def load_active_forecast_candidates(self, as_of_date: date) -> pd.DataFrame:
        sql = text(
            f"""
            WITH active_period AS (
                SELECT MAX(\"{COL_END_DATE}\") AS end_date
                FROM {tb_name_forecast}
                WHERE \"{COL_END_DATE}\" <= :as_of_date
            ), latest AS (
                SELECT \"{COL_STOCK_ID}\", MAX(\"{COL_ANN_DATE}\") AS ann_date
                FROM {tb_name_forecast}
                WHERE \"{COL_END_DATE}\" = (SELECT end_date FROM active_period)
                GROUP BY \"{COL_STOCK_ID}\"
            )
            SELECT f.*
            FROM {tb_name_forecast} f
            JOIN latest l ON l.\"{COL_STOCK_ID}\" = f.\"{COL_STOCK_ID}\" AND l.ann_date = f.\"{COL_ANN_DATE}\"
            JOIN {tb_name_a_stock_basic} b ON b.\"{COL_STOCK_ID}\" = f.\"{COL_STOCK_ID}\"
            WHERE f.\"{COL_END_DATE}\" = (SELECT end_date FROM active_period)
              AND f.\"{COL_FORECAST_TYPE}\" = '预增'
              AND f.\"{COL_FORECAST_CHANGE_MIN}\" >= 50
              AND b.\"{COL_LIST_STATUS}\" = 'L'
              AND b.\"{COL_STOCK_NAME}\" NOT LIKE '%ST%'
            ORDER BY f.\"{COL_STOCK_ID}\"
            """
        )
        result = pd.read_sql(sql, self.engine, params={"as_of_date": as_of_date})
        for column in [COL_ANN_DATE, COL_END_DATE]:
            result[column] = pd.to_datetime(result[column], errors="raise").dt.date
        return result

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
                result_row = cast(Any, result)
                if COL_ANN_DATE in result_row:
                    return str(result_row[COL_ANN_DATE])
                return str(result_row[0])
            return None

        except Exception as e:
            logger.exception(f"获取股东人数最新公告日期失败 - 股票代码: {stock_id}, 错误: {e}")
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
                result_row = cast(Any, result)
                if COL_ANN_DATE in result_row:
                    return str(result_row[COL_ANN_DATE])
                return str(result_row[0])
            return None

        except Exception as e:
            logger.exception(f"获取前十大流通股东最新公告日期失败 - 股票代码: {stock_id}, 错误: {e}")
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
            prepared = self._prepare_dataframe_for_save(
                df,
                column_map=COL_MAP_STOCK_BASIC,
                code_column=COL_STOCK_ID,
                date_columns={COL_IPO_DATE: "date", COL_DELISTING_DATE: "date"},
                output_columns=list(COL_MAP_STOCK_BASIC.values()),
            )
            max_lengths = {
                COL_STOCK_ID: 6,
                COL_STOCK_NAME: 40,
                COL_AREA: 20,
                COL_INDUSTRY: 40,
                COL_FULLNAME: 100,
                COL_ENNAME: 100,
                COL_CN_SPELL: 20,
                COL_MARKET: 20,
                COL_EXCHANGE: 10,
                COL_CURR_TYPE: 10,
                COL_LIST_STATUS: 2,
                COL_IS_HS: 2,
                COL_ACT_NAME: 100,
                COL_ACT_ENT_TYPE: 20,
            }
            for column, limit in max_lengths.items():
                lengths = prepared[column].astype("string").str.len()
                violations = prepared[lengths > limit]
                if not violations.empty:
                    actual_length = int(lengths.loc[violations.index].iloc[0])
                    stock_code = violations[COL_STOCK_ID].iloc[0]
                    logger.error(
                        "A股基础信息字段长度超限: 股票代码=%s, 字段=%s, 实际长度=%s, 限制=%s",
                        stock_code,
                        column,
                        actual_length,
                        limit,
                    )
                    return False

            self._write_dataframe(
                prepared,
                tb_name_a_stock_basic,
                if_exists="append",
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
            df = self._prepare_etf_basic(df)
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

    @staticmethod
    def _prepare_etf_basic(df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns=COL_MAP_ETF_BASIC)
        # 提取ETF代码（去掉 .SH/.SZ 后缀）
        df[COL_ETF_ID] = df[COL_ETF_ID].str.split(".").str[0]
        df = df[list(COL_MAP_ETF_BASIC.values())]
        # 转换日期为 date 类型
        df[COL_SETUP_DATE] = pd.to_datetime(df[COL_SETUP_DATE], format="%Y%m%d", errors="coerce").dt.date
        df[COL_IPO_DATE] = pd.to_datetime(df[COL_IPO_DATE], format="%Y%m%d", errors="coerce").dt.date
        return df

    def refresh_etf_basic_and_reconcile(self, df: pd.DataFrame) -> bool:
        """Replace ETF basic data and reconcile eligibility atomically."""
        from paper_trading.services.etf_eligibility_service import ETFEligibilityService
        from paper_trading.storage.repository import PaperTradingRepository

        assert self.Session is not None
        session = self.Session()
        try:
            prepared = self._prepare_etf_basic(df)
            with session.begin():
                session.query(ETFBasic).delete()
                prepared.to_sql(
                    tb_name_etf_basic,
                    session.connection(),
                    if_exists="append",
                    index=False,
                    method="multi",
                )
                snapshot = session.query(ETFBasic).all()
                ETFEligibilityService(PaperTradingRepository(session)).reconcile(snapshot, datetime.now(timezone.utc))
            logger.info(f"ETF基础信息数据保存成功，数据条数: {len(prepared)}")
            return True
        except Exception as e:
            logger.error(f"保存ETF基础信息数据或同步ETF准入状态失败: {str(e)}")
            return False
        finally:
            session.close()

    def reconcile_etf_eligibility(self) -> None:
        """Reconcile paper-trading eligibility from the persisted ETF snapshot."""
        from paper_trading.services.etf_eligibility_service import ETFEligibilityService
        from paper_trading.storage.repository import PaperTradingRepository

        assert self.Session is not None
        session = self.Session()
        try:
            snapshot = session.query(ETFBasic).all()
            ETFEligibilityService(PaperTradingRepository(session)).reconcile(snapshot, datetime.now(timezone.utc))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

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
            logger.info(f"ETF日线数据保存成功: {tb_name_etf_daily}, 数据条数: {len(df)}")
            return True

        except Exception as e:
            logger.error(f"保存ETF日线数据失败: {str(e)}")
            return False

    def save_etf_share_size(self, df: pd.DataFrame) -> bool:
        try:
            prepared = df.rename(columns=COL_MAP_ETF_SHARE_SIZE).copy()
            required = [COL_ETF_ID, COL_DATE, COL_CLOSE, COL_NAV, COL_ETF_TOTAL_SHARE, COL_ETF_TOTAL_SIZE]
            missing = set(required) - set(prepared.columns)
            if missing:
                raise ValueError(f"ETF share/size 缺少字段: {sorted(missing)}")

            prepared = prepared[required]
            prepared[COL_ETF_ID] = prepared[COL_ETF_ID].astype(str).str.split(".").str[0]
            prepared[COL_DATE] = pd.to_datetime(prepared[COL_DATE], errors="raise").dt.date
            for column in [COL_CLOSE, COL_NAV, COL_ETF_TOTAL_SHARE, COL_ETF_TOTAL_SIZE]:
                prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

            records = prepared.to_dict(orient="records")
            if not records:
                return True

            table = ETFShareSize.__table__
            stmt: PostgreSQLInsert | SQLiteInsert
            if self.engine.dialect.name == "postgresql":
                postgres_insert_stmt = pg_insert(table).values(records)
                stmt = postgres_insert_stmt.on_conflict_do_update(
                    index_elements=list(table.primary_key.columns.keys()),
                    set_={column.name: getattr(postgres_insert_stmt.excluded, column.name) for column in table.columns},
                )
            elif self.engine.dialect.name == "sqlite":
                sqlite_insert_stmt = sqlite_insert(table).values(records)
                stmt = sqlite_insert_stmt.on_conflict_do_update(
                    index_elements=list(table.primary_key.columns.keys()),
                    set_={column.name: getattr(sqlite_insert_stmt.excluded, column.name) for column in table.columns},
                )
            else:
                raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")
            with self.engine.begin() as conn:
                conn.execute(stmt)

            logger.info(f"ETF份额规模数据保存成功: {tb_name_etf_share_size}, 数据条数: {len(prepared)}")
            return True
        except Exception as e:
            logger.error(f"保存ETF份额规模数据失败: {str(e)}")
            return False

    def save_index_daily_turnover(self, df: pd.DataFrame) -> bool:
        try:
            prepared = df.rename(columns=COL_MAP_INDEX_DAILY_TURNOVER).copy()
            required = [COL_INDEX_CODE, COL_DATE, COL_CLOSE, COL_AMOUNT]
            missing = set(required) - set(prepared.columns)
            if missing:
                raise ValueError(f"指数收盘成交额缺少字段: {sorted(missing)}")

            prepared = prepared[required]
            prepared[COL_INDEX_CODE] = prepared[COL_INDEX_CODE].astype(str)
            prepared[COL_DATE] = pd.to_datetime(prepared[COL_DATE], errors="raise").dt.date
            for column in [COL_CLOSE, COL_AMOUNT]:
                prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

            records = prepared.to_dict(orient="records")
            if not records:
                return True

            table = IndexDailyTurnover.__table__
            stmt: PostgreSQLInsert | SQLiteInsert
            if self.engine.dialect.name == "postgresql":
                postgres_insert_stmt = pg_insert(table).values(records)
                stmt = postgres_insert_stmt.on_conflict_do_update(
                    index_elements=list(table.primary_key.columns.keys()),
                    set_={column.name: getattr(postgres_insert_stmt.excluded, column.name) for column in table.columns},
                )
            elif self.engine.dialect.name == "sqlite":
                sqlite_insert_stmt = sqlite_insert(table).values(records)
                stmt = sqlite_insert_stmt.on_conflict_do_update(
                    index_elements=list(table.primary_key.columns.keys()),
                    set_={column.name: getattr(sqlite_insert_stmt.excluded, column.name) for column in table.columns},
                )
            else:
                raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")
            with self.engine.begin() as conn:
                conn.execute(stmt)

            logger.info(f"指数收盘成交额数据保存成功: {tb_name_index_daily_turnover}, 数据条数: {len(prepared)}")
            return True
        except Exception as e:
            logger.error(f"保存指数收盘成交额数据失败: {str(e)}")
            return False

    def _read_sql_with_dialect_params(self, sql: str, params: tuple[Any, ...]) -> pd.DataFrame:
        if self.engine.dialect.name == "sqlite":
            sql = sql.replace("%s", "?")
        return pd.read_sql(sql, self.engine, params=params)

    def load_etf_share_size(
        self,
        etf_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        include_prior_effective: bool = False,
    ) -> pd.DataFrame:
        try:
            sql, sql_params = self._build_code_date_range_query(
                table_name=tb_name_etf_share_size,
                code_column=COL_ETF_ID,
                code_value=etf_id,
                date_column=COL_DATE,
                start_date=start_date,
                end_date=end_date,
            )
            df = self._read_sql_with_dialect_params(sql, sql_params)

            if include_prior_effective and start_date:
                prior_sql = f'''
                SELECT * FROM {tb_name_etf_share_size}
                WHERE "{COL_ETF_ID}" = %s
                  AND "{COL_DATE}" < %s
                ORDER BY "{COL_DATE}" DESC
                LIMIT 1
                '''
                prior = self._read_sql_with_dialect_params(prior_sql, (etf_id, start_date))
                if not prior.empty:
                    df = pd.concat([prior, df], ignore_index=True)

            logger.info(f"ETF份额规模数据加载成功: {etf_id}, 数据条数: {len(df)}")
            return df
        except Exception as e:
            logger.error(f"加载ETF份额规模数据失败: {etf_id}, 错误: {str(e)}")
            return pd.DataFrame()

    def load_index_daily_turnover(
        self,
        ts_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        try:
            sql, sql_params = self._build_code_date_range_query(
                table_name=tb_name_index_daily_turnover,
                code_column=COL_INDEX_CODE,
                code_value=ts_code,
                date_column=COL_DATE,
                start_date=start_date,
                end_date=end_date,
            )
            df = self._read_sql_with_dialect_params(sql, sql_params)
            logger.info(f"指数收盘成交额数据加载成功: {ts_code}, 数据条数: {len(df)}")
            return df
        except Exception as e:
            logger.error(f"加载指数收盘成交额数据失败: {ts_code}, 错误: {str(e)}")
            return pd.DataFrame()

    def save_etf_net_flow(self, df: pd.DataFrame) -> bool:
        try:
            prepared = df.rename(columns=COL_MAP_ETF_NET_FLOW).copy()
            required = [
                COL_ETF_ID,
                COL_DATE,
                COL_ETF_TOTAL_SHARE,
                COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
                COL_ETF_NET_SHARE_CHANGE,
                COL_ETF_ESTIMATED_TRADED_PRICE,
                COL_ETF_NET_FLOW_AMOUNT,
                COL_INDEX_CODE,
                COL_INDEX_TURNOVER_AMOUNT,
                COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
            ]
            missing = set(required) - set(prepared.columns)
            if missing:
                raise ValueError(f"ETF净申赎缺少字段: {sorted(missing)}")

            prepared = prepared[required]
            prepared[COL_ETF_ID] = prepared[COL_ETF_ID].astype(str).str.split(".").str[0]
            prepared[COL_INDEX_CODE] = prepared[COL_INDEX_CODE].astype(str)
            prepared[COL_DATE] = pd.to_datetime(prepared[COL_DATE], errors="raise").dt.date
            for column in [
                COL_ETF_TOTAL_SHARE,
                COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
                COL_ETF_NET_SHARE_CHANGE,
                COL_ETF_ESTIMATED_TRADED_PRICE,
                COL_ETF_NET_FLOW_AMOUNT,
                COL_INDEX_TURNOVER_AMOUNT,
                COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
            ]:
                prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

            records = prepared.to_dict(orient="records")
            if not records:
                return True

            table = ETFNetFlow.__table__
            stmt: PostgreSQLInsert | SQLiteInsert
            if self.engine.dialect.name == "postgresql":
                postgres_insert_stmt = pg_insert(table).values(records)
                stmt = postgres_insert_stmt.on_conflict_do_update(
                    index_elements=list(table.primary_key.columns.keys()),
                    set_={column.name: getattr(postgres_insert_stmt.excluded, column.name) for column in table.columns},
                )
            elif self.engine.dialect.name == "sqlite":
                sqlite_insert_stmt = sqlite_insert(table).values(records)
                stmt = sqlite_insert_stmt.on_conflict_do_update(
                    index_elements=list(table.primary_key.columns.keys()),
                    set_={column.name: getattr(sqlite_insert_stmt.excluded, column.name) for column in table.columns},
                )
            else:
                raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")
            with self.engine.begin() as conn:
                conn.execute(stmt)

            logger.info(f"ETF净申赎数据保存成功: {tb_name_etf_net_flow}, 数据条数: {len(prepared)}")
            return True
        except Exception as e:
            logger.error(f"保存ETF净申赎数据失败: {str(e)}")
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
            df = self._read_sql_with_dialect_params(sql, sql_params)
            logger.info(f"ETF日线数据加载成功，数据条数: {len(df)}")
            return df

        except Exception as e:
            logger.error(f"加载ETF日线数据失败: {str(e)}")
            return pd.DataFrame()

    def ensure_ssf_change_signals_table(self) -> None:
        """建表（若不存在），供 SSF 变动信号流程初始化使用。"""
        assert self.engine is not None
        if self.engine.dialect.name == "postgresql":
            if inspect(self.engine).has_table(tb_name_ssf_change_signal):
                self._ensure_ssf_change_signals_status_column()
            return

        from .model.ssf_change_signal import SSFChangeSignal  # noqa: F401

        SSFChangeSignal.__table__.create(self.engine, checkfirst=True)
        self._ensure_ssf_change_signals_status_column()

    def _ensure_ssf_change_signals_status_column(self) -> None:
        assert self.engine is not None
        columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_ssf_change_signal)}
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
        return [(row["stock_id"], pd.Timestamp(row["ann_date"]).strftime("%Y-%m-%d")) for _, row in df.iterrows()]

    def load_top10_floatholders_history(self, stock_id: str, limit_ann_dates: int = 2) -> pd.DataFrame:
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

    def load_latest_top10_floatholders(self, stock_id: str, as_of_date: date) -> pd.DataFrame:
        sql = text(
            f'''\
            SELECT *
            FROM {tb_name_top10_floatholders}
            WHERE "{COL_STOCK_ID}" = :stock_id
              AND "{COL_ANN_DATE}" <= :as_of_date
              AND "{COL_ANN_DATE}" = (
                  SELECT MAX("{COL_ANN_DATE}")
                  FROM {tb_name_top10_floatholders}
                  WHERE "{COL_STOCK_ID}" = :stock_id
                    AND "{COL_ANN_DATE}" <= :as_of_date
              )
            ORDER BY "{COL_FLOAT_HOLDER_NAME}"
            '''
        )
        assert self.engine is not None
        params: dict[str, str | date] = {"stock_id": stock_id, "as_of_date": as_of_date}
        df = pd.read_sql(sql, self.engine, params=params)
        if COL_ANN_DATE in df.columns:
            df[COL_ANN_DATE] = pd.to_datetime(df[COL_ANN_DATE])
        return df

    def save_ssf_change_signals(self, records: List[Dict[str, Any]]) -> List[int]:
        """保存 SSF 变动信号，已存在的 `(stock_id, ann_date)` 记录会跳过。"""
        normalized_records = []
        for payload in records:
            normalized_payload = dict(payload)
            normalized_payload.setdefault("status", SSF_CHANGE_SIGNAL_STATUS_SIGNAL)
            normalized_records.append(normalized_payload)
        return self._save_ssf_change_signal_records(normalized_records)

    def mark_ssf_change_candidates_processed(self, records: List[Dict[str, Any]]) -> List[int]:
        normalized_records = []
        for payload in records:
            normalized_records.append(
                {
                    "stock_id": payload["stock_id"],
                    "ann_date": payload["ann_date"],
                    "prev_ann_date": payload.get("prev_ann_date") or payload["ann_date"],
                    "status": SSF_CHANGE_SIGNAL_STATUS_NO_SIGNAL,
                    "event_types": [],
                    "score": 0.0,
                    "detail_json": {"holders": []},
                    "alert_sent_at": datetime.now(timezone.utc),
                }
            )
        return self._save_ssf_change_signal_records(normalized_records)

    def _save_ssf_change_signal_records(self, records: List[Dict[str, Any]]) -> List[int]:
        from .model.ssf_change_signal import SSFChangeSignal

        assert self.engine is not None
        table = SSFChangeSignal.__table__
        insert_fn: Any
        if self.engine.dialect.name == "postgresql":
            insert_fn = pg_insert
        elif self.engine.dialect.name == "sqlite":
            insert_fn = sqlite_insert
        else:
            raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")

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
                status = SSFChangeSignalStatus(payload.get("status", SSF_CHANGE_SIGNAL_STATUS_SIGNAL)).value
                event_types = validate_ssf_event_types(payload["event_types"])
                signal_payload = {
                    "stock_id": payload["stock_id"],
                    "ann_date": pd.to_datetime(payload["ann_date"]).date(),
                    "prev_ann_date": pd.to_datetime(payload["prev_ann_date"]).date(),
                    "status": status,
                    "event_types": event_types,
                    "score": payload["score"],
                    "detail_json": payload["detail_json"],
                }
                for field in optional_fields:
                    if field in payload and field != "status":
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
        self, frequency: Optional[str] = None, enabled: Optional[bool] = None, workflow: Optional[str] = None
    ) -> List[Any]:
        """
        查询监控目标列表。

        Args:
            frequency: 可选，按频率过滤 ('daily' 或 'intraday')。
            enabled: 可选，按启用状态过滤。
            workflow: 可选，按工作流所有者过滤。
        Returns:
            StockMonitorTarget 对象列表。
        """
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            query = session.query(StockMonitorTarget)
            if enabled is not None:
                query = query.filter_by(enabled=enabled)
            if frequency:
                query = query.filter_by(frequency=frequency)
            if workflow is not None:
                query = query.filter_by(workflow=workflow)
            return cast(List[Any], query.order_by(StockMonitorTarget.id.asc()).all())
        finally:
            session.close()

    def get_monitor_target(self, target_id: int) -> Optional[Any]:
        """按 ID 查询单个监控目标。"""
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            return session.query(StockMonitorTarget).filter_by(id=target_id).first()
        finally:
            session.close()

    def list_monitor_target_health(self) -> list[Any]:
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            return cast(list[Any], session.query(StockMonitorTarget).order_by(StockMonitorTarget.id.asc()).all())
        finally:
            session.close()

    def record_monitor_target_evaluation(self, target_id: int, checked_at: datetime) -> bool:
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
            if target is None:
                return False
            target.last_checked_at = checked_at
            target.latest_error_kind = target.latest_error_detail = target.latest_error_at = None
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def record_monitor_target_evaluation_error(
        self, target_id: int, kind: str, detail: str | None, occurred_at: datetime
    ) -> bool:
        self._validate_monitor_enum_value(kind, "kind", MonitorEvaluationErrorKind)
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
            if target is None:
                return False
            target.latest_error_kind = kind
            target.latest_error_detail = sanitize_error_detail(detail) if detail is not None else None
            target.latest_error_at = occurred_at
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_manual_monitor_targets(
        self,
        *,
        frequency: str | None = None,
        enabled: bool | None = None,
        market: str | None = None,
        condition_type: str | None = None,
    ) -> list[Any]:
        """查询未归属工作流的监控目标。"""
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            query = session.query(StockMonitorTarget).filter(StockMonitorTarget.workflow.is_(None))
            if frequency is not None:
                query = query.filter_by(frequency=frequency)
            if enabled is not None:
                query = query.filter_by(enabled=enabled)
            if market is not None:
                query = query.filter_by(market=market)
            if condition_type is not None:
                query = query.filter(StockMonitorTarget.condition["type"].as_string() == condition_type)
            return cast(list[Any], query.order_by(StockMonitorTarget.id.asc()).all())
        finally:
            session.close()

    def get_manual_monitor_target(self, target_id: int) -> Any | None:
        """按 ID 查询未归属工作流的监控目标。"""
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            return (
                session.query(StockMonitorTarget)
                .filter(StockMonitorTarget.id == target_id, StockMonitorTarget.workflow.is_(None))
                .first()
            )
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
        self._validate_monitor_enum_value(market, "market", MonitorMarket)
        self._validate_monitor_enum_value(frequency, "frequency", MonitorFrequency)
        self._validate_monitor_enum_value(reset_mode, "reset_mode", MonitorResetMode)
        condition = validate_condition(condition)
        self.ensure_monitor_targets_table()
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
                workflow=condition.get("workflow"),
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

    def create_manual_monitor_target(
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
        """创建未归属工作流的监控目标。"""
        if condition.get("workflow") is not None:
            raise ValueError("manual monitor target condition cannot include a workflow marker")
        return self.create_monitor_target(
            stock_code, market, condition, note, frequency, reset_mode, enabled, last_state
        )

    def update_monitor_target(self, target_id: int, **updates: Any) -> Optional[Any]:
        """更新监控目标。目标不存在时返回 None。"""
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
        for field, enum_type in (
            ("market", MonitorMarket),
            ("frequency", MonitorFrequency),
            ("reset_mode", MonitorResetMode),
        ):
            if field in updates:
                self._validate_monitor_enum_value(updates[field], field, enum_type)
        if "condition" in updates:
            updates["condition"] = validate_condition(updates["condition"])

        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
            if target is None:
                return None
            if (
                "condition" in updates
                and target.workflow is not None
                and updates["condition"].get("workflow") != target.workflow
            ):
                raise ValueError(f"condition workflow marker must match {target.workflow!r}")
            if "condition" in updates and target.workflow is None and updates["condition"].get("workflow") is not None:
                raise ValueError("manual monitor target condition cannot include a workflow marker")
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

    def update_manual_monitor_target(self, target_id: int, **updates: Any) -> Any | None:
        """更新未归属工作流的监控目标。目标不存在或属于工作流时返回 None。"""
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
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            target = (
                session.query(StockMonitorTarget)
                .filter(StockMonitorTarget.id == target_id, StockMonitorTarget.workflow.is_(None))
                .first()
            )
            if target is None:
                return None
            for field, enum_type in (
                ("market", MonitorMarket),
                ("frequency", MonitorFrequency),
                ("reset_mode", MonitorResetMode),
            ):
                if field in updates:
                    self._validate_monitor_enum_value(updates[field], field, enum_type)
            if "condition" in updates:
                updates["condition"] = validate_condition(updates["condition"])
                if updates["condition"].get("workflow") is not None:
                    raise ValueError("manual monitor target condition cannot include a workflow marker")
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
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        self.ensure_monitor_notification_tables()
        assert self.Session is not None
        session = self.Session()
        try:
            target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
            if target is None:
                return False
            self._cancel_monitor_notifications_for_target(session, target_id)
            session.delete(target)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_manual_monitor_target(self, target_id: int) -> bool:
        """删除未归属工作流的监控目标。"""
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        self.ensure_monitor_notification_tables()
        assert self.Session is not None
        session = self.Session()
        try:
            target = (
                session.query(StockMonitorTarget)
                .filter(StockMonitorTarget.id == target_id, StockMonitorTarget.workflow.is_(None))
                .first()
            )
            if target is None:
                return False
            self._cancel_monitor_notifications_for_target(session, target_id)
            session.delete(target)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_monitor_targets(self, frequency: Optional[str] = None, workflow: Optional[str] = None) -> List[Any]:
        """
        加载所有启用的监控目标。

        Args:
            frequency: 可选，按频率过滤 ('daily' 或 'intraday')；None 则返回全部。
            workflow: 可选，按工作流所有者过滤。
        Returns:
            StockMonitorTarget 对象列表。
        """
        return self.list_monitor_targets(frequency=frequency, enabled=True, workflow=workflow)

    def disable_forecast_ssf_target_with_candidate_transition(
        self,
        target_id: int,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
    ) -> bool:
        return self._disable_forecast_ssf_target_with_candidate_transition(
            target_id,
            state,
            state_reason,
            lambda _candidate: evidence,
        )

    def _disable_forecast_ssf_target_with_candidate_transition(
        self,
        target_id: int,
        state: str,
        state_reason: str,
        evidence_builder: Callable[[Any], dict[str, Any]],
    ) -> bool:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate
        from .model.stock_monitor_target import StockMonitorTarget

        self._validate_monitor_enum_value(state, "state", ForecastSSFCandidateState)
        self.ensure_monitor_targets_table()
        assert self.Session is not None
        session = self.Session()
        try:
            with session.begin():
                target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
                if target is None or target.workflow != "forecast_ssf_ma20" or target.frequency != "daily":
                    return False
                candidates = session.query(ForecastSSFCandidate).filter_by(monitor_target_id=target_id).all()
                if len(candidates) > 1:
                    raise ValueError(f"multiple candidates found for monitor_target_id={target_id}")
                if not candidates:
                    return False
                candidate = candidates[0]
                evidence = evidence_builder(candidate)
                self._transition_forecast_ssf_candidate_with_workflow_target_in_transaction(
                    session,
                    candidate.stock_code,
                    candidate.market,
                    candidate.report_end_date,
                    state,
                    state_reason,
                    evidence,
                    False,
                )
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _disable_workflow_target_in_transaction(self, session: Any, target: Any) -> None:
        target.enabled = False
        session.flush()

    def disable_forecast_ssf_target_for_blackroom(self, target_id: int, reason: str) -> bool:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate
        from .model.stock_monitor_target import StockMonitorTarget

        self.ensure_monitor_targets_table()
        assert self.Session is not None
        session = self.Session()
        try:
            with session.begin():
                target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
                if target is None or target.workflow != "forecast_ssf_ma20" or target.frequency != "daily":
                    return False
                candidates = session.query(ForecastSSFCandidate).filter_by(monitor_target_id=target_id).all()
                if len(candidates) > 1:
                    raise ValueError(f"multiple candidates found for monitor_target_id={target_id}")
                if not candidates:
                    return False
                candidate = candidates[0]
                evidence = dict(candidate.evidence or {})
                evidence["lifecycle"] = {
                    "as_of_date": date.today().isoformat(),
                    "state": "blackroom",
                    "reason": reason,
                    "previous_state": candidate.state,
                }
                self._transition_forecast_ssf_candidate_with_workflow_target_in_transaction(
                    session,
                    candidate.stock_code,
                    candidate.market,
                    candidate.report_end_date,
                    "blackroom",
                    reason,
                    evidence,
                    False,
                )
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def transition_forecast_ssf_candidate_with_workflow_target(
        self,
        stock_code: str,
        market: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        target_enabled: bool,
    ) -> Any:
        self._validate_monitor_enum_value(market, "market", MonitorMarket)
        self._validate_monitor_enum_value(state, "state", ForecastSSFCandidateState)
        self.ensure_monitor_targets_table()
        assert self.Session is not None
        session = self.Session()
        try:
            with session.begin():
                target = self._transition_forecast_ssf_candidate_with_workflow_target_in_transaction(
                    session,
                    stock_code,
                    market,
                    report_end_date,
                    state,
                    state_reason,
                    evidence,
                    target_enabled,
                )
            session.refresh(target)
            return target
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _transition_forecast_ssf_candidate_with_workflow_target_in_transaction(
        self,
        session: Any,
        stock_code: str,
        market: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        target_enabled: bool,
    ) -> Any:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate
        from .model.stock_monitor_target import StockMonitorTarget

        candidate = session.query(ForecastSSFCandidate).filter_by(stock_code=stock_code, market=market).first()
        if market != "A" or candidate is None or candidate.monitor_target_id is None:
            raise ValueError("candidate must have a linked workflow target")
        target = session.query(StockMonitorTarget).filter_by(id=candidate.monitor_target_id).first()
        if (
            target is None
            or target.stock_code != stock_code
            or target.market != market
            or target.market != "A"
            or target.workflow != "forecast_ssf_ma20"
            or target.frequency != "daily"
        ):
            raise ValueError("candidate must have a linked workflow target")
        candidates = session.query(ForecastSSFCandidate).filter_by(monitor_target_id=target.id).all()
        if len(candidates) != 1:
            raise ValueError(f"multiple candidates found for monitor_target_id={target.id}")

        candidate.report_end_date = report_end_date
        candidate.state = state
        candidate.state_reason = state_reason
        candidate.evidence = evidence
        if not target_enabled:
            self._disable_workflow_target_in_transaction(session, target)
        else:
            target.enabled = False if target.paused else True
            session.flush()
        return target

    def find_workflow_monitor_target(self, stock_code: str, market: str, frequency: str, workflow: str) -> Any | None:
        from .model.stock_monitor_target import StockMonitorTarget

        self._ensure_workflow_monitor_target_identity()
        assert self.Session is not None
        session = self.Session()
        try:
            matches = (
                session.query(StockMonitorTarget)
                .filter_by(stock_code=stock_code, market=market, frequency=frequency, workflow=workflow)
                .all()
            )
        finally:
            session.close()
        if len(matches) > 1:
            raise ValueError(f"发现多个 workflow={workflow!r} 的监控目标: {stock_code}/{market}/{frequency}")
        return matches[0] if matches else None

    def set_workflow_monitor_target_paused(self, target_id: int, paused: bool) -> Any | None:
        self.ensure_monitor_targets_table()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            with session.begin():
                target = session.query(StockMonitorTarget).filter_by(id=target_id).first()
                if target is None:
                    return None
                if target.workflow is None:
                    raise ValueError("only workflow monitor targets can be paused or resumed")
                if paused:
                    target.paused = True
                    target.enabled = False
                else:
                    target.paused = False
                session.flush()
            session.refresh(target)
            return target
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_workflow_monitor_target(
        self,
        stock_code: str,
        market: str,
        frequency: str,
        workflow: str,
        condition: dict[str, Any],
        note: str,
        enabled: bool,
        reset_last_state: bool,
    ) -> Any:
        self._validate_monitor_enum_value(market, "market", MonitorMarket)
        self._validate_monitor_enum_value(frequency, "frequency", MonitorFrequency)
        condition = validate_condition(condition)
        if condition.get("workflow") != workflow:
            raise ValueError(f"condition workflow marker must match {workflow!r}")
        self._ensure_workflow_monitor_target_identity()
        assert self.Session is not None
        session = self.Session()
        try:
            with session.begin():
                target = self._upsert_workflow_monitor_target_in_transaction(
                    session, stock_code, market, frequency, workflow, condition, note, enabled, reset_last_state
                )
            session.refresh(target)
            return target
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _upsert_workflow_monitor_target_in_transaction(
        self,
        session: Any,
        stock_code: str,
        market: str,
        frequency: str,
        workflow: str,
        condition: dict[str, Any],
        note: str,
        enabled: bool,
        reset_last_state: bool,
    ) -> Any:
        from .model.stock_monitor_target import StockMonitorTarget

        target = (
            session.query(StockMonitorTarget)
            .filter_by(stock_code=stock_code, market=market, frequency=frequency, workflow=workflow)
            .first()
        )
        if target is None:
            record = {
                "stock_code": stock_code,
                "market": market,
                "condition": condition,
                "note": note,
                "frequency": frequency,
                "workflow": workflow,
                "enabled": enabled,
                "paused": False,
                "last_state": False,
            }
            if session.bind.dialect.name == "postgresql":
                stmt: PostgreSQLInsert | SQLiteInsert = (
                    pg_insert(StockMonitorTarget.__table__)
                    .values(record)
                    .on_conflict_do_nothing(index_elements=["stock_code", "market", "frequency", "workflow"])
                )
            elif session.bind.dialect.name == "sqlite":
                stmt = (
                    sqlite_insert(StockMonitorTarget.__table__)
                    .values(record)
                    .on_conflict_do_nothing(index_elements=["stock_code", "market", "frequency", "workflow"])
                )
            else:
                raise ConnectionError(f"Unsupported database dialect: {session.bind.dialect.name}")
            session.execute(stmt)
            target = (
                session.query(StockMonitorTarget)
                .filter_by(stock_code=stock_code, market=market, frequency=frequency, workflow=workflow)
                .one()
            )
            effective_enabled = False if target.paused else enabled
            if target.condition != condition or target.note != note or target.enabled != effective_enabled:
                target.condition = condition
                target.note = note
                target.enabled = effective_enabled
                if reset_last_state:
                    target.last_state = False
        else:
            if target.condition.get("workflow") != workflow:
                raise ValueError(f"workflow target condition must retain marker {workflow!r}")
            target.condition = condition
            target.note = note
            target.enabled = False if target.paused else enabled
            if reset_last_state:
                target.last_state = False
        session.flush()
        return target

    def upsert_forecast_ssf_candidate_with_workflow_target(
        self,
        *,
        stock_code: str,
        market: str,
        report_end_date: date,
        state: str,
        state_reason: str,
        evidence: dict[str, Any],
        workflow: str,
        frequency: str,
        condition: dict[str, Any],
        note: str,
        target_enabled: bool,
        reset_last_state: bool,
    ) -> Any:
        from .model.forecast_ssf_candidate import ForecastSSFCandidate

        self._validate_monitor_enum_value(market, "market", MonitorMarket)
        self._validate_monitor_enum_value(frequency, "frequency", MonitorFrequency)
        self._validate_monitor_enum_value(state, "state", ForecastSSFCandidateState)
        condition = validate_condition(condition)
        if condition.get("workflow") != workflow:
            raise ValueError(f"condition workflow marker must match {workflow!r}")
        self._ensure_workflow_monitor_target_identity()
        assert self.Session is not None
        session = self.Session()
        try:
            with session.begin():
                target = self._upsert_workflow_monitor_target_in_transaction(
                    session,
                    stock_code,
                    market,
                    frequency,
                    workflow,
                    condition,
                    note,
                    target_enabled,
                    False,
                )
                self._upsert_forecast_ssf_candidate_in_transaction(
                    session.connection(),
                    ForecastSSFCandidate.__table__,
                    stock_code,
                    market,
                    report_end_date,
                    state,
                    state_reason,
                    evidence,
                    target.id,
                )
            session.refresh(target)
            return target
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _validate_monitor_enum_value(value: Any, field_name: str, enum_type: type[StrEnum]) -> None:
        if not isinstance(value, str) or value not in enum_type:
            raise ValueError(f"{field_name} must be one of {sorted(enum_type)}")

    def _ensure_workflow_monitor_target_identity(self) -> None:
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.engine is not None
        columns = {column["name"] for column in inspect(self.engine).get_columns(StockMonitorTarget.__tablename__)}
        if "workflow" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {StockMonitorTarget.__tablename__} ADD COLUMN workflow VARCHAR(64)"))
            columns.add("workflow")
        if "paused" not in columns:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {StockMonitorTarget.__tablename__} "
                        "ADD COLUMN paused BOOLEAN NOT NULL DEFAULT false"
                    )
                )

        assert self.Session is not None
        session = self.Session()
        try:
            for target in session.query(StockMonitorTarget).filter_by(workflow=None):
                workflow = target.condition.get("workflow")
                if workflow is not None:
                    target.workflow = workflow
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        session = self.Session()
        try:
            duplicate_owners = (
                session.query(
                    StockMonitorTarget.stock_code,
                    StockMonitorTarget.market,
                    StockMonitorTarget.frequency,
                    StockMonitorTarget.workflow,
                )
                .filter(StockMonitorTarget.workflow.is_not(None))
                .group_by(
                    StockMonitorTarget.stock_code,
                    StockMonitorTarget.market,
                    StockMonitorTarget.frequency,
                    StockMonitorTarget.workflow,
                )
                .having(func.count(StockMonitorTarget.id) > 1)
                .all()
            )
            for stock_code, market, frequency, workflow in duplicate_owners:
                target_ids = [
                    target_id
                    for (target_id,) in (
                        session.query(StockMonitorTarget.id)
                        .filter_by(
                            stock_code=stock_code,
                            market=market,
                            frequency=frequency,
                            workflow=workflow,
                        )
                        .order_by(StockMonitorTarget.id.asc())
                        .all()
                    )
                ]
                raise ValueError(
                    f"发现重复的 workflow 监控目标: {stock_code}/{market}/{frequency}/{workflow!r} (ids: {target_ids})"
                )
        finally:
            session.close()

        index_name = "uq_stock_monitor_targets_workflow_owner"
        indexes = {index["name"] for index in inspect(self.engine).get_indexes(StockMonitorTarget.__tablename__)}
        if index_name not in indexes:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {StockMonitorTarget.__tablename__} "
                        "(stock_code, market, frequency, workflow)"
                    )
                )

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
        self.ensure_monitor_targets_table()
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
        self._ensure_monitor_target_health_columns()
        self._migrate_sqlite_price_vs_ma_conditions()
        self._ensure_workflow_monitor_target_identity()

    def ensure_monitor_notification_tables(self) -> None:
        """Ensure the monitor target and notification outbox tables exist."""
        self.ensure_monitor_targets_table()
        MonitorNotification.__table__.create(self.engine, checkfirst=True)

    def create_monitor_notification_for_trigger(
        self, target_id: int, subject: str, body: str, triggered_at: datetime
    ) -> str | None:
        """Persist a notification only when a target crosses into the triggered state."""
        self.ensure_monitor_notification_tables()
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.Session is not None
        session = self.Session()
        try:
            query = session.query(StockMonitorTarget).filter_by(id=target_id)
            if self.engine.dialect.name == "postgresql":
                query = query.with_for_update()
            target = query.first()
            if target is None or not target.enabled or target.last_state:
                session.rollback()
                return None

            notification_id = uuid4()
            target.last_state = True
            target.triggered_at = triggered_at
            session.add(
                MonitorNotification(
                    id=notification_id,
                    target_id=target_id,
                    subject=subject,
                    body=body,
                    state=NotificationDeliveryState.PENDING.value,
                    attempt_count=0,
                    next_attempt_at=triggered_at,
                )
            )
            session.commit()
            return str(notification_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def claim_due_monitor_notifications(self, now: datetime, limit: int) -> list[MonitorNotification]:
        """Claim due or abandoned notifications for exclusive delivery processing."""
        if limit <= 0:
            return []
        self.ensure_monitor_notification_tables()

        assert self.Session is not None
        session = self.Session()
        try:
            stale_before = now - timedelta(minutes=30)
            due = or_(
                and_(
                    MonitorNotification.state == NotificationDeliveryState.PENDING.value,
                    MonitorNotification.next_attempt_at <= now,
                ),
                and_(
                    MonitorNotification.state == NotificationDeliveryState.PROCESSING.value,
                    MonitorNotification.claimed_at <= stale_before,
                ),
            )
            query = session.query(MonitorNotification).filter(due).order_by(
                MonitorNotification.next_attempt_at.asc(), MonitorNotification.created_at.asc()
            )
            if self.engine.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
            notifications = query.limit(limit).all()
            for notification in notifications:
                notification.state = NotificationDeliveryState.PROCESSING.value
                notification.claimed_at = now
            session.commit()
            for notification in notifications:
                session.refresh(notification)
                session.expunge(notification)
            return notifications
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def mark_monitor_notification_delivered(self, notification_id: str, delivered_at: datetime) -> bool:
        self.ensure_monitor_notification_tables()
        assert self.Session is not None
        session = self.Session()
        try:
            notification = session.get(MonitorNotification, UUID(notification_id))
            if notification is None or notification.state != NotificationDeliveryState.PROCESSING.value:
                session.rollback()
                return False
            notification.state = NotificationDeliveryState.DELIVERED.value
            notification.claimed_at = None
            notification.delivered_at = delivered_at
            notification.last_error = None
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def record_monitor_notification_failure(
        self, notification_id: str, error: str, occurred_at: datetime
    ) -> NotificationDeliveryState:
        self.ensure_monitor_notification_tables()
        assert self.Session is not None
        session = self.Session()
        try:
            notification = session.get(MonitorNotification, UUID(notification_id))
            if notification is None:
                session.rollback()
                return NotificationDeliveryState.FAILED
            if notification.state != NotificationDeliveryState.PROCESSING.value:
                session.rollback()
                if notification.state == NotificationDeliveryState.CANCELLED.value:
                    return NotificationDeliveryState.CANCELLED
                return NotificationDeliveryState.FAILED

            notification.attempt_count += 1
            notification.last_error = sanitize_error_detail(error)
            notification.claimed_at = None
            if notification.attempt_count >= 5:
                notification.state = NotificationDeliveryState.FAILED.value
                notification.next_attempt_at = occurred_at
            else:
                notification.state = NotificationDeliveryState.PENDING.value
                notification.next_attempt_at = occurred_at + timedelta(minutes=2 ** (notification.attempt_count - 1))
            session.commit()
            return NotificationDeliveryState(notification.state)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _cancel_monitor_notifications_for_target(session: Any, target_id: int) -> None:
        session.query(MonitorNotification).filter(
            MonitorNotification.target_id == target_id,
            MonitorNotification.state.in_(
                (NotificationDeliveryState.PENDING.value, NotificationDeliveryState.PROCESSING.value)
            ),
        ).update({MonitorNotification.state: NotificationDeliveryState.CANCELLED.value}, synchronize_session=False)

    def _ensure_monitor_target_health_columns(self) -> None:
        from .model.stock_monitor_target import StockMonitorTarget

        assert self.engine is not None
        columns = {column["name"] for column in inspect(self.engine).get_columns(StockMonitorTarget.__tablename__)}
        timestamp_type = "TIMESTAMP WITH TIME ZONE" if self.engine.dialect.name == "postgresql" else "DATETIME"
        column_types = {
            "last_checked_at": timestamp_type,
            "latest_error_kind": "VARCHAR(32)",
            "latest_error_detail": "VARCHAR(240)",
            "latest_error_at": timestamp_type,
        }
        with self.engine.begin() as conn:
            for name, type_sql in column_types.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE {StockMonitorTarget.__tablename__} ADD COLUMN {name} {type_sql}"))

    def _migrate_sqlite_price_vs_ma_conditions(self) -> None:
        if self.engine is None or self.engine.dialect.name != "sqlite":
            return
        inspector = inspect(self.engine)
        if not inspector.has_table("stock_monitor_targets"):
            return
        columns = {column["name"] for column in inspector.get_columns("stock_monitor_targets")}
        if "condition" not in columns:
            return
        has_enabled = "enabled" in columns
        select_columns = ["id", "market", "frequency", "condition"]
        if has_enabled:
            select_columns.append("enabled")
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(f"SELECT {', '.join(select_columns)} FROM stock_monitor_targets ORDER BY id")
            ).mappings()
            for row in rows:
                condition = row["condition"]
                if isinstance(condition, str):
                    try:
                        parsed_condition = json.loads(condition)
                    except json.JSONDecodeError:
                        continue
                elif isinstance(condition, dict):
                    parsed_condition = dict(condition)
                else:
                    continue
                if parsed_condition.get("type") != "price_vs_ma":
                    continue
                original_direction = parsed_condition.get("direction")
                parsed_condition["type"] = "close_cross_ma"
                parsed_condition["direction"] = "above"
                supported = row["market"] == "A" and row["frequency"] == "daily" and original_direction == "above"
                assignments = "condition = :condition"
                parameters: dict[str, Any] = {"target_id": row["id"], "condition": json.dumps(parsed_condition)}
                if has_enabled and not supported:
                    assignments += ", enabled = false"
                    logging.warning(
                        "Migrated unsupported price_vs_ma monitor target id=%s market=%s to disabled close_cross_ma",
                        row["id"],
                        row["market"],
                    )
                conn.execute(
                    text(f"UPDATE stock_monitor_targets SET {assignments} WHERE id = :target_id"),
                    parameters,
                )

    # ------------------------------------------------------------------
    # Blackroom record CRUD
    # ------------------------------------------------------------------

    def create_blackroom_record(
        self,
        stock_code: str,
        market: str = "A",
        ban_days: Optional[int] = None,
        remaining_days: Optional[int] = None,
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
        if remaining_days is None:
            remaining_days = ban_days
        if expire_at is None and ban_days is not None:
            expire_at = effective_start + timedelta(days=ban_days)

        assert self.Session is not None
        session = self.Session()
        try:
            record = BlackroomRecord(
                stock_code=stock_code,
                market=market,
                ban_days=ban_days,
                remaining_days=remaining_days,
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

        有效条件：enabled=True 且 remaining_days > 0。

        Args:
            market: 可选，按市场过滤。
        Returns:
            BlackroomRecord 对象列表。
        """
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            query = session.query(BlackroomRecord).filter_by(enabled=True).filter(BlackroomRecord.remaining_days > 0)
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
            "remaining_days",
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
            if "ban_days" in updates and "remaining_days" not in updates:
                record.remaining_days = record.ban_days
            if ("ban_days" in updates or "start_at" in updates) and "expire_at" not in updates:
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

    def delete_blackroom_records_by_stock(self, stock_code: str, market: str) -> int:
        """按股票代码和市场删除黑屋记录，返回删除条数。"""
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            records = session.query(BlackroomRecord).filter_by(stock_code=stock_code, market=market).all()
            deleted = len(records)
            for record in records:
                session.delete(record)
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def countdown_blackroom_records(self) -> dict[str, int]:
        """递减有效黑屋记录剩余天数，并删除归零记录。"""
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            records = (
                session.query(BlackroomRecord)
                .filter_by(enabled=True)
                .filter(BlackroomRecord.remaining_days > 0)
                .order_by(BlackroomRecord.id.asc())
                .all()
            )
            decremented = len(records)
            for record in records:
                record.remaining_days = int(record.remaining_days or 0) - 1
            expired = [record for record in records if int(record.remaining_days or 0) <= 0]
            deleted = len(expired)
            for record in expired:
                session.delete(record)
            session.commit()
            return {"decremented": decremented, "deleted": deleted}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ensure_blackroom_records_table(self) -> None:
        """建表（若不存在）。在 DAG 启动时调用一次。"""
        from .model.blackroom_record import BlackroomRecord  # noqa: F401

        if self.engine.dialect.name == "postgresql" and not inspect(self.engine).has_table("blackroom_records"):
            return
        if self.engine.dialect.name != "postgresql":
            BlackroomRecord.__table__.create(self.engine, checkfirst=True)
        columns = {column["name"] for column in inspect(self.engine).get_columns("blackroom_records")}
        if "remaining_days" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text("ALTER TABLE blackroom_records ADD COLUMN remaining_days INTEGER"))
                conn.execute(
                    text(
                        """
                        UPDATE blackroom_records
                        SET remaining_days = ban_days
                        WHERE remaining_days IS NULL AND ban_days IS NOT NULL
                        """
                    )
                )

    # ------------------------------------------------------------------
    # Paper trading schema bootstrap / upgrade
    # ------------------------------------------------------------------

    def ensure_paper_trading_schema(self) -> None:
        """Create or upgrade paper trading tables/columns.

        - Creates ``paper_trade_validity_checks`` if it does not exist.
        - Adds validity columns to an existing ``paper_orders`` table that
          predates the validity-analysis feature.
        - Adds fee columns to an existing ``paper_accounts`` table that
          predates the configurable-fees feature.
        - Adds ``comment`` column to ``paper_orders`` and ``paper_trades``
          for the optional order/trade comment feature.
        - Adds snapshot series metadata, backfills legacy rows, drops the
          old account/date unique constraint or unique index, and inserts
          at most one initial NAV=1 point for each eligible positive-cash
          account.

        Safe to call even when the ``paper_orders`` table does not exist yet
        (e.g. on a fresh install where ``Base.metadata.create_all`` will
        create it with the correct columns).

        Called once per process from ``__init__``.
        """
        from .model.paper_trading import (  # noqa: F401
            DailyBarDiagnostic,
            PaperCorporateAction,
            PaperLedgerRebuild,
            PaperOrderEvent,
            PaperTradeValidityCheck,
            PaperValuationGap,
        )

        has_paper_orders = inspect(self.engine).has_table(tb_name_paper_orders)
        has_paper_accounts = inspect(self.engine).has_table(tb_name_paper_accounts)
        has_current_users = _has_current_schema_table(self.engine, "users")
        ownership_schema_present = self.engine.dialect.name == "postgresql" and (
            "owner_user_id" in _current_schema_columns(self.engine, tb_name_paper_accounts) and has_current_users
        )
        if self.engine.dialect.name == "postgresql":
            from paper_trading.storage.enum_migration import migrate_paper_trading_enums

            with self.engine.begin() as conn:
                migrate_paper_trading_enums(conn)
        if self.engine.dialect.name != "postgresql" and has_paper_accounts:
            PaperCorporateAction.__table__.create(self.engine, checkfirst=True)
            PaperOrderEvent.__table__.create(self.engine, checkfirst=True)
        self._ensure_paper_cash_ledger_columns()
        self._ensure_sqlite_replay_time_provenance_columns()
        if self.engine.dialect.name == "sqlite":
            self._widen_sqlite_numeric_columns()
        if self.engine.dialect.name != "postgresql" and has_paper_orders:
            PaperTradeValidityCheck.__table__.create(self.engine, checkfirst=True)
            PaperLedgerRebuild.__table__.create(self.engine, checkfirst=True)
            PaperValuationGap.__table__.create(self.engine, checkfirst=True)
            DailyBarDiagnostic.__table__.create(self.engine, checkfirst=True)

        if self.engine.dialect.name == "postgresql" and has_paper_accounts:
            self._widen_postgresql_numeric_columns(
                tb_name_paper_accounts,
                {column_name: "NUMERIC(30, 12)" for column_name in _PAPER_ACCOUNT_ACCOUNTING_COLUMNS},
            )
            for table_name, column_names in _PAPER_SQLITE_PRECISION_COLUMNS.items():
                self._widen_postgresql_numeric_columns(
                    table_name,
                    {column_name: "NUMERIC(30, 12)" for column_name in column_names},
                )

        if inspect(self.engine).has_table(tb_name_paper_position_lots):
            lot_columns = {c["name"] for c in inspect(self.engine).get_columns(tb_name_paper_position_lots)}
            if "projected_cost_price" not in lot_columns:
                with self.engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE {tb_name_paper_position_lots} "
                            "ADD COLUMN projected_cost_price NUMERIC(30, 12) NOT NULL DEFAULT 0"
                        )
                    )
                    conn.execute(text(f"UPDATE {tb_name_paper_position_lots} SET projected_cost_price = cost_price"))

        if self.engine.dialect.name == "sqlite" and has_paper_accounts:
            account_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_accounts)}
            if "owner_user_id" not in account_columns:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_accounts} ADD COLUMN owner_user_id INTEGER"))

        if not has_paper_orders:
            self._ensure_postgresql_paper_account_ownership(ownership_schema_present, has_paper_accounts)
            self._ensure_paper_account_repair_without_orders()
            return

        if self.engine.dialect.name == "postgresql":
            with self.engine.begin() as conn:
                legacy_constraint = conn.execute(
                    text(
                        """
                        SELECT con.conname
                        FROM pg_constraint con
                        JOIN pg_class rel ON rel.oid = con.conrelid
                        WHERE rel.relname = :table_name
                          AND con.contype = 'u'
                          AND pg_get_constraintdef(con.oid) LIKE '%UNIQUE (idempotency_key)%'
                        """
                    ),
                    {"table_name": tb_name_paper_orders},
                ).scalar_one_or_none()
                if legacy_constraint:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_orders} DROP CONSTRAINT {legacy_constraint}"))
                if not legacy_constraint:
                    legacy_index = conn.execute(
                        text(
                            """
                            SELECT indexname
                            FROM pg_indexes
                            WHERE tablename = :table_name
                              AND indexdef LIKE '%(idempotency_key)%'
                              AND indexdef NOT LIKE '%(account_id, idempotency_key)%'
                            """
                        ),
                        {"table_name": tb_name_paper_orders},
                    ).scalar_one_or_none()
                    if legacy_index:
                        conn.execute(text(f"DROP INDEX IF EXISTS {legacy_index}"))
                conn.execute(
                    text(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_orders_account_idempotency_key "
                        f"ON {tb_name_paper_orders} (account_id, idempotency_key) "
                        "WHERE idempotency_key IS NOT NULL"
                    )
                )

        columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_orders)}
        if inspect(self.engine).has_table(tb_name_paper_matching_runs):
            run_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_matching_runs)}
            if "warning_count" not in run_columns:
                with self.engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE {tb_name_paper_matching_runs} "
                            "ADD COLUMN warning_count INTEGER NOT NULL DEFAULT 0"
                        )
                    )
            if "scope_key" not in run_columns:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_matching_runs} ADD COLUMN scope_key VARCHAR(40)"))
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        f"UPDATE {tb_name_paper_matching_runs} "
                        "SET scope_key = COALESCE(CAST(account_id AS VARCHAR(40)), 'all') "
                        "WHERE scope_key IS NULL"
                    )
                )
                if self.engine.dialect.name == "postgresql":
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_matching_runs} ALTER COLUMN scope_key SET NOT NULL"))
            if self.engine.dialect.name == "sqlite":
                with self.engine.begin() as conn:
                    conn.execute(
                        text(
                            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_matching_active_scope "
                            f"ON {tb_name_paper_matching_runs} (trade_date, scope_key) WHERE status = 'running'"
                        )
                    )
            elif self.engine.dialect.name == "postgresql":
                with self.engine.begin() as conn:
                    conn.execute(
                        text(
                            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_matching_active_scope "
                            f"ON {tb_name_paper_matching_runs} (trade_date, scope_key) WHERE status = 'running'"
                        )
                    )
        if "validity_status" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_orders} ADD COLUMN validity_status VARCHAR(20)"))
        if "validity_reason" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_orders} ADD COLUMN validity_reason VARCHAR(50)"))
        if "validity_checked_at" not in columns:
            with self.engine.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE {tb_name_paper_orders} ADD COLUMN validity_checked_at TIMESTAMP WITH TIME ZONE")
                )

        if has_paper_accounts:
            account_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_accounts)}
            account_fee_columns = {
                "fee_preset": "VARCHAR(30) NOT NULL DEFAULT 'a_share'",
                "commission_rate": "NUMERIC(20, 8) NOT NULL DEFAULT 0.0003",
                "min_commission": "NUMERIC(20, 4) NOT NULL DEFAULT 5.00",
                "stamp_duty_rate": "NUMERIC(20, 8) NOT NULL DEFAULT 0.0005",
                "transfer_fee_rate": "NUMERIC(20, 8) NOT NULL DEFAULT 0.00001",
            }
            hk_account_fee_columns = {
                "hk_commission_rate": "NUMERIC(20, 8)",
                "hk_min_commission": "NUMERIC(20, 4)",
                "hk_stamp_duty_rate": "NUMERIC(20, 8)",
                "hk_trading_fee_rate": "NUMERIC(20, 8)",
                "hk_sfc_levy_rate": "NUMERIC(20, 8)",
                "hk_afrc_levy_rate": "NUMERIC(20, 8)",
                "hk_settlement_fee_rate": "NUMERIC(20, 8)",
                "etf_commission_rate": "NUMERIC(20, 8)",
            }
            account_fee_columns.update(hk_account_fee_columns)
            for column_name, ddl in account_fee_columns.items():
                if column_name not in account_columns:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {tb_name_paper_accounts} ADD COLUMN {column_name} {ddl}"))
            account_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_accounts)}
            account_nav_columns = {
                "share_count": "NUMERIC(30, 12) NOT NULL DEFAULT 0",
                "net_asset_value": "NUMERIC(30, 12) NOT NULL DEFAULT 1",
                "cumulative_deposit": "NUMERIC(30, 12) NOT NULL DEFAULT 0",
                "cumulative_withdrawal": "NUMERIC(30, 12) NOT NULL DEFAULT 0",
                "realized_pnl": "NUMERIC(30, 12) NOT NULL DEFAULT 0",
            }
            missing_account_nav_columns = [
                column_name for column_name in account_nav_columns if column_name not in account_columns
            ]
            for column_name in missing_account_nav_columns:
                ddl = account_nav_columns[column_name]
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_accounts} ADD COLUMN {column_name} {ddl}"))
            if missing_account_nav_columns:
                backfill_values = {
                    "share_count": "initial_cash",
                    "net_asset_value": "1",
                    "cumulative_deposit": "initial_cash",
                    "cumulative_withdrawal": "0",
                    "realized_pnl": "0",
                }
                assignments = ", ".join(
                    f"{column_name} = {backfill_values[column_name]}" for column_name in missing_account_nav_columns
                )
                with self.engine.begin() as conn:
                    conn.execute(text(f"UPDATE {tb_name_paper_accounts} SET {assignments}"))
            if self.engine.dialect.name != "postgresql":
                self._ensure_sqlite_paper_account_repair_metadata()
        has_paper_snapshots = inspect(self.engine).has_table(tb_name_paper_account_snapshots)
        if self.engine.dialect.name == "postgresql" and (has_paper_accounts or has_paper_snapshots):
            with self.engine.begin() as conn:
                self._ensure_paper_account_snapshot_series(conn)
        elif has_paper_snapshots:
            self._ensure_sqlite_paper_account_snapshot_series()

        self._ensure_postgresql_paper_account_ownership(ownership_schema_present, has_paper_accounts)
        if inspect(self.engine).has_table(tb_name_paper_ledger_rebuilds):
            rebuild_columns = {
                column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_ledger_rebuilds)
            }
            rebuild_audit_columns = {
                "trigger_evidence": "JSON NOT NULL DEFAULT '{}'",
                "finished_at": "TIMESTAMP WITH TIME ZONE",
            }
            for column_name, ddl in rebuild_audit_columns.items():
                if column_name not in rebuild_columns:
                    with self.engine.begin() as conn:
                        conn.execute(
                            text(f"ALTER TABLE {tb_name_paper_ledger_rebuilds} ADD COLUMN {column_name} {ddl}")
                        )

        if "comment" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_orders} ADD COLUMN comment TEXT"))

        if inspect(self.engine).has_table(tb_name_paper_trades):
            trade_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_trades)}
            if "comment" not in trade_columns:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_trades} ADD COLUMN comment TEXT"))

        # Add source marker columns to positions and lots tables.
        source_ddl = "VARCHAR(20) NOT NULL DEFAULT 'trade'"
        for tb_name in (tb_name_paper_positions, tb_name_paper_position_lots):
            if inspect(self.engine).has_table(tb_name):
                cols = {c["name"] for c in inspect(self.engine).get_columns(tb_name)}
                if "source" not in cols:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {tb_name} ADD COLUMN source {source_ddl}"))

        market_ddl = "VARCHAR(20) NOT NULL DEFAULT 'a_share'"
        for tb_name in (
            tb_name_paper_positions,
            tb_name_paper_position_lots,
            tb_name_paper_orders,
            tb_name_paper_trades,
            tb_name_paper_trade_validity_checks,
        ):
            if inspect(self.engine).has_table(tb_name):
                market_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name)}
                if "market" not in market_columns:
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {tb_name} ADD COLUMN market {market_ddl}"))

    def _ensure_paper_account_repair_without_orders(self) -> None:
        has_paper_accounts = inspect(self.engine).has_table(tb_name_paper_accounts)
        has_paper_snapshots = inspect(self.engine).has_table(tb_name_paper_account_snapshots)
        if self.engine.dialect.name == "postgresql" and (has_paper_accounts or has_paper_snapshots):
            with self.engine.begin() as conn:
                self._ensure_paper_account_snapshot_series(conn)
            return
        if has_paper_accounts:
            self._ensure_sqlite_paper_account_repair_metadata()
        if has_paper_snapshots:
            self._ensure_sqlite_paper_account_snapshot_series()

    def _ensure_postgresql_paper_account_ownership(
        self, schema_signal: bool | None = None, had_accounts_at_startup: bool = True
    ) -> None:
        if self.engine.dialect.name != "postgresql" or not _has_current_schema_table(
            self.engine, tb_name_paper_accounts
        ):
            return
        account_columns = _current_schema_columns(self.engine, tb_name_paper_accounts)
        has_users = _has_current_schema_table(self.engine, "users")
        has_auth_schema = (
            schema_signal if schema_signal is not None else "owner_user_id" in account_columns and has_users
        )
        if not had_accounts_at_startup and not schema_signal:
            return
        if not has_auth_schema and not os.environ.get("AUTH_OWNER_EMAIL", "").strip():
            return
        if not has_users or not _has_current_schema_table(self.engine, "auth_tokens"):
            Base.metadata.create_all(self.engine, tables=[User.__table__, AuthToken.__table__], checkfirst=True)
        if "owner_user_id" not in account_columns:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_accounts} ADD COLUMN owner_user_id INTEGER"))
        self._backfill_paper_account_ownership()
        if not _has_paper_account_owner_foreign_key(self.engine):
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {tb_name_paper_accounts} "
                        "ADD CONSTRAINT fk_paper_accounts_owner_user_id_users "
                        "FOREIGN KEY (owner_user_id) REFERENCES users(id)"
                    )
                )

    def _ensure_sqlite_paper_account_repair_metadata(self) -> None:
        if not inspect(self.engine).has_table(tb_name_paper_accounts):
            return
        account_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_accounts)}
        if _PAPER_ACCOUNT_REPAIR_REASON_COLUMN in account_columns:
            return
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {tb_name_paper_accounts} ADD COLUMN "
                    f"{_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} {_SQLITE_PAPER_ACCOUNT_REPAIR_REASON_DDL}"
                )
            )

    def _ensure_sqlite_paper_account_snapshot_series(self) -> None:
        snapshot_columns = {
            column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_account_snapshots)
        }
        for column_name, ddl in _PAPER_SNAPSHOT_NAV_COLUMNS.items():
            if column_name not in snapshot_columns:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ADD COLUMN {column_name} {ddl}"))
        snapshot_columns = {
            column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_account_snapshots)
        }
        missing_series = {
            column_name: ddl
            for column_name, ddl in _SQLITE_PAPER_SNAPSHOT_SERIES_COLUMNS.items()
            if column_name not in snapshot_columns
        }
        for column_name, ddl in missing_series.items():
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ADD COLUMN {column_name} {ddl}"))
        if missing_series:
            assignments: list[str] = []
            if "event_at" in missing_series:
                assignments.append("event_at = COALESCE(created_at, event_at)")
            if "quality_status" in missing_series:
                assignments.append(
                    "quality_status = CASE "
                    "WHEN net_asset_value IS NULL THEN 'invalid' "
                    "WHEN CAST(net_asset_value AS TEXT) IN ('NaN', 'Infinity', '-Infinity') THEN 'invalid' "
                    "WHEN CAST(net_asset_value AS REAL) <= 0 THEN 'invalid' "
                    "ELSE 'valid' END"
                )
            if "invalid_reason" in missing_series:
                assignments.append(
                    "invalid_reason = CASE "
                    "WHEN net_asset_value IS NULL THEN 'missing_nav' "
                    "WHEN CAST(net_asset_value AS TEXT) IN ('NaN', 'Infinity', '-Infinity') THEN 'non_finite_nav' "
                    "WHEN CAST(net_asset_value AS REAL) <= 0 THEN 'non_positive_nav' "
                    "ELSE NULL END"
                )
            if assignments:
                with self.engine.begin() as conn:
                    conn.execute(text(f"UPDATE {tb_name_paper_account_snapshots} SET {', '.join(assignments)}"))
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_paper_account_snapshots_account_event "
                    f"ON {tb_name_paper_account_snapshots} (account_id, event_at, id)"
                )
            )
            conn.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_account_snapshots_account_initial "
                    f"ON {tb_name_paper_account_snapshots} (account_id) WHERE point_type = 'initial'"
                )
            )
        with self.engine.begin() as conn:
            self._ensure_sqlite_snapshot_trading_identity(conn)
            self._classify_sqlite_legacy_paper_account_chronology(conn)

    def _backfill_paper_account_ownership(self) -> None:
        if not _has_current_schema_table(self.engine, tb_name_paper_accounts):
            return
        with self.engine.begin() as conn:
            has_unowned = conn.execute(
                text(f"SELECT 1 FROM {tb_name_paper_accounts} WHERE owner_user_id IS NULL LIMIT 1")
            ).first()
        if has_unowned is None:
            return
        owner_email = os.environ.get("AUTH_OWNER_EMAIL")
        if not owner_email or not owner_email.strip():
            raise RuntimeError("AUTH_OWNER_EMAIL must identify exactly one verified user for paper account ownership")
        owner_email = owner_email.strip().lower()
        if not _has_current_schema_table(self.engine, "users"):
            raise RuntimeError("AUTH_OWNER_EMAIL must identify exactly one verified user for paper account ownership")
        with self.engine.begin() as conn:
            matches = conn.execute(
                text("SELECT id FROM users WHERE email = :email AND email_verified_at IS NOT NULL ORDER BY id ASC"),
                {"email": owner_email},
            ).fetchall()
            if len(matches) != 1:
                raise RuntimeError(
                    "AUTH_OWNER_EMAIL must identify exactly one verified user for paper account ownership"
                )
            owner_user_id = matches[0][0]
            conn.execute(
                text(f"UPDATE {tb_name_paper_accounts} SET owner_user_id = :owner_user_id WHERE owner_user_id IS NULL"),
                {"owner_user_id": owner_user_id},
            )

    def _classify_sqlite_legacy_paper_account_chronology(self, conn) -> None:
        if not inspect(conn).has_table(tb_name_paper_accounts):
            return
        account_columns = self._table_column_names(conn, tb_name_paper_accounts)
        if _PAPER_ACCOUNT_REPAIR_REASON_COLUMN not in account_columns:
            return
        predicates = [
            "account.created_at IS NULL",
            "account.initial_cash IS NULL",
            "CAST(account.initial_cash AS TEXT) IN ('NaN', 'Infinity', '-Infinity')",
            "CAST(account.initial_cash AS REAL) <= 0",
        ]
        predicates.extend(self._sqlite_legacy_source_predicates(conn))
        invalid_ledger_accounts = self._sqlite_invalid_cash_ledger_accounts(conn)
        if invalid_ledger_accounts:
            predicates.append(f"account.id IN ({', '.join(str(account_id) for account_id in invalid_ledger_accounts)})")
        predicates.append(self._sqlite_initial_snapshot_uncertain(conn))
        conn.execute(
            text(
                f"""
                UPDATE {tb_name_paper_accounts} AS account
                SET {_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} = 'legacy_ordering_uncertain'
                WHERE account.{_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} IS NULL
                  AND ({" OR ".join(predicates)})
                """
            )
        )

    def _sqlite_initial_snapshot_uncertain(self, conn) -> str:
        columns = self._table_column_names(conn, tb_name_paper_account_snapshots)
        required = {
            "trade_date",
            "event_at",
            "point_type",
            "cash_available",
            "total_assets",
            "net_asset_value",
            "share_count",
        }
        if not required <= columns:
            return "1 = 1"
        provenance = (
            "snapshot.event_time_provenance IS 'canonical_utc'" if "event_time_provenance" in columns else "1 = 0"
        )
        return f"""EXISTS (
            SELECT 1 FROM {tb_name_paper_account_snapshots} AS snapshot
            WHERE snapshot.account_id = account.id
              AND snapshot.point_type = 'initial'
              AND NOT (
                  {provenance}
                  AND date(snapshot.trade_date) = date(account.created_at)
                  AND datetime(snapshot.event_at) = datetime(account.created_at)
                  AND snapshot.cash_available = account.initial_cash
                  AND snapshot.total_assets = account.initial_cash
                  AND snapshot.net_asset_value = 1
                  AND snapshot.share_count = account.initial_cash
              )
        )"""

    def _sqlite_legacy_source_predicates(self, conn) -> list[str]:
        predicates: list[str] = []
        if not inspect(conn).has_table(tb_name_paper_cash_ledger) and inspect(conn).has_table(
            tb_name_paper_account_snapshots
        ):
            predicates.append(
                f"EXISTS (SELECT 1 FROM {tb_name_paper_account_snapshots} AS source "
                "WHERE source.account_id = account.id AND source.point_type IS NOT 'initial')"
            )
        for table_name, timestamp_columns, date_columns in _LEGACY_CHRONOLOGY_SOURCES:
            if not inspect(conn).has_table(table_name):
                continue
            columns = self._table_column_names(conn, table_name)
            expected = (*timestamp_columns, *date_columns)
            account_match = self._legacy_chronology_account_match(table_name, columns)
            if any(column not in columns for column in expected):
                predicates.append(f"EXISTS (SELECT 1 FROM {table_name} AS source WHERE {account_match})")
                continue
            timestamp_checks = [
                f"source.{column} IS NULL OR datetime(source.{column}) < datetime(account.created_at)"
                for column in timestamp_columns
            ]
            date_checks = [
                f"source.{column} IS NULL OR date(source.{column}) < date(account.created_at)"
                for column in date_columns
            ]
            conflict = ""
            if timestamp_columns and date_columns:
                conflict = " OR " + " OR ".join(
                    f"date(source.{date_column}) != date(source.{timestamp_column})"
                    for timestamp_column in timestamp_columns
                    for date_column in date_columns
                )
            checks = " OR ".join((*timestamp_checks, *date_checks)) + conflict
            if table_name in _SQLITE_PAPER_REPLAY_PROVENANCE_TABLES:
                provenance = (
                    "source.event_time_provenance IS NOT 'canonical_utc'"
                    if "event_time_provenance" in columns
                    else "1 = 1"
                )
                checks = f"{checks} OR {provenance}"
            if table_name == tb_name_paper_account_snapshots:
                checks = f"{checks} OR source.quality_status IS NOT 'valid'"
            predicates.append(f"EXISTS (SELECT 1 FROM {table_name} AS source WHERE {account_match} AND ({checks}))")
        return predicates

    def _sqlite_invalid_cash_ledger_accounts(self, conn) -> tuple[int, ...]:
        from paper_trading.domain.enums import CashEventType

        if not inspect(conn).has_table(tb_name_paper_cash_ledger):
            return ()
        columns = self._table_column_names(conn, tb_name_paper_cash_ledger)
        numeric_columns = ("amount", "net_asset_value", "share_delta", "rounding_residual")
        if not all(column in columns for column in numeric_columns):
            return tuple(
                row[0] for row in conn.execute(text(f"SELECT DISTINCT account_id FROM {tb_name_paper_cash_ledger}"))
            )
        rows = conn.execute(
            text(
                f"""
                SELECT account_id, event_type,
                       CAST(amount AS TEXT),
                       CAST(net_asset_value AS TEXT),
                       CAST(share_delta AS TEXT),
                       CAST(rounding_residual AS TEXT),
                       typeof(amount), typeof(net_asset_value),
                       typeof(share_delta), typeof(rounding_residual)
                FROM {tb_name_paper_cash_ledger}
                """
            )
        )
        invalid_accounts: set[int] = set()
        valid_event_types = {event_type.value for event_type in CashEventType}
        for account_id, event_type, amount, nav, share_delta, residual, *value_types in rows:
            if event_type not in valid_event_types or any(value_type != "text" for value_type in value_types):
                invalid_accounts.add(account_id)
                continue
            try:
                values = tuple(Decimal(str(value)) for value in (amount, nav, share_delta, residual))
            except (InvalidOperation, TypeError, ValueError):
                invalid_accounts.add(account_id)
                continue
            amount_value, nav_value, shares_value, residual_value = values
            if (
                not all(value.is_finite() for value in values)
                or nav_value <= 0
                or (event_type == "deposit" and (amount_value <= 0 or shares_value <= 0))
                or (event_type == "withdrawal" and (amount_value >= 0 or shares_value >= 0))
                or amount_value != shares_value * nav_value + residual_value
            ):
                invalid_accounts.add(account_id)
        return tuple(sorted(invalid_accounts))

    def _ensure_sqlite_snapshot_trading_identity(self, conn) -> None:
        snapshot_columns = {column["name"] for column in inspect(conn).get_columns(tb_name_paper_account_snapshots)}
        if "point_type" not in snapshot_columns or "trade_date" not in snapshot_columns:
            return
        duplicates = conn.execute(
            text(
                f"""
                SELECT account_id, trade_date
                FROM {tb_name_paper_account_snapshots}
                WHERE point_type = 'trading'
                GROUP BY account_id, trade_date
                HAVING COUNT(*) > 1
                """
            )
        ).all()
        if duplicates:
            raise RuntimeError("duplicate trading snapshots")
        for column_name, ddl in (
            ("valuation_quality", "VARCHAR(20)"),
            ("valuation_details", "JSON"),
        ):
            if column_name not in snapshot_columns:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ADD COLUMN {column_name} {ddl}"))
        conn.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_account_snapshots_account_trading "
                f"ON {tb_name_paper_account_snapshots} (account_id, trade_date) WHERE point_type = 'trading'"
            )
        )

    def _ensure_paper_account_snapshot_series(self, conn) -> None:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:lock_key AS text), 0))"),
            {"lock_key": _PAPER_SNAPSHOT_SERIES_LOCK_KEY},
        )
        self._ensure_paper_account_repair_metadata(conn)
        if not inspect(conn).has_table(tb_name_paper_account_snapshots):
            return
        self._ensure_paper_snapshot_series_metadata(conn)
        self._backfill_paper_snapshot_series_quality(conn)
        from paper_trading.storage.enum_migration import ensure_snapshot_valuation_metadata

        ensure_snapshot_valuation_metadata(conn)
        self._classify_legacy_paper_account_chronology(conn)
        self._insert_paper_account_initial_baselines(conn)

    def _table_column_names(self, conn, table_name: str) -> set[str]:
        return {column["name"] for column in inspect(conn).get_columns(table_name)}

    def _ensure_paper_cash_ledger_columns(self) -> None:
        if not inspect(self.engine).has_table(tb_name_paper_cash_ledger):
            return
        cash_ledger_columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name_paper_cash_ledger)}
        cash_ledger_nav_columns = {
            "trade_date": "DATE",
            "net_asset_value": "NUMERIC(30, 12)",
            "share_delta": "NUMERIC(30, 12)",
            "rounding_residual": "NUMERIC(30, 24) NOT NULL DEFAULT 0",
        }
        for column_name, ddl in cash_ledger_nav_columns.items():
            if column_name not in cash_ledger_columns:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {tb_name_paper_cash_ledger} ADD COLUMN {column_name} {ddl}"))
        if self.engine.dialect.name == "postgresql":
            self._widen_postgresql_numeric_columns(
                tb_name_paper_cash_ledger,
                {
                    "amount": "NUMERIC(30, 12)",
                    "net_asset_value": "NUMERIC(30, 12)",
                    "share_delta": "NUMERIC(30, 12)",
                    "rounding_residual": "NUMERIC(30, 24)",
                },
            )

    def _ensure_sqlite_replay_time_provenance_columns(self) -> None:
        if self.engine.dialect.name != "sqlite":
            return
        for table_name in _SQLITE_PAPER_REPLAY_PROVENANCE_TABLES:
            if not inspect(self.engine).has_table(table_name):
                continue
            columns = {column["name"] for column in inspect(self.engine).get_columns(table_name)}
            if "event_time_provenance" not in columns:
                with self.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN event_time_provenance VARCHAR(20)"))

    def _widen_sqlite_numeric_columns(self) -> None:
        for table_name, column_names in _PAPER_SQLITE_PRECISION_COLUMNS.items():
            if not inspect(self.engine).has_table(table_name):
                continue
            columns = {column["name"]: column for column in inspect(self.engine).get_columns(table_name)}
            targets = [
                name
                for name in column_names
                if name in columns
                and self._sqlite_numeric_target_exceeds_existing(
                    columns[name]["type"], self._sqlite_numeric_target(table_name, name)
                )
            ]
            if targets:
                self._rebuild_sqlite_numeric_table(table_name, targets)

    @staticmethod
    def _sqlite_numeric_target_exceeds_existing(existing_type: Any, target_type: Numeric) -> bool:
        """Return whether either target numeric dimension needs more capacity."""
        precision = getattr(existing_type, "precision", None)
        scale = getattr(existing_type, "scale", None)
        return (
            precision is not None
            and scale is not None
            and (precision < target_type.precision or scale < target_type.scale)
        )

    @staticmethod
    def _sqlite_numeric_target(table_name: str, column_name: str) -> Numeric:
        if table_name == tb_name_paper_cash_ledger and column_name == "rounding_residual":
            return Numeric(30, 24)
        return Numeric(30, 12)

    def _rebuild_sqlite_numeric_table(self, table_name: str, target_columns: list[str]) -> None:
        metadata = MetaData()
        table = Table(table_name, metadata, autoload_with=self.engine)
        index_sql = self._sqlite_index_sql(table_name)
        for column_name in target_columns:
            existing_type = table.c[column_name].type
            target_type = self._sqlite_numeric_target(table_name, column_name)
            existing_numeric = cast(Numeric, existing_type)
            table.c[column_name].type = Numeric(
                max(existing_numeric.precision or 0, target_type.precision or 0),
                max(existing_numeric.scale or 0, target_type.scale or 0),
            )
        temp_name = f"{table_name}__precision_upgrade"
        table.name = temp_name
        for index in list(table.indexes):
            table.indexes.remove(index)

        # SQLite only applies this pragma outside a transaction. A raw connection
        # also keeps this entire rebuild on the connection whose FK setting changes.
        raw_connection = self.engine.raw_connection()
        cursor = raw_connection.cursor()
        foreign_keys_enabled = cursor.execute("PRAGMA foreign_keys").fetchone()[0]
        try:
            raw_connection.rollback()
            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute("BEGIN")
            quote = self.engine.dialect.identifier_preparer.quote
            quoted_table = quote(table_name)
            quoted_temp = quote(temp_name)
            column_names = ", ".join(quote(column.name) for column in table.columns)
            cursor.execute(f"DROP TABLE IF EXISTS {quoted_temp}")
            cursor.execute(str(CreateTable(table).compile(dialect=self.engine.dialect)))
            cursor.execute(f"INSERT INTO {quoted_temp} ({column_names}) SELECT {column_names} FROM {quoted_table}")
            cursor.execute(f"DROP TABLE {quoted_table}")
            cursor.execute(f"ALTER TABLE {quoted_temp} RENAME TO {quoted_table}")
            for sql in index_sql:
                cursor.execute(sql)
            violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise IntegrityError("PRAGMA foreign_key_check", None, violations)
            raw_connection.commit()
        except Exception:
            raw_connection.rollback()
            raise
        finally:
            # PRAGMA foreign_keys is a no-op inside a transaction. Ensure the
            # successful commit or failed rollback has ended it before putting
            # the connection back into the pool with its original setting.
            raw_connection.rollback()
            cursor.execute(f"PRAGMA foreign_keys = {foreign_keys_enabled}")
            cursor.close()
            raw_connection.close()

    def _sqlite_index_sql(self, table_name: str) -> list[str]:
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = 'index' AND tbl_name = :table_name AND sql IS NOT NULL"
                    ),
                    {"table_name": table_name},
                ).scalars()
            )

    def _widen_postgresql_numeric_columns(self, table_name: str, column_types: dict[str, str], conn=None) -> None:
        if self.engine.dialect.name != "postgresql":
            return
        connection = conn or self.engine.connect()
        owns_connection = conn is None
        try:
            if not inspect(connection).has_table(table_name):
                return
            existing: dict[str, str] = {}
            for column in inspect(connection).get_columns(table_name):
                column_name = column["name"]
                target = column_types.get(column_name)
                if target is None:
                    continue
                precision = getattr(column["type"], "precision", None)
                scale = getattr(column["type"], "scale", None)
                target_precision, target_scale = _numeric_precision_scale(target)
                if precision is None or scale is None:
                    continue
                if precision < target_precision or scale < target_scale:
                    widened_precision = max(precision, target_precision)
                    widened_scale = max(scale, target_scale)
                    existing[column_name] = f"NUMERIC({widened_precision}, {widened_scale})"
            if not existing:
                return
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    + ", ".join(
                        f"ALTER COLUMN {column_name} TYPE {target_type}"
                        for column_name, target_type in existing.items()
                    )
                )
            )
        finally:
            if owns_connection:
                connection.commit()
                connection.close()

    def _ensure_paper_account_repair_metadata(self, conn) -> None:
        from paper_trading.domain.enums import MigrationRepairReason

        if not inspect(conn).has_table(tb_name_paper_accounts):
            return
        type_exists = conn.execute(
            text(
                """
                SELECT 1
                FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE n.nspname = current_schema()
                  AND t.typname = :type_name
                """
            ),
            {"type_name": _PAPER_ACCOUNT_REPAIR_REASON_TYPE},
        ).scalar_one_or_none()
        if type_exists is None:
            conn.execute(
                text(
                    f"CREATE TYPE {_PAPER_ACCOUNT_REPAIR_REASON_TYPE} AS ENUM "
                    f"('{MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value}')"
                )
            )
        if _PAPER_ACCOUNT_REPAIR_REASON_COLUMN not in self._table_column_names(conn, tb_name_paper_accounts):
            conn.execute(
                text(
                    f"ALTER TABLE {tb_name_paper_accounts} "
                    f"ADD COLUMN {_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} {_PAPER_ACCOUNT_REPAIR_REASON_TYPE}"
                )
            )
            return
        observed_type = conn.execute(
            text(
                """
                SELECT t.typname
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_type t ON t.oid = a.atttypid
                WHERE n.nspname = current_schema()
                  AND c.relname = :table_name
                  AND a.attname = :column_name
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                """
            ),
            {"table_name": tb_name_paper_accounts, "column_name": _PAPER_ACCOUNT_REPAIR_REASON_COLUMN},
        ).scalar_one_or_none()
        if observed_type == _PAPER_ACCOUNT_REPAIR_REASON_TYPE:
            return
        conn.execute(
            text(
                f"ALTER TABLE {tb_name_paper_accounts} "
                f"ALTER COLUMN {_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} "
                f"TYPE {_PAPER_ACCOUNT_REPAIR_REASON_TYPE} "
                f"USING {_PAPER_ACCOUNT_REPAIR_REASON_COLUMN}::text::{_PAPER_ACCOUNT_REPAIR_REASON_TYPE}"
            )
        )

    def _ensure_paper_snapshot_series_metadata(self, conn) -> None:
        from paper_trading.storage.enum_migration import ensure_snapshot_series_enum_types

        ensure_snapshot_series_enum_types(conn)
        snapshot_columns = self._table_column_names(conn, tb_name_paper_account_snapshots)
        self._widen_postgresql_numeric_columns(
            tb_name_paper_account_snapshots,
            {column_name: "NUMERIC(30, 12)" for column_name in _PAPER_SNAPSHOT_ACCOUNTING_COLUMNS},
            conn=conn,
        )
        for column_name, ddl in _PAPER_SNAPSHOT_NAV_COLUMNS.items():
            if column_name not in snapshot_columns:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ADD COLUMN {column_name} {ddl}"))
        snapshot_columns = self._table_column_names(conn, tb_name_paper_account_snapshots)
        series_columns = {
            "point_type": "paper_snapshot_point_type",
            "event_at": "TIMESTAMP WITH TIME ZONE",
            "quality_status": "paper_snapshot_quality_status",
            "invalid_reason": "TEXT",
        }
        for column_name, ddl in series_columns.items():
            if column_name not in snapshot_columns:
                conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ADD COLUMN {column_name} {ddl}"))

    def _backfill_paper_snapshot_series_quality(self, conn) -> None:
        conn.execute(
            text(
                f"""
                UPDATE {tb_name_paper_account_snapshots}
                SET
                    point_type = COALESCE(point_type, 'trading'),
                    quality_status = CASE
                        WHEN event_at IS NOT NULL AND quality_status IS NOT NULL THEN quality_status
                        WHEN net_asset_value IS NULL THEN 'invalid'
                        WHEN net_asset_value::text IN ('NaN', 'Infinity', '-Infinity') THEN 'invalid'
                        WHEN net_asset_value <= 0 THEN 'invalid'
                        ELSE 'valid'
                    END,
                    invalid_reason = CASE
                        WHEN event_at IS NOT NULL AND quality_status IS NOT NULL THEN invalid_reason
                        WHEN net_asset_value IS NULL THEN 'missing_nav'
                        WHEN net_asset_value::text IN ('NaN', 'Infinity', '-Infinity') THEN 'non_finite_nav'
                        WHEN net_asset_value <= 0 THEN 'non_positive_nav'
                        ELSE NULL
                    END,
                    event_at = COALESCE(event_at, created_at)
                WHERE point_type IS NULL
                   OR event_at IS NULL
                   OR quality_status IS NULL
                """
            )
        )
        conn.execute(
            text(f"ALTER TABLE {tb_name_paper_account_snapshots} ALTER COLUMN point_type SET DEFAULT 'trading'")
        )
        conn.execute(
            text(f"ALTER TABLE {tb_name_paper_account_snapshots} ALTER COLUMN quality_status SET DEFAULT 'valid'")
        )
        conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ALTER COLUMN event_at SET DEFAULT now()"))
        conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ALTER COLUMN point_type SET NOT NULL"))
        conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ALTER COLUMN event_at SET NOT NULL"))
        conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} ALTER COLUMN quality_status SET NOT NULL"))
        self._drop_legacy_snapshot_account_date_uniqueness(conn)
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_paper_account_snapshots_account_event "
                f"ON {tb_name_paper_account_snapshots} (account_id, event_at, id)"
            )
        )
        conn.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_account_snapshots_account_initial "
                f"ON {tb_name_paper_account_snapshots} (account_id) WHERE point_type = 'initial'"
            )
        )

    def _classify_legacy_paper_account_chronology(self, conn) -> None:
        from paper_trading.domain.enums import MigrationRepairReason

        if not inspect(conn).has_table(tb_name_paper_accounts):
            return
        account_columns = self._table_column_names(conn, tb_name_paper_accounts)
        if _PAPER_ACCOUNT_REPAIR_REASON_COLUMN not in account_columns:
            return
        if "created_at" not in account_columns:
            predicates = ["TRUE"]
        else:
            predicates = [
                "account.created_at IS NULL",
                "account.initial_cash IS NULL",
                "account.initial_cash::text IN ('NaN', 'Infinity', '-Infinity')",
                "account.initial_cash <= 0",
                *self._legacy_chronology_predicates(conn),
            ]
        conn.execute(
            text(
                f"""
                UPDATE {tb_name_paper_accounts} AS account
                SET {_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} = '{MigrationRepairReason.LEGACY_ORDERING_UNCERTAIN.value}'
                WHERE account.{_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} IS NULL
                  AND ({" OR ".join(predicates)})
                """
            )
        )

    def _legacy_chronology_predicates(self, conn) -> list[str]:
        predicates: list[str] = []
        snapshot_columns = self._table_column_names(conn, tb_name_paper_account_snapshots)
        initial_required = {
            "trade_date",
            "event_at",
            "point_type",
            "cash_available",
            "total_assets",
            "net_asset_value",
            "share_count",
        }
        if initial_required <= snapshot_columns:
            provenance = (
                "source.event_time_provenance IS NOT DISTINCT FROM 'canonical_utc'"
                if "event_time_provenance" in snapshot_columns
                else "FALSE"
            )
            predicates.append(
                f"""EXISTS (
                SELECT 1 FROM {tb_name_paper_account_snapshots} AS source
                WHERE source.account_id = account.id
                  AND source.point_type = 'initial'
                  AND NOT (
                      {provenance}
                      AND source.trade_date = CAST(account.created_at AS date)
                      AND source.event_at = account.created_at
                      AND source.cash_available = account.initial_cash
                      AND source.total_assets = account.initial_cash
                      AND source.net_asset_value = 1
                      AND source.share_count = account.initial_cash
                  )
            )"""
            )
        if not inspect(conn).has_table(tb_name_paper_cash_ledger):
            predicates.append(
                f"""EXISTS (
                SELECT 1
                FROM {tb_name_paper_account_snapshots} AS snapshot
                WHERE snapshot.account_id = account.id
                  AND snapshot.point_type IS DISTINCT FROM 'initial'
            )"""
            )
        for table_name, timestamp_columns, date_columns in _LEGACY_CHRONOLOGY_SOURCES:
            if not inspect(conn).has_table(table_name):
                continue
            columns = self._table_column_names(conn, table_name)
            expected_columns = (*timestamp_columns, *date_columns)
            account_match = self._legacy_chronology_account_match(table_name, columns)
            if any(column_name not in columns for column_name in expected_columns):
                predicates.append(
                    f"""EXISTS (
                    SELECT 1
                    FROM {table_name} AS source
                    WHERE {account_match}
                )"""
                )
                continue
            row_uncertain = self._legacy_chronology_row_uncertain(timestamp_columns, date_columns)
            if table_name in _SQLITE_PAPER_REPLAY_PROVENANCE_TABLES:
                if "event_time_provenance" not in columns:
                    row_uncertain = f"({row_uncertain}) OR TRUE"
                else:
                    row_uncertain = (
                        f"({row_uncertain}) OR (source.event_time_provenance IS DISTINCT FROM 'canonical_utc')"
                    )
            if table_name == tb_name_paper_cash_ledger:
                row_uncertain = f"({row_uncertain}) OR ({self._legacy_cash_ledger_invalid(columns)})"
            if table_name == tb_name_paper_account_snapshots:
                row_uncertain = f"({row_uncertain}) OR source.quality_status IS DISTINCT FROM 'valid'"
            predicates.append(
                f"""EXISTS (
                    SELECT 1
                    FROM {table_name} AS source
                    WHERE {account_match}
                      AND ({row_uncertain})
                )"""
            )
        return predicates

    @staticmethod
    def _legacy_cash_ledger_invalid(columns: set[str]) -> str:
        numeric_columns = ("amount", "net_asset_value", "share_delta", "rounding_residual")
        if not all(column in columns for column in numeric_columns):
            return "TRUE"
        return " OR ".join(
            (
                "source.amount IS NULL OR source.amount::text IN ('NaN', 'Infinity', '-Infinity')",
                "source.net_asset_value IS NULL OR source.net_asset_value::text IN ('NaN', 'Infinity', '-Infinity')",
                "source.share_delta IS NULL OR source.share_delta::text IN ('NaN', 'Infinity', '-Infinity')",
                "source.rounding_residual IS NULL OR source.rounding_residual::text "
                "IN ('NaN', 'Infinity', '-Infinity')",
                "source.net_asset_value <= 0",
                "(source.event_type = 'deposit' AND (source.amount <= 0 OR source.share_delta <= 0))",
                "(source.event_type = 'withdrawal' AND (source.amount >= 0 OR source.share_delta >= 0))",
                "source.amount <> source.share_delta * source.net_asset_value + source.rounding_residual",
            )
        )

    def _legacy_chronology_row_uncertain(
        self, timestamp_columns: tuple[str, ...], date_columns: tuple[str, ...]
    ) -> str:
        date_unproven = " OR ".join(
            f"(source.{column_name} IS NULL OR source.{column_name} < CAST(account.created_at AS date))"
            for column_name in date_columns
        )
        if not timestamp_columns:
            return date_unproven
        timestamp_early = " OR ".join(
            f"source.{column_name} IS NULL OR source.{column_name} < account.created_at"
            for column_name in timestamp_columns
        )
        if not date_columns:
            return f"({timestamp_early})"
        timestamp_date_conflict = " OR ".join(
            f"CAST(source.{date_column} AS date) <> CAST(source.{timestamp_column} AS date)"
            for timestamp_column in timestamp_columns
            for date_column in date_columns
        )
        return f"({timestamp_early}) OR ({date_unproven}) OR ({timestamp_date_conflict})"

    def _legacy_chronology_account_match(self, table_name: str, columns: set[str]) -> str:
        if table_name == tb_name_paper_matching_runs:
            if "account_id" not in columns:
                return "TRUE"
            if "scope_key" in columns:
                return "(source.account_id = account.id OR (source.account_id IS NULL AND source.scope_key = 'all'))"
            return "(source.account_id = account.id OR source.account_id IS NULL)"
        account_match = "source.account_id = account.id"
        if table_name == tb_name_paper_account_snapshots and "point_type" in columns:
            return f"{account_match} AND source.point_type IS DISTINCT FROM 'initial'"
        return account_match

    def _insert_paper_account_initial_baselines(self, conn) -> None:
        if not inspect(conn).has_table(tb_name_paper_accounts):
            return
        assign_ids = (
            conn.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": tb_name_paper_account_snapshots},
            ).scalar_one_or_none()
            is None
        )
        id_column = "id, " if assign_ids else ""
        id_value = (
            f"COALESCE((SELECT MAX(existing.id) FROM {tb_name_paper_account_snapshots} AS existing), 0) "
            "+ ROW_NUMBER() OVER (ORDER BY account.id), "
            if assign_ids
            else ""
        )
        conn.execute(
            text(
                f"""
                INSERT INTO {tb_name_paper_account_snapshots} (
                    {id_column}account_id, trade_date, point_type, event_at, event_time_provenance, quality_status,
                    invalid_reason,
                    cash_available, cash_frozen, market_value, total_assets, realized_pnl,
                    unrealized_pnl, position_count, order_count, trade_count, pending_settlement,
                    net_asset_value, share_count, cumulative_deposit, cumulative_withdrawal, net_cash_flow
                )
                SELECT
                    {id_value}account.id,
                    CAST(account.created_at AS date),
                    'initial',
                    account.created_at,
                    'canonical_utc',
                    'valid',
                    NULL,
                    account.initial_cash,
                    0,
                    0,
                    account.initial_cash,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    1,
                    account.initial_cash,
                    account.initial_cash,
                    0,
                    account.initial_cash
                FROM {tb_name_paper_accounts} AS account
                WHERE account.initial_cash > 0
                  AND account.created_at IS NOT NULL
                  AND account.{_PAPER_ACCOUNT_REPAIR_REASON_COLUMN} IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {tb_name_paper_account_snapshots} AS snapshot
                      WHERE snapshot.account_id = account.id
                        AND snapshot.point_type = 'initial'
                  )
                """
            )
        )

    def _drop_legacy_snapshot_account_date_uniqueness(self, conn) -> None:
        for constraint_name in conn.execute(
            text(
                """
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                WHERE nsp.nspname = current_schema()
                  AND rel.relname = :table_name
                  AND con.contype = 'u'
                  AND pg_get_constraintdef(con.oid) LIKE '%UNIQUE (account_id, trade_date)%'
                """
            ),
            {"table_name": tb_name_paper_account_snapshots},
        ).scalars():
            conn.execute(text(f"ALTER TABLE {tb_name_paper_account_snapshots} DROP CONSTRAINT {constraint_name}"))
        for index_name in conn.execute(
            text(
                """
                SELECT ic.relname
                FROM pg_index i
                JOIN pg_class ic ON ic.oid = i.indexrelid
                JOIN pg_class tc ON tc.oid = i.indrelid
                JOIN pg_namespace nsp ON nsp.oid = tc.relnamespace
                WHERE nsp.nspname = current_schema()
                  AND tc.relname = :table_name
                  AND i.indisunique
                  AND NOT i.indisprimary
                  AND i.indpred IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_constraint con WHERE con.conindid = i.indexrelid
                  )
                  AND (
                      SELECT array_agg(a.attname ORDER BY key.ordinality)
                      FROM unnest(i.indkey) WITH ORDINALITY AS key(attnum, ordinality)
                      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = key.attnum
                  ) = ARRAY['account_id', 'trade_date']::name[]
                """
            ),
            {"table_name": tb_name_paper_account_snapshots},
        ).scalars():
            conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))


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
    pid = os.getpid()

    if pid not in _storage_instances:
        if config is None:
            config = StorageConfig()
        _storage_instances[pid] = StorageDb(config)
        logger.debug(f"Created new StorageDb instance for PID {pid}")

    return _storage_instances[pid]
