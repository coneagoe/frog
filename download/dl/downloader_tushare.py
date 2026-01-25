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
    COL_DV_RATIO,
    COL_DV_TTM,
    COL_FLOAT_SHARE,
    COL_FREE_SHARE,
    COL_LIMIT_STATUS,
    COL_PB,
    COL_PB_MRQ,
    COL_PE,
    COL_PE_TTM,
    COL_PS,
    COL_PS_TTM,
    COL_TOTAL_MV,
    COL_TOTAL_SHARE,
    COL_TS_CODE,
    COL_TURNOVER_RATE,
    COL_TURNOVER_RATE_F,
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


_TS_TO_INTERNAL_COL_MAP = {
    "ts_code": COL_TS_CODE,
    "close": COL_CLOSE,
    "turnover_rate": COL_TURNOVER_RATE,
    "turnover_rate_f": COL_TURNOVER_RATE_F,
    "volume_ratio": COL_VOLUME_RATIO,
    "pe": COL_PE,
    "pe_ttm": COL_PE_TTM,
    "pb": COL_PB,
    "pb_mrq": COL_PB_MRQ,
    "ps": COL_PS,
    "ps_ttm": COL_PS_TTM,
    "dv_ratio": COL_DV_RATIO,
    "dv_ttm": COL_DV_TTM,
    "total_share": COL_TOTAL_SHARE,
    "float_share": COL_FLOAT_SHARE,
    "free_share": COL_FREE_SHARE,
    "total_mv": COL_TOTAL_MV,
    "circ_mv": COL_CIRC_MV,
    "trade_date": COL_DATE,
    "limit_status": COL_LIMIT_STATUS,
}


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


@retrying.retry(wait_fixed=1000, stop_max_attempt_number=3)
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

    # Rename columns from tushare names to internal names
    return df.rename(columns=_TS_TO_INTERNAL_COL_MAP)
