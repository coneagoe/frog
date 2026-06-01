from datetime import datetime, timezone

import pytest

from monitor.validation import (
    validate_bool,
    validate_date_range,
    validate_datetime_or_none,
    validate_market,
    validate_positive_int,
    validate_stock_code,
    validate_yyyymmdd,
)


def test_validate_positive_int_rejects_bool_zero_and_negative():
    for value in (True, 0, -1, "1"):
        with pytest.raises(ValueError, match="days 必须是正整数"):
            validate_positive_int(value, "days")


def test_validate_bool_rejects_non_bool():
    with pytest.raises(ValueError, match="enabled 必须是布尔值"):
        validate_bool(1, "enabled")


def test_validate_stock_code_rejects_blank():
    with pytest.raises(ValueError, match="stock_code 不能为空"):
        validate_stock_code("  ")


def test_validate_market_uses_allowed_values():
    validate_market("A", {"A", "HK", "ETF"})
    with pytest.raises(ValueError, match="market 必须是"):
        validate_market("US", {"A", "HK", "ETF"})


def test_validate_datetime_or_none():
    validate_datetime_or_none(None, "start_at")
    validate_datetime_or_none(datetime(2026, 1, 1, tzinfo=timezone.utc), "start_at")
    with pytest.raises(ValueError, match="start_at 必须是 datetime 或 None"):
        validate_datetime_or_none("20260101", "start_at")


def test_validate_yyyymmdd_rejects_bad_dates():
    validate_yyyymmdd("20260131", "start_date")
    with pytest.raises(ValueError, match="start_date 必须是 YYYYMMDD 格式"):
        validate_yyyymmdd("2026-01-31", "start_date")
    with pytest.raises(ValueError):
        validate_yyyymmdd("20260231", "start_date")


def test_validate_date_range_rejects_reversed_range():
    validate_date_range("20260101", "20260131")
    with pytest.raises(ValueError, match="start_date 不能晚于 end_date"):
        validate_date_range("20260201", "20260131")
