from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Collection

_YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")


def validate_positive_int(value: Any, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} 必须是正整数")


def validate_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是布尔值")


def validate_stock_code(stock_code: Any) -> None:
    if not isinstance(stock_code, str) or not stock_code.strip():
        raise ValueError("stock_code 不能为空")


def validate_market(market: Any, allowed_markets: Collection[str]) -> None:
    if not isinstance(market, str) or market not in allowed_markets:
        raise ValueError(f"market 必须是 {sorted(allowed_markets)} 之一")


def validate_datetime_or_none(value: Any, field_name: str) -> None:
    if value is not None and not isinstance(value, datetime):
        raise ValueError(f"{field_name} 必须是 datetime 或 None")


def validate_yyyymmdd(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not _YYYYMMDD_PATTERN.match(value):
        raise ValueError(f"{field_name} 必须是 YYYYMMDD 格式")
    datetime.strptime(value, "%Y%m%d")


def validate_date_range(start_date: Any, end_date: Any) -> None:
    validate_yyyymmdd(start_date, "start_date")
    validate_yyyymmdd(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")
