import os
import re
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


def get_pro(func: F) -> F:
    """Decorator to create a TuShare pro client and inject it into function.

    Token source: env var `TUSHARE_TOKEN`.

    The decorated function must accept a keyword argument `pro`.

    Raises:
        ConnectionError: if token is missing.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            raise ConnectionError(
                "Tushare token is missing. Please set env var TUSHARE_TOKEN."
            )
        kwargs["pro"] = ts.pro_api(token=token)

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
@get_pro
def download_history_data_stock_hk_ts(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.HFQ,
    pro: Any | None = None,
) -> pd.DataFrame | Any:
    client = require_pro_client(pro)
    if period != PeriodType.DAILY:
        raise ValueError(
            "Only daily period is supported for HK Tushare history downloads."
        )
    if adjust != AdjustType.HFQ:
        raise ValueError(
            "Only HFQ adjust is supported for HK Tushare history downloads."
        )
    ts_code = _to_hk_ts_code(stock_id)
    normalized_start_date = convert_date(start_date) if start_date else ""
    normalized_end_date = convert_date(end_date) if end_date else ""

    df = client.hk_daily_adj(
        ts_code=ts_code,
        trade_date="",
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        fields=hk_daily_adj_fields,
    )

    if df.empty:
        return _empty_hk_history_dataframe()

    df = df.rename(
        columns={
            "trade_date": COL_DATE,
            "open": COL_OPEN,
            "close": COL_CLOSE,
            "high": COL_HIGH,
            "low": COL_LOW,
            "vol": COL_VOLUME,
            "amount": COL_AMOUNT,
            "change": COL_CHANGE,
            "pct_change": COL_CHANGE_RATE,
            "turnover_ratio": COL_TURNOVER_RATE,
        }
    )
    df[COL_DATE] = pd.to_datetime(df[COL_DATE], format="%Y%m%d")
    df[COL_STOCK_ID] = stock_id
    df = df.reindex(columns=hk_history_columns)
    df[hk_history_numeric_columns] = (
        df[hk_history_numeric_columns]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .astype("float64")
    )

    return df


stk_holdernumber_fields = [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_num",
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
