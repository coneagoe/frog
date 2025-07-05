from datetime import (date, timedelta)
import os
import sys
import subprocess
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celery_app import app, redis_client
from stock import is_hk_market_open_today
from utility import send_email


@app.task
def obos_hk():
    import conf
    conf.parse_config()

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
            "python", "backtest/obos_hk_2.py",
            "-s", start_date_str, "-e", end_date_str,
            "-f", "02362 02981",
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
