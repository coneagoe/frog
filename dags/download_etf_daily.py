"""DAG for downloading ETF daily data on weekdays."""

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

from common_dags import (  # noqa: E402
    LOCAL_TZ,
    get_default_args,
    get_partition_count,
    get_partition_ids,
    get_partitioned_ids,
)

from common import is_a_market_open_today  # noqa: E402
from common.const import COL_ETF_ID, AdjustType, PeriodType  # noqa: E402
from download import DownloadManager  # noqa: E402
from storage import get_storage  # noqa: E402

DEFAULT_START_DATE: Final = "2010-01-01"


def download_etf_daily_partition_task(*, partition_id: int, **context):
    """Download ETF daily data for a specific partition.

    Args:
        partition_id: The 0-based partition identifier

    Returns:
        Success message with download statistics

    Raises:
        AirflowSkipException: If market is closed or partition is not active
        Exception: If download fails
    """
    if not is_a_market_open_today():
        raise AirflowSkipException("A股市场今日休市，跳过下载任务")

    partition_count = get_partition_count()
    if partition_id >= partition_count:
        raise AirflowSkipException(
            f"partition_id={partition_id} >= partition_count={partition_count}, skip"
        )

    start_date = DEFAULT_START_DATE
    end_date = datetime.now(tz=LOCAL_TZ).date().isoformat()

    df_etfs = get_storage().load_etf_basic()
    if df_etfs is None or df_etfs.empty:
        raise Exception("无法获取ETF基本信息数据")

    etf_ids = df_etfs[COL_ETF_ID].tolist()
    my_ids = get_partitioned_ids(etf_ids, partition_id, partition_count)

    manager = DownloadManager()

    failed_ids: list[str] = []
    total = len(my_ids)
    for idx, etf_id in enumerate(my_ids, start=1):
        ok = manager.download_etf_history(
            etf_id=etf_id,
            period=PeriodType.DAILY,
            start_date=start_date,
            end_date=end_date,
            adjust=AdjustType.QFQ,
        )
        if not ok:
            failed_ids.append(etf_id)

        if idx % 50 == 0 or idx == total:
            print(
                f"[ETF p{partition_id:02d}] 进度: {idx}/{total} "
                f"(failed={len(failed_ids)})"
            )

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"ETF日线分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return (
        f"ETF日线数据下载成功完成: partition={partition_id}/{partition_count}, "
        f"count={total}"
    )


# Create DAG
dag = DAG(
    "download_etf_daily_weekdays",
    default_args=get_default_args(),
    description="Weekdays ETF daily data download",
    schedule="0 16 * * 1-5",
    catchup=False,
    max_active_runs=1,
)

# Create partition tasks
for _pid in get_partition_ids():
    PythonOperator(
        task_id=f"download_etf_daily_p{_pid:02d}",
        python_callable=download_etf_daily_partition_task,
        op_kwargs={"partition_id": _pid},
        dag=dag,
    )
