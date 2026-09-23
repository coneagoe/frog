"""DAG for downloading HK GGT stock unadjusted daily history on weekdays."""

import json
import os
import sys
from dataclasses import asdict
from datetime import date
from typing import Any, Callable, Final, cast

import redis
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from airflow.sdk.exceptions import AirflowSkipException
from airflow.utils.trigger_rule import TriggerRule

# Ensure project root is on sys.path
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import (  # noqa: E402, I001
    LOCAL_TZ,
    get_default_args,
    get_partition_ids,
    run_partition_items,
)

from common.const import (  # noqa: E402
    COL_STOCK_ID,
    DEFAULT_REDIS_URL,
    REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY,
    AdjustType,
    PeriodType,
)
from download import DownloadManager  # noqa: E402
from paper_trading.domain.enums import Market  # noqa: E402
from paper_trading.domain.market_data_diagnostics import canonical_adjust_label  # noqa: E402
from paper_trading.storage.repository import PaperTradingRepository  # noqa: E402
from paper_trading.services.data_gap_recovery_service import HkRecoveryAuthorityPolicy  # noqa: E402
from paper_trading.services.trade_calendar import HkTradeCalendar  # noqa: E402
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider  # noqa: E402
from paper_trading.storage.market_data import StorageMarketDataProvider  # noqa: E402
from dags.download_stock_history_daily import (  # noqa: E402
    run_paper_trading_matching_for_active_accounts,
    run_unified_bfq_data_gap_recovery,
)
from stock.market import is_hk_market_open  # noqa: E402
from storage import get_storage  # noqa: E402

DEFAULT_START_DATE: Final = "2026-01-01"
# hk_daily_adj API 限制 2次/分钟，跨进程文件锁已将调用串行化，多分片无法提升吞吐，故固定为 1
PARTITION_COUNT = 1


def get_redis_client() -> redis.Redis:
    """Get Redis client for storing results."""
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return redis.Redis.from_url(redis_url, decode_responses=True)


def get_business_date(context: dict[str, Any]) -> date:
    return cast(date, context["logical_date"].in_timezone(LOCAL_TZ).date())


def ensure_hk_trade_date(context: dict[str, Any]) -> date:
    business_date = get_business_date(context)
    if not is_hk_market_open(business_date.isoformat()):
        raise AirflowSkipException(f"港股{business_date.isoformat()}休市，跳过任务")
    return business_date


