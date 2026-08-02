# ruff: noqa: I001
"""DAG for downloading stock history (HFQ) on weekdays."""

import json
import os
import sys
from dataclasses import asdict
from datetime import date
from typing import Any, cast

import redis
from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

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
from paper_trading.domain.market_data_diagnostics import canonical_adjust_label  # noqa: E402
from paper_trading.storage.repository import PaperTradingRepository  # noqa: E402
from stock.market import is_a_share_trade_date  # noqa: E402
from tools.paper_trading_cli import run_paper_trading_ledger_rebuild  # noqa: E402
from tools.paper_trading_cli import run_paper_trading_matching  # noqa: E402, I001


def _persist_diagnostic(session, business_date, stock_id, adjust, outcome):
    PaperTradingRepository(session).upsert_daily_bar_diagnostic(
        business_date,
        stock_id,
        canonical_adjust_label(adjust),
        outcome.classification,
        [asdict(item) for item in outcome.provider_outcomes],
        outcome.resolved,
    )


def get_redis_client() -> redis.Redis:
    """Get Redis client for storing results."""
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url, decode_responses=True)


PARTITION_COUNT = get_partition_count()


def get_business_date(context: dict[str, Any]) -> date:
    """Get the scheduled business date in the configured local timezone."""
    return cast(date, context["data_interval_end"].in_timezone(LOCAL_TZ).date())


