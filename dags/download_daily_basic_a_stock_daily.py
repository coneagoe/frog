import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

# Ensure project root is on sys.path (Airflow container mounts code at /opt/airflow/frog)
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_alert_emails(raw: str) -> list[str]:
    return [
        email.strip() for email in raw.replace(";", ",").split(",") if email.strip()
    ]


ALERT_EMAILS = _parse_alert_emails(
    os.environ.get("ALERT_EMAILS") or os.environ.get("MAIL_RECEIVERS") or ""
)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# DAG 默认参数
default_args = {
    "owner": "frog",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1, tzinfo=LOCAL_TZ),
    "email": ALERT_EMAILS,
    "email_on_failure": bool(ALERT_EMAILS),
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "download_daily_basic_a_stock_daily",
    default_args=default_args,
    description="Weekdays daily_basic A-share download",
    schedule="0 18 * * 1-5",  # 每个工作日18点执行
    catchup=False,
    max_active_runs=1,
)


def download_daily_basic_a_stock_task(**context):
    """工作日下载A股 daily_basic 数据（单进程增量）。"""
    # Import heavy modules inside the task to keep DAG parsing fast.
    from common import is_a_market_open_today
    from download import DownloadManager

    if not is_a_market_open_today():
        raise AirflowSkipException("Market is closed today.")

    manager = DownloadManager()
    ok = manager.download_daily_basic_a_stock()
    if not ok:
        raise Exception("daily_basic 下载失败")

    return "A股 daily_basic 下载成功完成"


PythonOperator(
    task_id="download_daily_basic_a_stock",
    python_callable=download_daily_basic_a_stock_task,
    dag=dag,
)
