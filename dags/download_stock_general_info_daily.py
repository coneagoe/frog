"""DAG for downloading stock general info on weekdays."""

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


def download_stock_general_info_task(**context):
    """Download general info for stocks, ETFs, and HK GGT stocks.

    Returns:
        Success message if any download succeeds

    Raises:
        AirflowSkipException: If market is closed
        Exception: If all downloads fail
    """
    if not is_a_market_open_today():
        raise AirflowSkipException("Market is closed today.")

    manager = DownloadManager()

    print("开始下载股票基础信息...")
    stock_result = manager.download_general_info_stock()
    print("✅ A股基础信息下载成功" if stock_result else "❌ A股基础信息下载失败")

    print("开始下载ETF基础信息...")
    etf_result = manager.download_general_info_etf()
    print("✅ ETF基础信息下载成功" if etf_result else "❌ ETF基础信息下载失败")

    print("开始下载港股通基础信息...")
    hk_ggt_result = manager.download_general_info_hk_ggt()
    print("✅ 港股通基础信息下载成功" if hk_ggt_result else "❌ 港股通基础信息下载失败")

    if stock_result or etf_result or hk_ggt_result:
        return "基础信息下载任务完成"

    raise Exception("所有基础信息下载失败")


# Create DAG
dag = DAG(
    "download_stock_general_info_daily",
    default_args=__import__(
        "common_dags", fromlist=["get_default_args"]
    ).get_default_args(),
    description="Daily general info download for stocks, ETFs, and HK GGT stocks",
    schedule="0 16 * * 1-5",
    catchup=False,
    max_active_runs=1,
)

# Create task
PythonOperator(
    task_id="download_stock_general_info",
    python_callable=download_stock_general_info_task,
    dag=dag,
)
