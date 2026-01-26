import os
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar, cast

import pandas as pd
import retrying
import tushare as ts

from common.const import (
    COL_CIRC_MV,
    COL_CLOSE,
    COL_DATE,
    COL_DOWN_LIMIT,
    COL_DV_RATIO,
    COL_DV_TTM,
    COL_FLOAT_SHARE,
    COL_FREE_SHARE,
    COL_LIMIT_STATUS,
    COL_PB,
    COL_PB_MRQ,
    COL_PE,
    COL_PE_TTM,
    COL_PRE_CLOSE,
    COL_PS,
    COL_PS_TTM,
    COL_SUSPEND_TIMING,
    COL_SUSPEND_TYPE,
    COL_TOTAL_MV,
    COL_TOTAL_SHARE,
    COL_TS_CODE,
    COL_TURNOVER_RATE,
    COL_TURNOVER_RATE_F,
    COL_UP_LIMIT,
    COL_VOLUME_RATIO,
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

        ts.set_token(token)

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
    "limit_status",
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


@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
)
@get_pro
def download_daily_basic_a_stock_ts(
    trade_date: str,
) -> pd.DataFrame | Any:
    trade_date = convert_date(trade_date)

    df = ts.pro_api().daily_basic(
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
) -> pd.DataFrame | Any:
    if trade_date:
        trade_date = convert_date(trade_date)
    if start_date:
        start_date = convert_date(start_date)
    if end_date:
        end_date = convert_date(end_date)

    df = ts.pro_api().stk_limit(
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
) -> pd.DataFrame | Any:
    if trade_date:
        trade_date = convert_date(trade_date)
    if start_date:
        start_date = convert_date(start_date)
    if end_date:
        end_date = convert_date(end_date)

    df = ts.pro_api().suspend_d(
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
