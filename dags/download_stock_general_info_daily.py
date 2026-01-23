import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import is_a_market_open_today  # noqa: E402
from download import DownloadManager  # noqa: E402


def _parse_alert_emails(raw: str) -> list[str]:
    return [
        email.strip() for email in raw.replace(";", ",").split(",") if email.strip()
    ]


ALERT_EMAILS = _parse_alert_emails(
    os.environ.get("ALERT_EMAILS") or os.environ.get("MAIL_RECEIVERS") or ""
)

# DAG 默认参数
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

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

# 创建 DAG
dag = DAG(
    "download_stock_general_info_daily",
    default_args=default_args,
    description="Daily general info download for stocks, ETFs, and HK GGT stocks",
    schedule="0 16 * * 1-5",  # 每个工作日下午4点执行
    catchup=False,
    max_active_runs=1,
)


def download_stock_general_info_task(**context):
    # Import heavy modules inside the task to keep DAG parsing fast.
    if not is_a_market_open_today():
        raise AirflowSkipException("Market is closed today.")

    try:
        # 创建下载管理器
        manager = DownloadManager()

        print("开始下载股票基础信息...")

        # 下载A股基础信息
        stock_result = manager.download_general_info_stock()
        if stock_result:
            print("✅ A股基础信息下载成功")
        else:
            print("❌ A股基础信息下载失败")

        # 下载ETF基础信息
        print("开始下载ETF基础信息...")
        etf_result = manager.download_general_info_etf()
        if etf_result:
            print("✅ ETF基础信息下载成功")
        else:
            print("❌ ETF基础信息下载失败")

        # 下载港股通基础信息
        print("开始下载港股通基础信息...")
        hk_ggt_result = manager.download_general_info_hk_ggt()
        if hk_ggt_result:
            print("✅ 港股通基础信息下载成功")
        else:
            print("❌ 港股通基础信息下载失败")

        # 如果至少有一个成功，则任务成功
        if stock_result or etf_result or hk_ggt_result:
            return "基础信息下载任务完成"
        else:
            error_message = "❌ 所有基础信息下载失败"
            print(error_message)
            raise Exception(error_message)

    except Exception as e:
        error_message = f"基础信息下载任务执行失败: {str(e)}"
        print(f"❌ {error_message}")
        raise Exception(error_message)


# 定义任务
task_download_stock_general_info = PythonOperator(
    task_id="download_stock_general_info",
    python_callable=download_stock_general_info_task,
    dag=dag,
)
