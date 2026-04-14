"""DAG for monitoring stock conditions after daily market close."""

import os
import sys
from datetime import datetime

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_dags import LOCAL_TZ, get_default_args  # noqa: E402
from common import is_a_market_open_today  # noqa: E402


def run_daily_monitor(**context):
    """Evaluate daily-frequency monitor targets after market close."""
    if not is_a_market_open_today():
        raise AirflowSkipException("非交易日，跳过每日监控任务")

    from monitor.monitor_runner import run_monitor

    summary = run_monitor(frequency="daily")
    msg = (
        f"每日监控完成: 共{summary.total}个目标, "
        f"触发{summary.triggered}个, 跳过{summary.skipped}个, 错误{summary.errors}个"
    )
    if summary.errors:
        raise Exception(f"{msg}\n错误详情: {summary.error_details}")
    return msg


dag = DAG(
    "monitor_stock_daily",
    default_args=get_default_args(),
    description="每日收盘后检查股票监控条件",
    schedule="30 15 * * 1-5",
    catchup=False,
    max_active_runs=1,
    tags=["monitor"],
)

PythonOperator(
    task_id="run_daily_monitor",
    python_callable=run_daily_monitor,
    dag=dag,
)
