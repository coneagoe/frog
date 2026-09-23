"""DAG for scanning A-share top10 floatholder data weekly."""

import os
import sys

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from airflow.sdk.exceptions import AirflowSkipException

# Ensure project root is on sys.path
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import (  # noqa: E402, I001
    get_default_args,
    get_partition_count,
    get_partition_ids,
    run_partition_items,
)

from monitor.top10_floatholder import run_ssf_change_alert  # noqa: E402

PARTITION_COUNT = get_partition_count()


def scan_top10_floatholder_partition_task(*, partition_id: int, partition_count: int, **context):
    """Scan A-share top10 floatholder data for a specific partition.

    Args:
        partition_id: The partition identifier (0-based)

    Returns:
        Success message with scan statistics

    Raises:
        AirflowSkipException: If partition is not active
        Exception: If any stock scan fails
    """
    from common.const import COL_STOCK_ID  # noqa: E402
    from download import DownloadManager  # noqa: E402
    from storage import get_storage  # noqa: E402

    if partition_id >= partition_count:
        raise AirflowSkipException(f"partition_id={partition_id} >= partition_count={partition_count}, skip")

    df_stocks = get_storage().load_general_info_stock()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    manager = DownloadManager()
    failed_count = 0

    def action(stock_id):
        nonlocal failed_count
        result = manager.download_top10_floatholders_a_stock(stock_id)
        if not result:
            failed_count += 1
        return result

    def on_progress(stock_id, completed, total):
        if completed % 100 == 0 or completed == total:
            print(
                f"[top10 floatholder scan p{partition_id:02d}] "
                f"进度: {completed}/{total} (failed={failed_count})"
            )

    def is_failure(result):
        return not result

    selected_ids, failures = run_partition_items(
        stock_ids,
        partition_id,
        partition_count,
        action,
        is_failure=is_failure,
        on_progress=on_progress,
    )
    failed_ids = [stock_id for stock_id, _ in failures]
    total = len(selected_ids)

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"前十大流通股东分片扫描失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return f"前十大流通股东扫描成功完成: partition={partition_id}/{partition_count}, count={total}"


dag = DAG(
    "scan_top10_floatholder_weekly",
    default_args=get_default_args(),
    description="Weekly A-share top10 floatholder scan",
    schedule="0 21 * * 0",
    catchup=False,
    max_active_runs=1,
)

partition_tasks = [
    PythonOperator(
        task_id=f"scan_top10_floatholder_p{pid:02d}",
        python_callable=scan_top10_floatholder_partition_task,
        op_kwargs={"partition_id": pid, "partition_count": PARTITION_COUNT},
        dag=dag,
    )
    for pid in get_partition_ids(PARTITION_COUNT)
]

analysis_task = PythonOperator(
    task_id="analyze_ssf_change_signals",
    python_callable=run_ssf_change_alert,
    do_xcom_push=False,
    dag=dag,
)

for task in partition_tasks:
    task >> analysis_task