def ensure_a_share_trade_date(context: dict[str, Any]) -> date:
    """Skip daily-history work when the scheduled date is not a trade date."""
    business_date = get_business_date(context)
    if not is_a_share_trade_date(business_date):
        raise AirflowSkipException(f"A股{business_date.isoformat()}休市，跳过任务")
    return business_date


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
    from storage import get_storage  # noqa: E402

    business_date = ensure_a_share_trade_date(context)

    if partition_id >= partition_count:
        raise AirflowSkipException(f"partition_id={partition_id} >= partition_count={partition_count}, skip")

    start_date = "2010-01-01"

    df_stocks = get_storage().load_general_info_stock()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    my_ids = get_partitioned_ids(stock_ids, partition_id, partition_count)

    manager = DownloadManager()

    outcomes = []
    storage = get_storage()
    assert storage.Session is not None
    session = storage.Session()
    total = len(my_ids)
    try:
        for idx, stock_id in enumerate(my_ids, start=1):
            outcome = manager.download_stock_history_outcome(
                stock_id=stock_id,
                period=PeriodType.DAILY,
                start_date=start_date,
                end_date=business_date.isoformat(),
                adjust=AdjustType.HFQ,
            )
            outcomes.append(asdict(outcome))
            if outcome.classification != "downloaded":
                _persist_diagnostic(session, business_date, stock_id, AdjustType.HFQ, outcome)
            if idx % 50 == 0 or idx == total:
                print(f"[HFQ p{partition_id:02d}] 进度: {idx}/{total}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return {"adjust": "hfq", "partition_id": partition_id, "count": total, "outcomes": outcomes}


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
    from storage import get_storage  # noqa: E402

    business_date = ensure_a_share_trade_date(context)

    if partition_id >= partition_count:
        raise AirflowSkipException(f"partition_id={partition_id} >= partition_count={partition_count}, skip")

    start_date = "2020-01-01"

    df_stocks = get_storage().load_general_info_stock()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    my_ids = get_partitioned_ids(stock_ids, partition_id, partition_count)

    manager = DownloadManager()

    outcomes = []
    storage = get_storage()
    assert storage.Session is not None
    session = storage.Session()
    total = len(my_ids)
    try:
        for idx, stock_id in enumerate(my_ids, start=1):
            outcome = manager.download_stock_history_outcome(
                stock_id=stock_id,
                period=PeriodType.DAILY,
                start_date=start_date,
                end_date=business_date.isoformat(),
                adjust=AdjustType.BFQ,
            )
            outcomes.append(asdict(outcome))
            if outcome.classification != "downloaded":
                _persist_diagnostic(session, business_date, stock_id, AdjustType.BFQ, outcome)
            if idx % 50 == 0 or idx == total:
                print(f"[BFQ p{partition_id:02d}] 进度: {idx}/{total}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return {"adjust": "bfq", "partition_id": partition_id, "count": total, "outcomes": outcomes}


def save_download_result_to_redis(*, partition_count: int, **context):
    """Aggregate partition results (HFQ + BFQ) and write success/fail to Redis."""
    business_date = ensure_a_share_trade_date(context)
    ti = context["ti"]
    warning_symbols: set[str] = set()
    evidence: list[dict[str, Any]] = []

    for adjust_prefix in ("hfq", "bfq"):
        for pid in range(partition_count):
            task_id = f"download_stock_history_{adjust_prefix}_p{pid:02d}"
            result = ti.xcom_pull(task_ids=task_id)
            if not isinstance(result, dict):
                raise ValueError(f"invalid partition outcome for {task_id}")
            for outcome in result.get("outcomes", []):
                if outcome.get("classification") != "downloaded":
                    warning_symbols.add(outcome["stock_id"])
                    evidence.append({"adjust": result["adjust"], **outcome})

    r = get_redis_client()
    evidence.sort(key=lambda item: (item["stock_id"], item["adjust"]))
    summary = {
        "date": business_date.isoformat(),
        "result": "success",
        "status": "warning" if warning_symbols else "success",
        "missing_symbols": sorted(warning_symbols),
        "provider_evidence": evidence[:20],
    }

    r.set(
        REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY,
        json.dumps(summary, ensure_ascii=False),
        ex=86400,
    )

    return f"Results saved to Redis: {REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY}, result=success"


def run_paper_trading_matching_for_active_accounts(**context):
    """Run paper-trading matching for all active accounts after successful download."""
    ti: Any = context.get("ti")
    aggregate_summary = ti.xcom_pull(task_ids="save_download_result_to_redis") if ti is not None else None
    aggregate_is_fatal = isinstance(aggregate_summary, dict) and aggregate_summary.get("result") != "success"
    aggregate_is_fatal = aggregate_is_fatal or (
        isinstance(aggregate_summary, str) and "result=fail" in aggregate_summary
    )
    if aggregate_is_fatal:
        raise AirflowSkipException("daily-history aggregate was fatal; skip paper trading matching")
    trade_date = ensure_a_share_trade_date(context)
    result = run_paper_trading_matching(
        trade_date=trade_date.isoformat(),
        base_url=os.environ.get("PAPER_TRADING_API_BASE_URL", "http://paper-trading:8000"),
        token=os.environ["PAPER_TRADING_API_TOKEN"],
    )
    warning_count = result.get("warning_count")
    rebuild_result = run_paper_trading_ledger_rebuild(
        base_url=os.environ.get("PAPER_TRADING_API_BASE_URL", "http://paper-trading:8000"),
        token=os.environ["PAPER_TRADING_API_TOKEN"],
    )
    rebuilt_accounts = rebuild_result.get("rebuilt_account_ids", [])
    warning_suffix = f", warning_count={warning_count}" if warning_count is not None else ""
    return (
        f"Paper trading matching completed: trade_date={trade_date.isoformat()}, "
        f"run_id={result.get('id')}{warning_suffix}, rebuilt_accounts={len(rebuilt_accounts)}"
    )


# Create DAG
dag = DAG(
    "download_stock_history_weekdays",
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
    trigger_rule=TriggerRule.ALL_SUCCESS,
    dag=dag,
)

paper_trading_matching_task = PythonOperator(
    task_id="run_paper_trading_matching",
    python_callable=run_paper_trading_matching_for_active_accounts,
    trigger_rule=TriggerRule.ALL_SUCCESS,
    dag=dag,
)

all_partition_tasks = hfq_partition_tasks + bfq_partition_tasks
for _task in all_partition_tasks:
    _task >> aggregate_task

aggregate_task >> paper_trading_matching_task
