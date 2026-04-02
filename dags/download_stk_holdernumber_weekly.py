"""DAG for downloading A-share stk_holdernumber (shareholder count) data weekly."""

import os
import sys
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

MAX_PARTITIONS: Final = 4


def download_stk_holdernumber_partition_task(*, partition_id: int, **context):
    """Download A-share shareholder count data for a specific partition.

    Args:
        partition_id: The partition identifier (0-3)

    Returns:
        Success message with download statistics

    Raises:
        AirflowSkipException: If partition is not active
        Exception: If any stock download fails
    """
    from common_dags import (  # noqa: E402
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

    df_stocks = get_storage().load_general_info_stock()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    my_ids = get_partitioned_ids(stock_ids, partition_id, partition_count)

    manager = DownloadManager()
    failed_ids: list[str] = []
    total = len(my_ids)

    for idx, stock_id in enumerate(my_ids, start=1):
        ok = manager.download_stk_holdernumber_a_stock(stock_id)
        if not ok:
            failed_ids.append(stock_id)

        if idx % 100 == 0 or idx == total:
            print(
                f"[holdernumber p{partition_id:02d}] 进度: {idx}/{total} "
                f"(failed={len(failed_ids)})"
            )

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"股东人数分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return (
        f"股东人数下载成功完成: partition={partition_id}/{partition_count}, "
        f"count={total}"
    )


# Create DAG
dag = DAG(
    "download_stk_holdernumber_weekly",
    default_args=__import__(
        "common_dags", fromlist=["get_default_args"]
    ).get_default_args(),
    description="Weekly A-share shareholder count (stk_holdernumber) download",
    schedule="0 21 * * 0",
    catchup=False,
    max_active_runs=1,
)

# Create partition tasks
for _pid in range(MAX_PARTITIONS):
    PythonOperator(
        task_id=f"download_stk_holdernumber_p{_pid:02d}",
        python_callable=download_stk_holdernumber_partition_task,
        op_kwargs={"partition_id": _pid},
        dag=dag,
    )
