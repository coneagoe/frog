"""DAG for downloading A-share basic info weekly."""

import os
import sys

from airflow import DAG
from airflow.operators.python import PythonOperator

# Ensure project root and dags directory are on sys.path
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Also add dags directory to sys.path for common_dags import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from download import DownloadManager  # noqa: E402


def download_a_stock_basic_task(**context):
    """Download A-share basic info.

    Returns:
        Success message

    Raises:
        Exception: If download fails
    """
    manager = DownloadManager()
    ok = manager.download_a_stock_basic(list_status="L")
    if not ok:
        raise Exception("stock_basic 下载失败")

    return "A股基础信息下载成功完成"


# Create DAG
dag = DAG(
    "download_a_stock_basic_weekly",
    default_args=__import__(
        "common_dags", fromlist=["get_default_args"]
    ).get_default_args(),
    description="Weekly A-stock basic info download",
    schedule="0 20 * * 0",
    catchup=False,
    max_active_runs=1,
)

# Create task
PythonOperator(
    task_id="download_a_stock_basic",
    python_callable=download_a_stock_basic_task,
    dag=dag,
)
