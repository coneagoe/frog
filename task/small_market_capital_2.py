import json
import os
import subprocess
import sys
from datetime import date

import pandas_market_calendars as mcal
import redis

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from celery_app import app  # noqa: E402
from common.const import (  # noqa: E402
    DEFAULT_REDIS_URL,
    REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY,
)
from utility import send_email  # noqa: E402


def get_redis_client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url, decode_responses=True)


def is_first_trading_day_of_month(today: date) -> bool:
    """判断 today 是否为当月第一个交易日（A股日历）。"""
    cal = mcal.get_calendar("XSHG")
    month_start = today.replace(day=1).isoformat()
    today_str = today.isoformat()
    trading_days = cal.valid_days(start_date=month_start, end_date=today_str)
    if trading_days.empty:
        return False
    return bool(trading_days[0].strftime("%Y-%m-%d") == today_str)


@app.task
def small_market_capital_2():
    conf.parse_config()

    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    # 检查下载结果
    try:
        r = get_redis_client()
        result = r.get(REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY)
        if not result:
            return "Skip: missing Redis download result."

        data = json.loads(result)
        if data.get("date") != today_str:
            return f"Skip: Redis download result date is {data.get('date')}, expected {today_str}"

        if data.get("result") != "success":
            return f"Skip: download result is {data.get('result')}"
    except Exception as e:
        return f"Skip: failed to read Redis: {e}"

    # 检查是否为当月第一个交易日
    if not is_first_trading_day_of_month(today):
        return f"Skip: {today_str} is not the first trading day of the month."

    start_date_str = "2025-10-01"

    try:
        subject = f"small_market_capital_2_{start_date_str}_{today_str}"
        command = [
            "python",
            "backtest/small_market_capital_2.py",
            "-s",
            start_date_str,
            "-e",
            today_str,
        ]
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode == 0:
            send_email(
                subject=subject,
                body=process.stdout,
            )
            return "Backtest success."
        else:
            send_email(
                subject=subject,
                body=f"Backtest failed.\n{process.stderr}",
            )
            return f"Backtest fail. {process.stderr}"
    except Exception as e:
        return f"Exception occurred: {str(e)}"