def _persist_diagnostic(storage, business_date: date, stock_id: str, outcome) -> None:
    session = storage.Session()
    try:
        PaperTradingRepository(session).upsert_daily_bar_diagnostic(
            business_date,
            Market.HK_CONNECT,
            stock_id,
            canonical_adjust_label(AdjustType.BFQ),
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


def run_hk_matching_task(*, aggregate_task_id: str, **context):
    ti: Any = context.get("ti")
    assert ti is not None
    summary = ti.xcom_pull(task_ids=aggregate_task_id)
    if isinstance(summary, dict) and summary.get("result") != "success":
        raise AirflowSkipException("HK aggregate was not successful; skip matching")
    return run_paper_trading_matching_for_active_accounts(
        _aggregate_task_id=aggregate_task_id,
        _business_date=get_business_date(context),
        **context,
    )


def run_hk_recovery_task(*, aggregate_task_id: str, **context):
    ti: Any = context.get("ti")
    assert ti is not None
    summary = ti.xcom_pull(task_ids=aggregate_task_id)
    if isinstance(summary, dict) and summary.get("result") != "success":
        raise AirflowSkipException("HK aggregate was not successful; skip recovery")
    return run_unified_bfq_data_gap_recovery(
        _aggregate_task_id=aggregate_task_id,
        _business_date=get_business_date(context),
        **context,
    )


def download_hk_ggt_history_none_partition_task(*, partition_id: int, partition_count: int, **context):
    """Download HK GGT unadjusted history data for a specific partition.

    Args:
        partition_id: The 0-based partition identifier

    Returns:
        Success message with download statistics

    Raises:
        AirflowSkipException: If market is closed or partition is not active
        Exception: If download fails
    """

    business_date = ensure_hk_trade_date(context)

    if partition_id >= partition_count:
        raise AirflowSkipException(f"partition_id={partition_id} >= partition_count={partition_count}, skip")

    start_date = DEFAULT_START_DATE
    end_date = business_date.isoformat()

    df_stocks = get_storage().load_general_info_hk_ggt()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取港股通股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    manager = DownloadManager()

    storage = get_storage()
    authority_policy = None
    session_factory = getattr(storage, "Session", None)
    if session_factory is not None:
        session = cast(Callable[[], Any], session_factory)()
        authority_policy = HkRecoveryAuthorityPolicy(
            HkTradeCalendar(),
            HkConnectMetadataProvider(session),
            StorageMarketDataProvider(storage, HkTradeCalendar()),
        )
        session.close()

    outcomes: list[dict[str, Any]] = []

    def action(stock_id):
        authority_evidence = None
        if authority_policy is not None:
            try:
                authority_evidence = authority_policy.evaluate(stock_id, business_date)
            except Exception as exc:  # noqa: BLE001
                authority_evidence = {"decision": False, "state": "authority_unavailable", "error": str(exc)}
        if authority_evidence is not None and not authority_evidence.get("decision", False):
            from paper_trading.domain.market_data_diagnostics import ProviderOutcome, StockHistoryOutcome

            suspension = authority_evidence.get("suspension")
            state = authority_evidence.get("state") or (
                "ineligible"
                if not authority_evidence.get("ordinary_eligibility", False)
                else "suspended"
                if suspension == "suspended"
                else "authority_unavailable"
            )
            outcome = StockHistoryOutcome(
                stock_id,
                end_date,
                "bfq",
                state,
                (ProviderOutcome("hk_authority", "error", f"{state}: {json.dumps(authority_evidence)}"),),
                False,
            )
        else:
            outcome = manager.download_hk_ggt_history_outcome(
                stock_id=stock_id,
                period=PeriodType.DAILY,
                start_date=start_date,
                end_date=end_date,
                adjust=AdjustType.BFQ,
            )
        outcomes.append(asdict(outcome))
        if outcome.classification != "downloaded":
            _persist_diagnostic(get_storage(), business_date, stock_id, outcome)
        return outcome

    def on_progress(_stock_id, completed, total):
        if completed % 50 == 0 or completed == total:
            print(f"[HK NONE p{partition_id:02d}] 进度: {completed}/{total}")

    selected_ids = run_partition_items(
        stock_ids,
        partition_id,
        partition_count,
        action,
        lambda _outcome: False,
        on_progress=on_progress,
    )[0]

    return {"adjust": "bfq", "partition_id": partition_id, "count": len(selected_ids), "outcomes": outcomes}


def aggregate_and_save_result(*, partition_count: int, **context):
    """Aggregate all partition results and save to Redis."""

    # Collect results from XCom
    business_date = get_business_date(context)
    closed = not is_hk_market_open(business_date.isoformat())
    ti = context.get("ti")
    outcomes: list[dict[str, Any]] = []

    missing_symbols: list[str] = []
    for pid in range(partition_count):
        task_id = f"download_hk_ggt_history_none_p{pid:02d}"
        result = ti.xcom_pull(task_ids=task_id) if ti is not None else None
        if isinstance(result, dict) and isinstance(result.get("outcomes"), list):
            outcomes.extend(result.get("outcomes", []))
        elif not closed:
            missing_symbols.append(task_id)

    incomplete = [item for item in outcomes if item.get("classification") != "downloaded"]
    fatal = bool(missing_symbols) or any(item.get("classification") == "provider_error" for item in incomplete)
    status = "fatal" if fatal else ("warning" if incomplete else ("success" if outcomes else "skipped"))
    result = "fail" if fatal else ("success" if outcomes else "skipped")
    evidence = sorted(outcomes, key=lambda item: item.get("stock_id", ""))[:20]
    r = get_redis_client()
    summary = {
        "date": business_date.isoformat(),
        "result": "skipped" if closed else result,
        "status": "skipped" if closed else status,
        "missing_symbols": sorted(missing_symbols + [item["stock_id"] for item in incomplete if "stock_id" in item]),
        "provider_evidence": evidence,
    }
    r.set(
        REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY,
        json.dumps(summary, ensure_ascii=False),
        ex=86400,
    )
    if closed:
        return summary
    if missing_symbols:
        raise RuntimeError(f"missing or malformed partition outcome: {', '.join(missing_symbols)}")
    if fatal:
        raise RuntimeError("HK history aggregate was fatal")
    return summary


# Create DAG
dag = DAG(
    "download_hk_ggt_history_daily",
    default_args=get_default_args(),
    description="Weekdays HK GGT stock unadjusted daily history download",
    schedule="30 16 * * 1-5",
    catchup=False,
    max_active_runs=1,
)

# Create partition tasks
partition_tasks = [
    PythonOperator(
        task_id=f"download_hk_ggt_history_none_p{pid:02d}",
        python_callable=download_hk_ggt_history_none_partition_task,
        op_kwargs={"partition_id": pid, "partition_count": PARTITION_COUNT},
        dag=dag,
    )
    for pid in get_partition_ids(PARTITION_COUNT)
]

# Aggregate task runs after all partitions complete
aggregate_task = PythonOperator(
    task_id="aggregate_results",
    python_callable=aggregate_and_save_result,
    op_kwargs={"partition_count": PARTITION_COUNT},
    trigger_rule=TriggerRule.ALL_DONE,
    dag=dag,
)

matching_task = PythonOperator(
    task_id="run_hk_paper_trading_matching",
    python_callable=run_hk_matching_task,
    op_kwargs={"aggregate_task_id": "aggregate_results"},
    dag=dag,
)
recovery_task = PythonOperator(
    task_id="run_hk_bfq_data_gap_recovery",
    python_callable=run_hk_recovery_task,
    op_kwargs={"aggregate_task_id": "aggregate_results"},
    dag=dag,
)

# Set dependency: aggregate runs after all partition tasks complete
for task in partition_tasks:
    task >> aggregate_task
aggregate_task >> matching_task >> recovery_task
