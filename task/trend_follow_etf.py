import os
import subprocess
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from celery_app import app  # noqa: E402
from stock import is_a_market_open_today  # noqa: E402
from utility import send_email  # noqa: E402


@app.task
def trend_follow_etf():
    import conf

    conf.parse_config()

    if not is_a_market_open_today():
        return "Market is closed today."

    end_date = date.today()
    end_date_str = end_date.strftime("%Y-%m-%d")

    # start_date_str = (end_date - timedelta(days=60)).strftime("%Y-%m-%d")
    start_date_str = "2024-11-01"
    # end_date_str = "2025-07-02"

    stock_list_path = "trend_follow_etf_pool.csv"

    try:
        subject = f"trend_follow_etf_{start_date_str}_{end_date_str}"
        command = [
            "python",
            "backtest/trend_follow_etf_8.py",
            "-s",
            start_date_str,
            "-e",
            end_date_str,
            "-l",
            stock_list_path,
        ]
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode == 0:
            send_email(
                subject=subject,
                body=f"{process.stdout}",
            )
            # print(f"Backtest completed successfully. Output: {process.stdout}")
            # redis_client.set(result_key, process.stdout)
            return "Backtest success."
        else:
            send_email(
                subject=subject,
                body=f"Backtest failed.\n{process.stderr}",
            )
            # print(f"Backtest failed. Error: {process.stderr}")
            # redis_client.set(result_key, f"Error: {process.stderr}")
            return f"Backtest fail. {process.stderr}"
    except Exception as e:
        return f"Exception occurred: {str(e)}"
