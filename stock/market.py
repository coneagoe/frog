# -*- coding: utf-8 -*-
import logging
import os
from datetime import date, datetime
from typing import List

import pandas as pd
import pandas_market_calendars as mcal


def is_testing():
    if os.getenv("TEST") in ["true", "on", "1"] or os.getenv("FROG_SERVER_CONFIG") in [
        "development",
        "testing",
    ]:
        return True

    return False


def is_market_open():
    if is_testing():
        return True

    if date.today().weekday() >= 5:
        return False

    now = datetime.now()
    if (
        (now.hour == 9 and now.minute >= 30)
        or (now.hour == 10)
        or (now.hour == 11 and now.minute <= 30)
        or (now.hour == 13)
        or (now.hour == 14)
        or (now.hour == 15 and now.minute <= 30)
    ):
        return True

    return False


def get_last_trading_day() -> str:
    """
    Get the last trading day.
    If today is a trading day, return today.
    Otherwise, return the most recent trading day.

    Returns:
        str: Date in format 'YYYY-MM-DD'
    """
    cal = mcal.get_calendar("XSHG")

    today = datetime.now().strftime("%Y-%m-%d")
    today_date = datetime.strptime(today, "%Y-%m-%d")

    start_date = (today_date - pd.Timedelta(days=10)).strftime("%Y-%m-%d")

    trading_days = cal.valid_days(start_date=start_date, end_date=today)
    if trading_days.empty:
        logging.error("No trading day found")
        raise RuntimeError("No trading day found")

    trading_days_str: List[str] = [d.strftime("%Y-%m-%d") for d in trading_days]

    if today in trading_days_str:
        return today
    else:
        return trading_days_str[-1]


def is_a_market_open(date_str: str) -> bool:
    """
    Check if the given date is a trading day.

    Args:
        date_str (str): Date in format 'YYYY-MM-DD'

    Returns:
        bool: True if the date is a trading day, False otherwise.
    """
    cal = mcal.get_calendar("XSHG")
    schedule = cal.schedule(start_date=date_str, end_date=date_str)
    return not schedule.empty


def is_a_market_open_today() -> bool:
    """
    Check if today is a trading day.

    Returns:
        bool: True if today is a trading day, False otherwise.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    return is_a_market_open(today_str)


def is_hk_market_open(date_str: str) -> bool:
    """
    Check if the given date is a trading day in Hong Kong market.

    Args:
        date_str (str): Date in format 'YYYY-MM-DD'

    Returns:
        bool: True if the date is a trading day, False otherwise.
    """
    cal = mcal.get_calendar("XHKG")
    schedule = cal.schedule(start_date=date_str, end_date=date_str)
    return not schedule.empty


def is_hk_market_open_today() -> bool:
    """
    Check if today is a trading day in Hong Kong market.

    Returns:
        bool: True if today is a trading day, False otherwise.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    return is_hk_market_open(today_str)
