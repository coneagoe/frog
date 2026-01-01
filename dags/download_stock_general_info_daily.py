import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import is_a_market_open_today  # noqa: E402
from download import DownloadManager  # noqa: E402

# DAG 默认参数
default_args = {
    "owner": "frog",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# 创建 DAG
dag = DAG(
    "download_stock_general_info_daily",
    default_args=default_args,
    description="Daily stock general info download using download_general_info_stock",
    schedule="0 16 * * 1-5",  # 每个工作日下午4点执行
    catchup=False,
    max_active_runs=1,
)


def download_stock_general_info_task(**context):
    if not is_a_market_open_today():
        return "Market is closed today."

    try:
        # 创建下载管理器
        manager = DownloadManager()

        print("开始下载股票基础信息...")

        # 使用download_general_info_stock方法下载股票基础信息
        result = manager.download_general_info_stock(force=True)

        if result:
            print("✅ 股票基础信息下载成功")
            return "股票基础信息下载成功"
        else:
            error_message = "❌ 股票基础信息下载失败"
            print(error_message)
            raise Exception(error_message)

    except Exception as e:
        error_message = f"股票基础信息下载任务执行失败: {str(e)}"
        print(f"❌ {error_message}")
        raise Exception(error_message)


# 定义任务
task_download_stock_general_info = PythonOperator(
    task_id="download_stock_general_info",
    python_callable=download_stock_general_info_task,
    dag=dag,
)
