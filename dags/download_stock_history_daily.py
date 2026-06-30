"""DAG for downloading stock history (HFQ) on weekdays."""

import json
import os
import sys
from datetime import datetime

import redis
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

from common.const import (  # noqa: E402
    DEFAULT_REDIS_URL,
    REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY,
    AdjustType,
    PeriodType,
)


def get_redis_client() -> redis.Redis:
    """Get Redis client for storing results."""
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url, decode_responses=True)


PARTITION_COUNT = get_partition_count()


def download_stock_history_hfq_partition_task(*, partition_id: int, partition_count: int, **context):
    """Download A-share HFQ history data for a specific partition.

    Args:
        partition_id: The partition identifier (0-based)

    Returns:
        Success message with download statistics

    Raises:
        AirflowSkipException: If market is closed or partition is not active
        Exception: If download fails
    """
    from common.const import COL_STOCK_ID  # noqa: E402
    from download import DownloadManager  # noqa: E402
    from stock.market import is_a_market_open_today  # noqa: E402
    from storage import get_storage  # noqa: E402

    if not is_a_market_open_today():
        raise AirflowSkipException("A股市场今日休市，跳过下载任务")

    if partition_id >= partition_count:
        raise AirflowSkipException(f"partition_id={partition_id} >= partition_count={partition_count}, skip")

    start_date = "2010-01-01"
    end_date = datetime.now(tz=LOCAL_TZ).date().isoformat()

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
            adjust=AdjustType.HFQ,
        )
        if not ok:
            failed_ids.append(stock_id)

        if idx % 50 == 0 or idx == total:
            print(f"[HFQ p{partition_id:02d}] 进度: {idx}/{total} (failed={len(failed_ids)})")

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"HFQ 分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return f"A股HFQ历史数据下载成功完成: partition={partition_id}/{partition_count}, count={total}"


def download_stock_history_bfq_partition_task(*, partition_id: int, partition_count: int, **context):
    """Download A-share BFQ history data for a specific partition.

    Args:
        partition_id: The partition identifier (0-based)

    Returns:
        Success message with download statistics

    Raises:
        AirflowSkipException: If market is closed or partition is not active
        Exception: If download fails
    """
    from common.const import COL_STOCK_ID  # noqa: E402
    from download import DownloadManager  # noqa: E402
    from stock.market import is_a_market_open_today  # noqa: E402
    from storage import get_storage  # noqa: E402

    if not is_a_market_open_today():
        raise AirflowSkipException("A股市场今日休市，跳过下载任务")

    if partition_id >= partition_count:
        raise AirflowSkipException(f"partition_id={partition_id} >= partition_count={partition_count}, skip")

    start_date = "2020-01-01"
    end_date = datetime.now(tz=LOCAL_TZ).date().isoformat()

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
            adjust=AdjustType.BFQ,
        )
        if not ok:
            failed_ids.append(stock_id)

        if idx % 50 == 0 or idx == total:
            print(f"[BFQ p{partition_id:02d}] 进度: {idx}/{total} (failed={len(failed_ids)})")

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"BFQ 分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return f"A股BFQ历史数据下载成功完成: partition={partition_id}/{partition_count}, count={total}"


def save_download_result_to_redis(*, partition_count: int, **context):
    """Aggregate partition results (HFQ + BFQ) and write success/fail to Redis."""
    ti = context["ti"]
    total_count = 0

    for adjust_prefix in ("hfq", "bfq"):
        for pid in range(partition_count):
            task_id = f"download_stock_history_{adjust_prefix}_p{pid:02d}"
            result = ti.xcom_pull(task_ids=task_id)
            if result and "count=" in result:
                count = int(result.split("count=")[1].split(",")[0])
                total_count += count

    r = get_redis_client()
    execution_date = datetime.now(tz=LOCAL_TZ).date().isoformat()
    result_str = "success" if total_count > 0 else "fail"
    summary = {"date": execution_date, "result": result_str}

    r.set(
        REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY,
        json.dumps(summary, ensure_ascii=False),
        ex=86400,
    )

    return f"Results saved to Redis: {REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY}, result={result_str}"


def run_paper_trading_matching_for_active_accounts(**context):
    """Run paper-trading matching for all active accounts after successful download."""
    from paper_trading.api.deps import get_market_data_provider, get_session  # noqa: E402
    from paper_trading.domain.enums import AccountStatus  # noqa: E402
    from paper_trading.services.matching_service import MatchingService  # noqa: E402
    from paper_trading.services.snapshot_service import SnapshotService  # noqa: E402
    from paper_trading.storage.repository import PaperTradingRepository  # noqa: E402

    trade_date = datetime.now(tz=LOCAL_TZ).date()
    session_generator = get_session()
    session = next(session_generator)
    try:
        repo = PaperTradingRepository(session)
        market_data = get_market_data_provider()
        active_accounts = [account for account in repo.list_accounts() if account.status == AccountStatus.ACTIVE.value]
        if not active_accounts:
            return f"No active paper trading accounts for matching: trade_date={trade_date.isoformat()}"

        runs = []
        for account in active_accounts:
            run = MatchingService(repo, market_data, SnapshotService(repo, market_data)).run(trade_date, account.id)
            runs.append(run.id)
        session.commit()
        return (
            "Paper trading matching completed: "
            f"trade_date={trade_date.isoformat()}, accounts={len(active_accounts)}, runs={runs}"
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Create DAG
dag = DAG(
    "download_stock_history_hfq_weekdays",
    default_args=get_default_args(),
    description="Weekdays stock history HFQ download",
    schedule="0 16 * * 1-5",
    catchup=False,
    max_active_runs=1,
)

# Create HFQ partition tasks
hfq_partition_tasks = [
    PythonOperator(
        task_id=f"download_stock_history_hfq_p{pid:02d}",
        python_callable=download_stock_history_hfq_partition_task,
        op_kwargs={"partition_id": pid, "partition_count": PARTITION_COUNT},
        dag=dag,
    )
    for pid in get_partition_ids(PARTITION_COUNT)
]

# Create BFQ partition tasks
bfq_partition_tasks = [
    PythonOperator(
        task_id=f"download_stock_history_bfq_p{pid:02d}",
        python_callable=download_stock_history_bfq_partition_task,
        op_kwargs={"partition_id": pid, "partition_count": PARTITION_COUNT},
        dag=dag,
    )
    for pid in get_partition_ids(PARTITION_COUNT)
]

# Aggregate task runs after all HFQ and BFQ partitions complete
aggregate_task = PythonOperator(
    task_id="save_download_result_to_redis",
    python_callable=save_download_result_to_redis,
    op_kwargs={"partition_count": PARTITION_COUNT},
    dag=dag,
)

paper_trading_matching_task = PythonOperator(
    task_id="run_paper_trading_matching",
    python_callable=run_paper_trading_matching_for_active_accounts,
    dag=dag,
)

all_partition_tasks = hfq_partition_tasks + bfq_partition_tasks
for _task in all_partition_tasks:
    _task >> aggregate_task

aggregate_task >> paper_trading_matching_task
