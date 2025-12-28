import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# Ensure project root is on sys.path (Airflow container mounts code at /opt/airflow/frog)
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import is_a_market_open_today  # noqa: E402
from common.const import AdjustType, PeriodType  # noqa: E402
from download import DownloadManager  # noqa: E402


def _parse_alert_emails(raw: str) -> list[str]:
    return [
        email.strip() for email in raw.replace(";", ",").split(",") if email.strip()
    ]


ALERT_EMAILS = _parse_alert_emails(
    os.environ.get("ALERT_EMAILS") or os.environ.get("MAIL_RECEIVERS") or ""
)

# DAG 默认参数
default_args = {
    "owner": "frog",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email": ALERT_EMAILS,
    "email_on_failure": bool(ALERT_EMAILS),
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "download_stock_history_hfq_weekdays",
    default_args=default_args,
    description="Weekdays stock history HFQ download",
    schedule="0 16 * * 1-5",  # 每个工作日下午4点执行
    catchup=False,
    max_active_runs=1,
)


def download_stock_history_task(**context):
    """工作日下载A股HFQ历史数据任务"""
    if not is_a_market_open_today():
        print("A股市场今日休市，跳过下载任务")
        return "Market is closed today, task skipped."

    try:
        manager = DownloadManager()

        start_date = "2010-01-01"
        end_date = datetime.today().strftime("%Y-%m-%d")

        print("开始批量下载A股历史数据（HFQ）...")
        print(f"日期范围: {start_date} 到 {end_date}")

        success = manager.download_all_stock_history(
            period=PeriodType.DAILY,
            adjust=AdjustType.HFQ,
            start_date=start_date,
            end_date=end_date,
        )

        if not success:
            raise Exception("部分股票HFQ历史数据下载失败，请查看日志了解详情")

        return "A股HFQ历史数据下载成功完成"

    except Exception as e:
        error_message = f"股票HFQ历史数据下载任务执行失败: {str(e)}"
        print(f"❌ {error_message}")
        raise Exception(error_message)


task_download_stock_history_hfq = PythonOperator(
    task_id="download_stock_history_hfq",
    python_callable=download_stock_history_task,
    dag=dag,
)
