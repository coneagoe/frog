"""DAG for downloading HK GGT stock history (HFQ) on weekdays."""

import os
import sys
from datetime import datetime
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

from common.const import AdjustType, PeriodType  # noqa: E402

MAX_PARTITIONS: Final = 16


def download_hk_ggt_history_hfq_partition_task(*, partition_id: int, **context):
    """Download HK GGT HFQ history data for a specific partition.

    Args:
        partition_id: The partition identifier (0-15)

    Returns:
        Success message with download statistics

    Raises:
        AirflowSkipException: If market is closed or partition is not active
        Exception: If download fails
    """
    from common_dags import (  # noqa: E402
        LOCAL_TZ,
        get_partition_count,
        get_partitioned_ids,
    )

    from common import is_hk_market_open_today  # noqa: E402
    from common.const import COL_STOCK_ID  # noqa: E402
    from download import DownloadManager  # noqa: E402
    from storage import get_storage  # noqa: E402

    if not is_hk_market_open_today():
        raise AirflowSkipException("港股市场今日休市，跳过下载任务")

    partition_count = min(get_partition_count(), MAX_PARTITIONS)
    if partition_id >= partition_count:
        raise AirflowSkipException(
            f"partition_id={partition_id} >= partition_count={partition_count}, skip"
        )

    start_date = "2010-01-01"
    end_date = datetime.now(tz=LOCAL_TZ).date().isoformat()

    df_stocks = get_storage().load_general_info_hk_ggt()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取港股通股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    my_ids = get_partitioned_ids(stock_ids, partition_id, partition_count)

    manager = DownloadManager()

    failed_ids: list[str] = []
    total = len(my_ids)
    for idx, stock_id in enumerate(my_ids, start=1):
        ok = manager.download_hk_ggt_history(
            stock_id=stock_id,
            period=PeriodType.DAILY,
            start_date=start_date,
            end_date=end_date,
            adjust=AdjustType.HFQ,
        )
        if not ok:
            failed_ids.append(stock_id)

        if idx % 50 == 0 or idx == total:
            print(
                f"[HK HFQ p{partition_id:02d}] 进度: {idx}/{total} "
                f"(failed={len(failed_ids)})"
            )

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"HK HFQ 分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return (
        f"港股通HFQ历史数据下载成功完成: partition={partition_id}/{partition_count}, "
        f"count={total}"
    )


# Create DAG
dag = DAG(
    "download_hk_ggt_history_daily",
    default_args=__import__(
        "common_dags", fromlist=["get_default_args"]
    ).get_default_args(),
    description="Weekdays HK GGT stock history HFQ download",
    schedule="30 16 * * 1-5",
    catchup=False,
    max_active_runs=1,
)

# Create partition tasks
for _pid in range(MAX_PARTITIONS):
    PythonOperator(
        task_id=f"download_hk_ggt_history_hfq_p{_pid:02d}",
        python_callable=download_hk_ggt_history_hfq_partition_task,
        op_kwargs={"partition_id": _pid},
        dag=dag,
    )
