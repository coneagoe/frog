import os
import subprocess
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from celery_app import app
from stock import is_hk_market_open_today
from utility import send_email
from .obos_hk import obos_hk


@app.task
def download_hk_stock_data():
    if not is_hk_market_open_today():
        return "Market is closed today."

    try:
        command = ["python", "tools/download_history_data_stock_hk.py"]
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command,
                                                output=process.stdout, stderr=process.stderr)

        obos_hk.delay()
        return "Download success."
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.strip()
        send_email(
            subject="HK Stock Data Download Failed",
            body=error_message
        )
        return f"Download failed: {error_message}"
    except Exception as e:
        send_email(
            subject="HK Stock Data Download Failed",
            body=str(e)
        )
        return f"An exception occurred: {str(e)}"
