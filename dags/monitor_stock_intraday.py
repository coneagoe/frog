"""DAG for monitoring stock conditions during trading hours (every 5 minutes)."""

import os
import sys

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_dags import get_default_args  # noqa: E402

from common import is_a_market_open_today  # noqa: E402


def run_intraday_monitor(**context):
    """Evaluate intraday-frequency monitor targets during trading hours."""
    if not is_a_market_open_today():
        raise AirflowSkipException("非交易日，跳过盘中监控任务")

    from datetime import datetime as dt
    from zoneinfo import ZoneInfo

    now_cn = dt.now(tz=ZoneInfo("Asia/Shanghai"))
    current_time = now_cn.strftime("%H:%M")
    if not ("09:30" <= current_time <= "15:00"):
        raise AirflowSkipException(
            f"当前时间 {current_time} 不在交易时段 09:30-15:00，跳过"
        )

    from monitor.monitor_runner import run_monitor

    summary = run_monitor(frequency="intraday")
    msg = (
        f"盘中监控完成: 共{summary.total}个目标, "
        f"触发{summary.triggered}个, 跳过{summary.skipped}个, 错误{summary.errors}个"
    )
    if summary.errors:
        raise Exception(f"{msg}\n错误详情: {summary.error_details}")
    return msg


dag = DAG(
    "monitor_stock_intraday",
    default_args=get_default_args(),
    description="盘中每5分钟检查股票监控条件",
    schedule="*/5 9-15 * * 1-5",
    catchup=False,
    max_active_runs=1,
    tags=["monitor"],
)

PythonOperator(
    task_id="run_intraday_monitor",
    python_callable=run_intraday_monitor,
    dag=dag,
)
