import logging
import re
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar, cast

import baostock as bs
import baostock.data.resultset
import pandas as pd

from common.const import (
    COL_AMOUNT,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_IS_ST,
    COL_LOW,
    COL_OPEN,
    COL_PB_MRQ,
    COL_PCF_NCF_TTM,
    COL_PE_TTM,
    COL_PS_TTM,
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_TURNOVER_RATE,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)

F = TypeVar("F", bound=Callable[..., Any])


def login(func: F) -> F:
    """Decorator to handle baostock login and logout automatically.

    This decorator wraps functions that use baostock API calls, handling
    the login before execution and logout after completion (including
    when exceptions occur).

    Args:
        func: The function to wrap

    Returns:
        The wrapped function result

    Raises:
        ConnectionError: If baostock login fails
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Login to baostock
        lg = bs.login()
        if lg.error_code != "0":
            raise ConnectionError(f"Baostock login failed: {lg.error_msg}")

        try:
            # Execute the wrapped function
            result = func(*args, **kwargs)
            return result
        finally:
            # Always logout, even if an exception occurs
            bs.logout()

    return cast(F, wrapper)


def _validate_and_convert_date(date_str: str) -> str:
    """Validate and convert date string to YYYY-MM-DD format.

    Args:
        date_str: Date string in various formats

    Returns:
        Date string in YYYY-MM-DD format

    Raises:
        ValueError: If date format is invalid
    """
    date_formats = [
        "%Y-%m-%d",  # YYYY-MM-DD
        "%Y/%m/%d",  # YYYY/MM/DD
        "%Y.%m.%d",  # YYYY.MM.DD
        "%d-%m-%Y",  # DD-MM-YYYY
        "%d/%m/%Y",  # DD/MM/YYYY
        "%d.%m.%Y",  # DD.MM.YYYY
        "%Y%m%d",  # YYYYMMDD
    ]

    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise ValueError(f"Invalid date format: {date_str}.")


@login
def download_history_data_stock_bs(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
) -> pd.DataFrame:
    assert re.match(r"^\d{6}$", stock_id), "Stock ID must be 6 digits."

    start_date = _validate_and_convert_date(start_date)
    end_date = _validate_and_convert_date(end_date)

    stock_id_org = stock_id

    if stock_id.startswith("6"):
        stock_id = f"sh.{stock_id}"
    else:
        stock_id = f"sz.{stock_id}"

    frequency_map = {"daily": "d", "week": "w", "month": "m"}
    adjust_map = {"": "3", "qfq": "1", "hfq": "2"}
    fields_1d = "date,code,open,high,low,close,volume,amount,turn,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
    fields_1w = "date,code,open,high,low,close,volume,amount,turn,pctChg"

    if period == PeriodType.DAILY:
        fields = fields_1d
    else:
        fields = fields_1w

    rs = bs.query_history_k_data_plus(
        stock_id,
        fields,
        start_date,
        end_date,
        frequency=frequency_map[period.value],
        adjustflag=adjust_map[adjust.value],
    )

    data = []
    while rs.error_code == "0" and rs.next():
        data.append(rs.get_row_data())
    df = pd.DataFrame(data, columns=rs.fields)

    column_mapping = {
        "date": COL_DATE,
        "code": COL_STOCK_ID,
        "open": COL_OPEN,
        "high": COL_HIGH,
        "low": COL_LOW,
        "close": COL_CLOSE,
        "volume": COL_VOLUME,
        "amount": COL_AMOUNT,
        "turn": COL_TURNOVER_RATE,
        "pctChg": COL_CHANGE_RATE,
        "peTTM": COL_PE_TTM,
        "pbMRQ": COL_PB_MRQ,
        "psTTM": COL_PS_TTM,
        "pcfNcfTTM": COL_PCF_NCF_TTM,
        "isST": COL_IS_ST,
    }

    df.rename(columns=column_mapping, inplace=True)

    df[COL_STOCK_ID] = stock_id_org

    # Replace empty values with 0 for numeric columns
    numeric_columns = [
        COL_OPEN,
        COL_HIGH,
        COL_LOW,
        COL_CLOSE,
        COL_VOLUME,
        COL_AMOUNT,
        COL_TURNOVER_RATE,
        COL_CHANGE_RATE,
        COL_PE_TTM,
        COL_PB_MRQ,
        COL_PS_TTM,
        COL_PCF_NCF_TTM,
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


@login
def _download_ingredient(
    query_func: Callable[..., baostock.data.resultset.ResultData]
) -> pd.DataFrame:
    start_date = datetime(2010, 1, 1)
    end_date = datetime.today()

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")

        rs = query_func(date=date_str)
        rows = []
        while rs.next():
            if rs.error_code != "0":
                logging.error(f"query fail({rs.error_code}): {rs.error_msg}")
                exit(1)

            rows.append(rs.get_row_data())

        # while (rs.error_code == '0') & rs.next():
        #     rows.append(rs.get_row_data())

        df = pd.DataFrame(rows, columns=rs.fields)
        df.rename(
            columns={"code": COL_STOCK_ID, "code_name": COL_STOCK_NAME},
            inplace=True,
        )
        df = df[[COL_STOCK_ID, COL_STOCK_NAME]]
        df[COL_STOCK_ID] = (
            df[COL_STOCK_ID].str.replace("sh.", "").str.replace("sz.", "")
        )

        if current_date.month == 1 and current_date.day == 1:
            current_date = datetime(current_date.year, 7, 1)
        else:
            current_date = datetime(current_date.year + 1, 1, 1)

    return df


def download_ingredient_300() -> pd.DataFrame:
    return _download_ingredient(bs.query_hs300_stocks)


def download_ingredient_500() -> pd.DataFrame:
    return _download_ingredient(bs.query_zz500_stocks)
