from datetime import (date, timedelta)
import os
import sys
import subprocess
# import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celery_app import app, redis_client
from stock import (
    is_trading_day,
)
from utility import send_email


@app.task
def obos_hk():
    import conf
    conf.parse_config()

    # end_date = date.today()
    # end_date_str = end_date.strftime("%Y-%m-%d")

    # if not is_trading_day(end_date_str):
    #     return

    # start_date_str = (end_date - timedelta(days=60)).strftime("%Y-%m-%d")
    start_date_str = "2024-11-01"
    end_date_str = "2025-07-03"

    try:
        subject = f"obos_hk_{start_date_str}_{end_date_str}"
        command = [
            "python", "backtest/obos_hk_2.py",
            "-s", start_date_str, "-e", end_date_str,
            "-f", "02362 02981",
            # "-c", os.environ.get('INIT_CASH', '300000'),
        ]
        process = subprocess.run(command, capture_output=True, text=True)
        # if process.returncode == 0:
            # send report
        send_email(
            subject=subject,
            body=f"{process.stdout}",
        )
            # print(f"Backtest completed successfully. Output: {process.stdout}")
            # redis_client.set(result_key, process.stdout)
        return "Backtest success."
        # else:
        #     send_email(
        #         subject=subject,
        #         body=f"Backtest failed.\n{process.stderr}",
        #     )
        #     # print(f"Backtest failed. Error: {process.stderr}")
        #     # redis_client.set(result_key, f"Error: {process.stderr}")
        #     return f"Backtest fail. {process.stderr}"
    except Exception as e:
        return f"Exception occurred: {str(e)}"
