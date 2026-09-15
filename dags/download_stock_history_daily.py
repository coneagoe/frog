# ruff: noqa: I001
"""DAG for downloading stock history (HFQ) on weekdays."""

import json
import os
import sys
from dataclasses import asdict
from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import redis
from airflow.sdk.exceptions import AirflowSkipException
from airflow.utils.trigger_rule import TriggerRule
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG


# Ensure project root is on sys.path
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import (  # noqa: E402
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
from paper_trading.domain.enums import Market  # noqa: E402
from paper_trading.domain.market_data_diagnostics import canonical_adjust_label  # noqa: E402
from paper_trading.domain.enums import (  # noqa: E402
    DataGapRecoveryBatchStatus,
    DataGapRecoveryClassification,
    DataGapRecoveryRouting,
)
from paper_trading.services.data_gap_recovery_service import DataGapRecoveryService  # noqa: E402
from paper_trading.storage.data_gap_recovery_repository import DataGapRecoveryRepository  # noqa: E402
from paper_trading.storage.repository import PaperTradingRepository  # noqa: E402
from stock.market import is_a_share_trade_date  # noqa: E402
from storage import get_storage  # noqa: E402
from tools.paper_trading_cli import run_paper_trading_ledger_rebuild  # noqa: E402
from tools.paper_trading_cli import run_paper_trading_matching  # noqa: E402, I001


def _persist_diagnostic(storage, business_date, stock_id, adjust, outcome):
    """Persist one diagnostic without holding a connection during downloads."""
    assert storage.Session is not None
    session = storage.Session()
    try:
        PaperTradingRepository(session).upsert_daily_bar_diagnostic(
            business_date,
            Market.A_SHARE,
            stock_id,
            canonical_adjust_label(adjust),
            outcome.classification,
            [asdict(item) for item in outcome.provider_outcomes],
            outcome.resolved,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_redis_client() -> redis.Redis:
    """Get Redis client for storing results."""
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url, decode_responses=True)


PARTITION_COUNT = get_partition_count()


def get_business_date(context: dict[str, Any]) -> date:
    """Get the scheduled business date in the configured local timezone."""
    return cast(date, context["logical_date"].in_timezone(LOCAL_TZ).date())


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
    total = len(my_ids)
    storage = get_storage()
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
            _persist_diagnostic(storage, business_date, stock_id, AdjustType.HFQ, outcome)
        if idx % 50 == 0 or idx == total:
            print(f"[HFQ p{partition_id:02d}] 进度: {idx}/{total}")

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
    total = len(my_ids)
    storage = get_storage()
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
            _persist_diagnostic(storage, business_date, stock_id, AdjustType.BFQ, outcome)
        if idx % 50 == 0 or idx == total:
            print(f"[BFQ p{partition_id:02d}] 进度: {idx}/{total}")

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


def run_unified_bfq_data_gap_recovery(**context) -> dict[str, Any]:
    """Run the independent post-matching ordinary BFQ recovery batch."""
    ti: Any = context.get("ti")
    aggregate_summary = ti.xcom_pull(task_ids="save_download_result_to_redis") if ti is not None else None
    aggregate_is_fatal = isinstance(aggregate_summary, dict) and aggregate_summary.get("result") != "success"
    aggregate_is_fatal = aggregate_is_fatal or (
        isinstance(aggregate_summary, str) and "result=fail" in aggregate_summary
    )
    if aggregate_is_fatal:
        raise AirflowSkipException("daily-history aggregate was fatal; skip unified BFQ recovery")

    business_date = ensure_a_share_trade_date(context)
    storage = get_storage()
    assert storage.Session is not None
    session = storage.Session()
    try:
        repository = DataGapRecoveryRepository(session)
        diagnostics = get_unresolved_ordinary_gaps(repository=repository, business_date=business_date)
        gaps = [
            _detach_gap(
                repository.get_or_create_gap_from_diagnostic(
                    diagnostic,
                    routing=DataGapRecoveryRouting.ORDINARY,
                    classification=classify_diagnostic(diagnostic),
                )
            )
            for diagnostic in diagnostics
        ]
        batch = repository.record_batch(
            DataGapRecoveryBatchStatus.RUNNING,
            {"business_date": business_date.isoformat()},
        )
        session.commit()
        batch_id = batch.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    recovery_repository = _FreshSessionRecoveryRepository(storage)
    results: list[Any] = []
    try:
        results = DataGapRecoveryService(repository=recovery_repository).recover_unresolved_ordinary_gaps(
            gaps, batch_id=batch_id
        )
        batch_status = (
            DataGapRecoveryBatchStatus.FAILED
            if any(item.status == "failed" for item in results)
            else DataGapRecoveryBatchStatus.COMPLETED
        )
        recovery_repository.finalize_batch(
            batch_id,
            batch_status,
            gap_count=len(results),
            recovered_count=sum(item.status in {"recovered", "skipped"} for item in results),
            failed_count=sum(item.status == "failed" for item in results),
            summary={"business_date": business_date.isoformat(), "results": [asdict(item) for item in results]},
        )
    except Exception:
        processed_results = getattr(sys.exc_info()[1], "partial_results", results)
        recovery_repository.finalize_batch(
            batch_id,
            DataGapRecoveryBatchStatus.FAILED,
            gap_count=len(processed_results),
            recovered_count=sum(item.status in {"recovered", "skipped"} for item in processed_results),
            failed_count=sum(item.status == "failed" for item in processed_results),
            summary={"business_date": business_date.isoformat(), "error": "recovery batch failed"},
        )
        raise
    return {
        "date": business_date.isoformat(),
        "gap_count": len(results),
        "results": [asdict(item) for item in results],
    }


def _detach_gap(gap: Any) -> Any:
    """Detach recovery fields needed after the metadata session is closed."""
    return SimpleNamespace(
        id=gap.id,
        business_date=gap.business_date,
        stock_id=gap.stock_id,
        market=gap.market,
        adjust=gap.adjust,
        summary=dict(getattr(gap, "summary", {}) or {}),
    )


class _FreshSessionRecoveryRepository:
    """Persist recovery events with short-lived sessions, never across providers."""

    def __init__(self, storage: Any):
        self.storage = storage

    def _call(self, callback):
        assert self.storage.Session is not None
        session = self.storage.Session()
        try:
            result = callback(DataGapRecoveryRepository(session))
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def record_attempt(self, *args: Any) -> Any:
        return self._call(lambda repository: repository.record_attempt(*args))

    def resolve_gap(self, gap_id: int) -> None:
        self._call(lambda repository: repository.resolve_gap(gap_id))

    def finalize_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._call(lambda repository: repository.finalize_batch(*args, **kwargs))


def classify_diagnostic(diagnostic: Any) -> DataGapRecoveryClassification:
    """Map a persisted daily-bar diagnostic to ordinary recovery policy."""
    if getattr(diagnostic, "classification", None) == "missing_exact_date":
        return DataGapRecoveryClassification.VALUATION_ONLY
    return DataGapRecoveryClassification.ORDER_DEPENDENT


def get_unresolved_ordinary_gaps(repository: DataGapRecoveryRepository, *, business_date: date) -> list[Any]:
    """Load ordinary unresolved BFQ diagnostics for the recovery date."""
    return repository.list_unresolved_ordinary_diagnostics(business_date=business_date)


# Create DAG
dag = DAG(
    "download_stock_history_weekdays",
    default_args=get_default_args(),
    description="Weekdays stock history HFQ download",
    schedule="0 18 * * 1-5",
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

data_gap_recovery_task = PythonOperator(
    task_id="data_gap_recovery",
    python_callable=run_unified_bfq_data_gap_recovery,
    trigger_rule=TriggerRule.ALL_SUCCESS,
    dag=dag,
)

all_partition_tasks = hfq_partition_tasks + bfq_partition_tasks
for _task in all_partition_tasks:
    _task >> aggregate_task

aggregate_task >> paper_trading_matching_task
paper_trading_matching_task >> data_gap_recovery_task
