import json
import os
import subprocess
import sys
from datetime import date

import redis

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf  # noqa: E402
from celery_app import app  # noqa: E402
from common import is_hk_market_open_today  # noqa: E402
from common.const import (  # noqa: E402
    DEFAULT_REDIS_URL,
    REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY,
)
from utility import send_email  # noqa: E402


def get_redis_client() -> redis.Redis:
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url, decode_responses=True)


@app.task
def obos_hk():
    conf.parse_config()

    # Check Redis for download result
    try:
        r = get_redis_client()
        result = r.get(REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY)
        if result:
            data = json.loads(result)
            if data.get("result") != "success":
                return f"Skip: download result is {data.get('result')}"
    except Exception as e:
        return f"Skip: failed to read Redis: {e}"

    if not is_hk_market_open_today():
        return "Market is closed today."

    end_date = date.today()
    end_date_str = end_date.strftime("%Y-%m-%d")

    # start_date_str = (end_date - timedelta(days=60)).strftime("%Y-%m-%d")
    start_date_str = "2024-11-01"
    # end_date_str = "2025-07-03"

    try:
        subject = f"obos_hk_{start_date_str}_{end_date_str}"
        command = [
            "python",
            "backtest/obos_hk_9.py",
            "-s",
            start_date_str,
            "-e",
            end_date_str,
            "-f",
            "02362 02981 00168 01211 09997 01558",
        ]
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode == 0:
            send_email(
                subject=subject,
                body=f"{process.stdout}",
            )
            # print(f"Backtest completed successfully. Output: {process.stdout}")
            return "Backtest success."
        else:
            error_message = process.stderr.strip()
            send_email(
                subject=subject,
                body=f"Backtest failed with error: {error_message}",
            )
            # print(f"Backtest failed. Error: {error_message}")
            return f"Backtest failed: {error_message}"
    except Exception as e:
        return f"Exception occurred: {str(e)}"
