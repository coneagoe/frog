"""DAG for downloading stock history (QFQ) on weekends."""

import os
import sys
from datetime import datetime, timedelta
from typing import Final

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

# Ensure project root is on sys.path
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.const import AdjustType, PeriodType, SecurityType  # noqa: E402

MAX_PARTITIONS: Final = 16


def reset_stock_history_qfq_table(**context):
    """Reset A-share QFQ history table for full rebuild on weekends."""
    from storage import get_storage, get_table_name  # noqa: E402

    table_name = get_table_name(SecurityType.STOCK, PeriodType.DAILY, AdjustType.QFQ)
    get_storage().drop_table(table_name)
    return f"cleared table: {table_name}"


def download_stock_history_qfq_partition_task(*, partition_id: int, **context):
    """Download A-share QFQ history data for a specific partition.

    Args:
        partition_id: The partition identifier (0-15)

    Returns:
        Success message with download statistics

    Raises:
        AirflowSkipException: If partition is not active
        Exception: If download fails
    """
    from common_dags import (  # noqa: E402
        LOCAL_TZ,
        get_partition_count,
        get_partitioned_ids,
    )

    from common.const import COL_STOCK_ID  # noqa: E402
    from download import DownloadManager  # noqa: E402
    from storage import get_storage  # noqa: E402

    partition_count = min(get_partition_count(), MAX_PARTITIONS)
    if partition_id >= partition_count:
        raise AirflowSkipException(
            f"partition_id={partition_id} >= partition_count={partition_count}, skip"
        )

    start_date = "2010-01-01"
    end_date = (datetime.now(tz=LOCAL_TZ) - timedelta(days=1)).date().isoformat()

    df_stocks = get_storage().load_general_info_stock()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    my_ids = get_partitioned_ids(stock_ids, partition_id, partition_count)

    manager = DownloadManager()

    failed_ids: list[str] = []
    total = len(my_ids)
    for idx, stock_id in enumerate(my_ids, start=1):
        ok = manager.download_stock_history(
            stock_id=stock_id,
            period=PeriodType.DAILY,
            start_date=start_date,
            end_date=end_date,
            adjust=AdjustType.QFQ,
        )
        if not ok:
            failed_ids.append(stock_id)

        if idx % 50 == 0 or idx == total:
            print(
                f"[QFQ p{partition_id:02d}] 进度: {idx}/{total} "
                f"(failed={len(failed_ids)})"
            )

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"QFQ 分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return (
        f"A股QFQ历史数据下载成功完成: partition={partition_id}/{partition_count}, "
        f"count={total}"
    )


# Create DAG
dag = DAG(
    "download_stock_history_qfq_weekend",
    default_args=__import__(
        "common_dags", fromlist=["get_default_args"]
    ).get_default_args(),
    description="Weekend stock history QFQ download",
    schedule="0 3 * * 0",
    catchup=False,
    max_active_runs=1,
)

# Create reset task
task_reset_stock_history_qfq = PythonOperator(
    task_id="reset_stock_history_qfq",
    python_callable=reset_stock_history_qfq_table,
    dag=dag,
)

# Create partition tasks with dependency on reset task
for _pid in range(MAX_PARTITIONS):
    task = PythonOperator(
        task_id=f"download_stock_history_qfq_p{_pid:02d}",
        python_callable=download_stock_history_qfq_partition_task,
        op_kwargs={"partition_id": _pid},
        dag=dag,
    )
    task_reset_stock_history_qfq >> task
