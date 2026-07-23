import fcntl
import os
import re
import tempfile
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar, cast

import pandas as pd
import retrying
import tushare as ts

from common.const import (
    COL_AMOUNT,
    COL_CHANGE,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_TURNOVER_RATE,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)

F = TypeVar("F", bound=Callable[..., Any])
_HK_DAILY_ADJ_CACHE_BY_TRADE_DATE: dict[str, pd.DataFrame] = {}
_HK_DAILY_ADJ_RATE_LIMIT_LOCK_PATH = os.path.join(tempfile.gettempdir(), "frog_hk_daily_adj.lock")
_HK_DAILY_ADJ_RATE_LIMIT_STATE_PATH = os.path.join(tempfile.gettempdir(), "frog_hk_daily_adj.last_call")


def _create_pro_client() -> Any:
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise ConnectionError("Tushare token is missing. Please set env var TUSHARE_TOKEN.")
    return ts.pro_api(token=token)


def get_pro(func: F) -> F:
    """Decorator to create a TuShare pro client and inject it into function.

    Token source: env var `TUSHARE_TOKEN`.

    The decorated function must accept a keyword argument `pro`.

    Raises:
        ConnectionError: if token is missing.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        kwargs["pro"] = _create_pro_client()

        return func(*args, **kwargs)

    return cast(F, wrapper)


def convert_date(date_str: str) -> str:
    date_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y%m%d")
        except ValueError:
            continue

    raise ValueError(f"Invalid date format: {date_str}.")


def require_pro_client(pro: Any | None) -> Any:
    if pro is None:
        raise ConnectionError("Tushare pro client is missing.")
    return pro


def retry_on_non_validation_errors(exception: Exception) -> bool:
    return not isinstance(exception, ValueError)


daily_basic_fields = [
    "ts_code",
    "trade_date",
    "close",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
]


stk_limit_fields = [
    "trade_date",
    "ts_code",
    "pre_close",
    "up_limit",
    "down_limit",
]


suspend_d_fields = [
    "ts_code",
    "trade_date",
    "suspend_timing",
    "suspend_type",
]


stock_basic_fields = [
    "ts_code",
    "symbol",
    "name",
    "area",
    "industry",
    "fullname",
    "enname",
    "cnspell",
    "market",
    "exchange",
    "curr_type",
    "list_status",
    "list_date",
    "delist_date",
    "is_hs",
    "act_name",
    "act_ent_type",
]


fund_daily_fields = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]


hk_daily_adj_fields = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "change",
    "pct_change",
    "vol",
    "amount",
    "turnover_ratio",
]


hk_daily_fields = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]


hk_history_columns = [
    COL_DATE,
    COL_STOCK_ID,
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
    COL_AMOUNT,
    COL_CHANGE,
    COL_CHANGE_RATE,
    COL_TURNOVER_RATE,
]


hk_history_numeric_columns = [
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
    COL_AMOUNT,
    COL_CHANGE,
    COL_CHANGE_RATE,
    COL_TURNOVER_RATE,
]

hk_history_required_numeric = [
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
    COL_AMOUNT,
]

hk_history_optional_numeric = [
    COL_CHANGE,
    COL_CHANGE_RATE,
    COL_TURNOVER_RATE,
]


def _empty_hk_history_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_DATE: pd.Series(dtype="datetime64[ns]"),
            COL_STOCK_ID: pd.Series(dtype="object"),
            COL_OPEN: pd.Series(dtype="float64"),
            COL_CLOSE: pd.Series(dtype="float64"),
            COL_HIGH: pd.Series(dtype="float64"),
            COL_LOW: pd.Series(dtype="float64"),
            COL_VOLUME: pd.Series(dtype="float64"),
            COL_AMOUNT: pd.Series(dtype="float64"),
            COL_CHANGE: pd.Series(dtype="float64"),
            COL_CHANGE_RATE: pd.Series(dtype="float64"),
            COL_TURNOVER_RATE: pd.Series(dtype="float64"),
        },
        columns=hk_history_columns,
    )


def _get_hk_daily_adj_min_interval_seconds() -> float:
    value = os.getenv("TUSHARE_HK_DAILY_ADJ_MIN_INTERVAL_SECONDS", "31")
    try:
        return max(0.0, float(value))
    except ValueError:
        return 31.0


def _normalize_hk_history_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_hk_history_dataframe()

    normalized = df.rename(
        columns={
            "trade_date": COL_DATE,
            "open": COL_OPEN,
            "close": COL_CLOSE,
            "high": COL_HIGH,
            "low": COL_LOW,
            "vol": COL_VOLUME,
            "amount": COL_AMOUNT,
            "change": COL_CHANGE,
            "pct_chg": COL_CHANGE_RATE,
            "pct_change": COL_CHANGE_RATE,
            "turnover_ratio": COL_TURNOVER_RATE,
        }
    ).copy()
    normalized[COL_DATE] = pd.to_datetime(normalized[COL_DATE], format="%Y%m%d")
    if "ts_code" in normalized.columns:
        normalized[COL_STOCK_ID] = normalized["ts_code"].astype(str).str.replace(".HK", "", regex=False)
    normalized = normalized.reindex(columns=hk_history_columns)

    # Required core OHLCV/amount fields: raise on non-convertible values
    for column in hk_history_required_numeric:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise").astype("float64")

    # Optional fields: coerce non-convertible to NaN, then fill with 0
    for column in hk_history_optional_numeric:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0.0).astype("float64")

    return normalized


def _call_hk_daily_adj_throttled(client: Any, **kwargs: Any) -> pd.DataFrame | Any:
    """Call client.hk_daily_adj with cross-process rate-limit enforcement."""
    min_interval = _get_hk_daily_adj_min_interval_seconds()
    with open(_HK_DAILY_ADJ_RATE_LIMIT_LOCK_PATH, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            last_called_at = 0.0
            if os.path.exists(_HK_DAILY_ADJ_RATE_LIMIT_STATE_PATH):
                with open(_HK_DAILY_ADJ_RATE_LIMIT_STATE_PATH, encoding="utf-8") as state_file:
                    raw_value = state_file.read().strip()
                    if raw_value:
                        last_called_at = float(raw_value)
            remaining = min_interval - (time.time() - last_called_at)
            if remaining > 0:
                time.sleep(remaining)
            # Record the call time BEFORE the API call so that even a failed call
            # (e.g. rate-limit exception) counts toward the interval. This prevents
            # @retrying.retry from immediately re-entering the throttle on retry.
            with open(_HK_DAILY_ADJ_RATE_LIMIT_STATE_PATH, "w", encoding="utf-8") as state_file:
                state_file.write(str(time.time()))
            return client.hk_daily_adj(**kwargs)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _call_hk_daily_adj_for_trade_date(client: Any, trade_date: str) -> pd.DataFrame | Any:
    return _call_hk_daily_adj_throttled(
        client,
        ts_code="",
        trade_date=trade_date,
        start_date="",
        end_date=trade_date,
        fields=hk_daily_adj_fields,
    )


def _load_hk_history_by_trade_date(trade_date: str, stock_id: str, pro: Any | None = None) -> pd.DataFrame:
    cached = _HK_DAILY_ADJ_CACHE_BY_TRADE_DATE.get(trade_date)
    if cached is None:
        client = require_pro_client(pro) if pro is not None else _create_pro_client()
        cached = _normalize_hk_history_dataframe(_call_hk_daily_adj_for_trade_date(client, trade_date))
        _HK_DAILY_ADJ_CACHE_BY_TRADE_DATE[trade_date] = cached

    filtered = cached.loc[cached[COL_STOCK_ID] == stock_id].copy()
    if filtered.empty:
        return _empty_hk_history_dataframe()
    return filtered


etf_basic_fields = [
    "ts_code",
    "csname",
    "extname",
    "cname",
    "index_code",
    "index_name",
    "setup_date",
    "list_date",
    "list_status",
    "exchange",
    "mgr_name",
    "custod_name",
    "mgt_fee",
    "etf_type",
]


def _to_hk_ts_code(stock_id: str) -> str:
    if not re.fullmatch(r"\d{5}", stock_id):
        raise ValueError("Stock ID must be 5 digits.")
    return f"{stock_id}.HK"


def _to_a_stock_ts_code(stock_id: str) -> str:
    if not re.fullmatch(r"\d{6}", stock_id):
        raise ValueError("Stock ID must be 6 digits.")
    suffix = "SH" if stock_id.startswith("6") else "SZ"
    return f"{stock_id}.{suffix}"


def _pro_bar_freq(period: PeriodType) -> str:
    freq_map = {
        PeriodType.DAILY: "D",
        PeriodType.WEEKLY: "W",
        PeriodType.MONTHLY: "M",
    }
    return freq_map[period]


_a_stock_history_columns = [
    COL_DATE,
    COL_STOCK_ID,
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
    COL_AMOUNT,
    COL_CHANGE_RATE,
]

_a_stock_history_required_numeric = [
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
    COL_AMOUNT,
]

_a_stock_history_optional_numeric = [
    COL_CHANGE_RATE,
]


def _normalize_a_stock_history_ts(df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    column_mapping = {
        "trade_date": COL_DATE,
        "ts_code": COL_STOCK_ID,
        "open": COL_OPEN,
        "high": COL_HIGH,
        "low": COL_LOW,
        "close": COL_CLOSE,
        "vol": COL_VOLUME,
        "amount": COL_AMOUNT,
        "pct_chg": COL_CHANGE_RATE,
        "change": COL_CHANGE,
    }
    normalized = df.rename(columns=column_mapping).copy()

    # Validate all required columns exist after rename
    _a_stock_history_required = [COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME, COL_AMOUNT]
    for column in _a_stock_history_required:
        if column not in normalized.columns:
            raise ValueError(f"Missing required column '{column}' in TuShare pro_bar response")

    normalized[COL_DATE] = pd.to_datetime(normalized[COL_DATE], format="%Y%m%d")
    normalized[COL_STOCK_ID] = stock_id

    # Required OHLCV/amount fields: raise on non-convertible values
    for column in _a_stock_history_required_numeric:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise")

    # Optional fields: coerce non-convertible to NaN, then fill with 0
    for column in _a_stock_history_optional_numeric:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0)

    # Drop any columns not in the canonical set
    normalized = normalized.reindex(columns=_a_stock_history_columns)
    return normalized.sort_values(COL_DATE).reset_index(drop=True)


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_daily_basic_a_stock_ts(
    trade_date: str,
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    trade_date = convert_date(trade_date)
    client = require_pro_client(pro)

    df = client.daily_basic(
        **{
            "ts_code": "",
            "trade_date": trade_date,
            "start_date": "",
            "end_date": "",
            "limit": "",
            "offset": "",
        },
        fields=daily_basic_fields,
    )

    return df


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
    retry_on_exception=retry_on_non_validation_errors,
)
def download_history_data_stock_ts(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
) -> pd.DataFrame:
    client = _create_pro_client()
    df = ts.pro_bar(
        api=client,
        ts_code=_to_a_stock_ts_code(stock_id),
        start_date=convert_date(start_date),
        end_date=convert_date(end_date),
        freq=_pro_bar_freq(period),
        adj=adjust.value or None,
    )
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected DataFrame, got {type(df)}")
    if df.empty:
        return df
    return _normalize_a_stock_history_ts(df, stock_id)


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_stk_limit(
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    if trade_date:
        trade_date = convert_date(trade_date)
    if start_date:
        start_date = convert_date(start_date)
    if end_date:
        end_date = convert_date(end_date)
    client = require_pro_client(pro)

    df = client.stk_limit(
        **{
            "ts_code": ts_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
        },
        fields=stk_limit_fields,
    )

    return df


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_suspend_d(
    ts_code: str = "",
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    suspend_type: str = "",
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    if trade_date:
        trade_date = convert_date(trade_date)
    if start_date:
        start_date = convert_date(start_date)
    if end_date:
        end_date = convert_date(end_date)
    client = require_pro_client(pro)

    df = client.suspend_d(
        **{
            "ts_code": ts_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
            "suspend_type": suspend_type,
        },
        fields=suspend_d_fields,
    )

    return df


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_a_stock_basic(
    ts_code: str = "",
    name: str = "",
    market: str = "",
    list_status: str = "L",
    exchange: str = "",
    is_hs: str = "",
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    client = require_pro_client(pro)

    df = client.stock_basic(
        **{
            "ts_code": ts_code,
            "name": name,
            "market": market,
            "list_status": list_status,
            "exchange": exchange,
            "is_hs": is_hs,
        },
        fields=stock_basic_fields,
    )

    return df


def _get_etf_suffix(etf_id: str) -> str:
    """Get the exchange suffix for an ETF code.

    Shanghai ETFs: 510xxx, 511xxx, 512xxx, 513xxx, 515xxx, 516xxx, 517xxx,
                   518xxx, 519xxx, 530xxx, 531xxx, 532xxx, 533xxx
    Shenzhen ETFs: 159xxx, 160xxx, 161xxx, 162xxx, 163xxx, 164xxx
    """
    if etf_id.startswith(("159", "160", "161", "162", "163", "164")):
        return ".SZ"
    # Default to Shanghai for 510xxx, 511xxx, etc.
    return ".SH"


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_history_data_etf_ts(
    etf_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    # fund_daily is daily-only; keep signature compatibility with history downloader.
    del period, adjust

    normalized_start_date = convert_date(start_date) if start_date else ""
    normalized_end_date = convert_date(end_date) if end_date else ""
    ts_code = etf_id + _get_etf_suffix(etf_id)

    client = require_pro_client(pro)
    df = client.fund_daily(
        **{
            "ts_code": ts_code,
            "trade_date": "",
            "start_date": normalized_start_date,
            "end_date": normalized_end_date,
        },
        fields=fund_daily_fields,
    )
    if df.empty:
        return pd.DataFrame(
            columns=[
                COL_DATE,
                COL_STOCK_ID,
                COL_OPEN,
                COL_CLOSE,
                COL_HIGH,
                COL_LOW,
                COL_VOLUME,
            ]
        )

    normalized = (
        df.rename(
            columns={
                "trade_date": COL_DATE,
                "ts_code": COL_STOCK_ID,
                "open": COL_OPEN,
                "close": COL_CLOSE,
                "high": COL_HIGH,
                "low": COL_LOW,
                "vol": COL_VOLUME,
            }
        )
        .copy()
        .loc[
            :,
            [
                COL_DATE,
                COL_STOCK_ID,
                COL_OPEN,
                COL_CLOSE,
                COL_HIGH,
                COL_LOW,
                COL_VOLUME,
            ],
        ]
    )
    normalized[COL_STOCK_ID] = normalized[COL_STOCK_ID].astype(str).str.split(".").str[0]
    normalized[COL_DATE] = pd.to_datetime(normalized[COL_DATE], format="%Y%m%d", errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    return normalized.dropna(subset=[COL_DATE])


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_etf_daily(
    etf_id: str = "",  # without suffix
    trade_date: str = "",
    start_date: str = "",
    end_date: str = "",
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    if trade_date:
        trade_date = convert_date(trade_date)
    if start_date:
        start_date = convert_date(start_date)
    if end_date:
        end_date = convert_date(end_date)

    # Add suffix based on ETF code
    ts_code = etf_id + _get_etf_suffix(etf_id)

    client = require_pro_client(pro)

    df = client.fund_daily(
        **{
            "ts_code": ts_code,
            "trade_date": trade_date,
            "start_date": start_date,
            "end_date": end_date,
        },
        fields=fund_daily_fields,
    )

    return df


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_etf_basic(
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    client = require_pro_client(pro)

    df = client.etf_basic(
        list_status="L",
        fields=etf_basic_fields,
    )

    return df


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
    retry_on_exception=retry_on_non_validation_errors,
)
def download_history_data_stock_hk_ts(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.BFQ,
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    if period != PeriodType.DAILY:
        raise ValueError("Only daily period is supported for HK Tushare history downloads.")
    if adjust != AdjustType.BFQ:
        raise ValueError("Only BFQ adjust is supported for HK Tushare history downloads.")
    ts_code = _to_hk_ts_code(stock_id)
    normalized_start_date = convert_date(start_date) if start_date else ""
    normalized_end_date = convert_date(end_date) if end_date else ""

    client = require_pro_client(pro) if pro is not None else _create_pro_client()

    df = client.hk_daily(
        ts_code=ts_code,
        trade_date="",
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        fields=hk_daily_fields,
    )

    if df.empty:
        return _empty_hk_history_dataframe()

    normalized = _normalize_hk_history_dataframe(df)
    normalized[COL_STOCK_ID] = stock_id
    return normalized


stk_holdernumber_fields = [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_num",
]


top10_floatholders_fields = [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio",
    "hold_float_ratio",
    "hold_change",
    "holder_type",
]


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_stk_holdernumber(
    ts_code: str = "",
    start_date: str = "",
    end_date: str = "",
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    if start_date:
        start_date = convert_date(start_date)
    if end_date:
        end_date = convert_date(end_date)
    client = require_pro_client(pro)

    df = client.stk_holdernumber(
        **{
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
        },
        fields=stk_holdernumber_fields,
    )

    return df


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_top10_floatholders(
    ts_code: str = "",
    start_date: str = "",
    end_date: str = "",
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    if start_date:
        start_date = convert_date(start_date)
    if end_date:
        end_date = convert_date(end_date)
    client = require_pro_client(pro)

    df = client.top10_floatholders(
        **{
            "ts_code": ts_code,
            "start_date": start_date,
            "end_date": end_date,
        },
        fields=top10_floatholders_fields,
    )

    return df
