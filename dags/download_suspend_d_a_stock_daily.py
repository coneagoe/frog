"""DAG for downloading A-share suspend_d data on weekdays."""

import os
import sys

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

# Ensure project root is on sys.path
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import is_a_market_open_today  # noqa: E402
from download import DownloadManager  # noqa: E402


def download_suspend_d_a_stock_task(**context):
    """Download A-share suspend_d data.

    Returns:
        Success message

    Raises:
        AirflowSkipException: If market is closed
        Exception: If download fails
    """
    if not is_a_market_open_today():
        raise AirflowSkipException("Market is closed today.")

    manager = DownloadManager()
    ok = manager.download_suspend_d_a_stock()
    if not ok:
        raise Exception("suspend_d 下载失败")

    return "A股 suspend_d 下载成功完成"


# Create DAG
dag = DAG(
    "download_suspend_d_a_stock_daily",
    default_args=__import__(
        "common_dags", fromlist=["get_default_args"]
    ).get_default_args(),
    description="Weekdays suspend_d A-share download",
    schedule="0 9 * * 1-5",
    catchup=False,
    max_active_runs=1,
)

# Create task
PythonOperator(
    task_id="download_suspend_d_a_stock",
    python_callable=download_suspend_d_a_stock_task,
    dag=dag,
)
