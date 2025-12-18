import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock.data.downloader.download_status import (  # noqa: E402
    get_today_status_summary,
    status_manager,
)
from stock.data.factory import create_download_manager  # noqa: E402

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
    "download_daily_data",
    default_args=default_args,
    description="Daily stock and ETF data download",
    schedule="0 9 * * 1-5",  # 每个工作日上午9点执行
    catchup=False,
    max_active_runs=1,
)


def download_basic_info(**context):
    """下载基础信息任务"""
    manager = create_download_manager(storage_type="csv")
    success = manager.download_all_basic_info()

    if not success:
        raise Exception("Failed to download basic info")

    return "Basic info download completed successfully"


def download_stock_history_batch(**context):
    """批量下载股票历史数据"""
    # 这里可以从配置文件或数据库获取股票列表
    stock_ids = [
        "000001",
        "000002",
        "000858",
        "600000",
        "600036",
        "600519",
        "000858",
        "002415",
        "300014",
        "688981",
    ]

    manager = create_download_manager(storage_type="csv")
    manager.run_batch_history_download(
        item_ids=stock_ids,
        item_type="stock",
        period="daily",
        start_date="20240101",
        end_date=datetime.today().strftime("%Y%m%d"),
        adjust="qfq",
    )

    return f"Stock history download completed for {len(stock_ids)} stocks"


def download_etf_history_batch(**context):
    """批量下载ETF历史数据"""
    # ETF列表
    etf_ids = [
        "510300",
        "510500",
        "159919",
        "159915",
        "512880",
        "516160",
        "159941",
        "512170",
        "159928",
        "159985",
    ]

    manager = create_download_manager(storage_type="csv")
    manager.run_batch_history_download(
        item_ids=etf_ids,
        item_type="etf",
        period="daily",
        start_date="20240101",
        end_date=datetime.today().strftime("%Y%m%d"),
        adjust="qfq",
    )

    return f"ETF history download completed for {len(etf_ids)} ETFs"


def check_download_status(**context):
    """检查下载状态并生成报告"""
    status = get_today_status_summary()

    summary = status["summary"]
    print(f"Download Status Summary for {status['date']}:")
    print(f"Total tasks: {summary['total']}")
    print(f"Successful: {summary['success']}")
    print(f"Failed: {summary['failed']}")
    print(f"In progress: {summary['in_progress']}")

    # 如果有失败的任务，记录详细信息
    if summary["failed"] > 0:
        print("\nFailed tasks:")
        for task_name, task_data in status["tasks"].items():
            if task_data["status"] == "failed":
                print(
                    f"- {task_name}: {task_data.get('error_message', 'Unknown error')}"
                )

    return status


def cleanup_old_status(**context):
    """清理旧的状态记录"""
    status_manager.cleanup_old_records(keep_days=30)
    return "Cleanup completed"


# 定义任务
task_download_basic_info = PythonOperator(
    task_id="download_basic_info",
    python_callable=download_basic_info,
    dag=dag,
)

task_download_stock_history = PythonOperator(
    task_id="download_stock_history",
    python_callable=download_stock_history_batch,
    dag=dag,
)

task_download_etf_history = PythonOperator(
    task_id="download_etf_history",
    python_callable=download_etf_history_batch,
    dag=dag,
)

task_check_status = PythonOperator(
    task_id="check_download_status",
    python_callable=check_download_status,
    dag=dag,
)

task_cleanup = PythonOperator(
    task_id="cleanup_old_status",
    python_callable=cleanup_old_status,
    dag=dag,
    trigger_rule="all_done",  # 无论前面任务成功还是失败都执行
)

# 设置任务依赖关系
task_download_basic_info >> [task_download_stock_history, task_download_etf_history]
(
    [task_download_stock_history, task_download_etf_history]
    >> task_check_status
    >> task_cleanup
)
