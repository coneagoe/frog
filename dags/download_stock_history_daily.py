# ruff: noqa: I001
"""DAG for downloading stock history (HFQ) on weekdays."""

import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from typing import Any, Callable, cast

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
from paper_trading.services.data_gap_alert_service import DataGapAlertService  # noqa: E402
from paper_trading.services.ledger_rebuild_service import LedgerRebuildService  # noqa: E402
from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationService  # noqa: E402
from paper_trading.storage.data_gap_recovery_repository import DataGapRecoveryRepository  # noqa: E402
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider  # noqa: E402
from paper_trading.storage.market_data import StorageMarketDataProvider  # noqa: E402
from paper_trading.api.deps import _DataAvailableCalendar  # noqa: E402
from paper_trading.storage.repository import PaperTradingRepository  # noqa: E402
from stock.market import is_a_share_trade_date  # noqa: E402
from storage import get_storage  # noqa: E402
from tools.paper_trading_cli import run_paper_trading_ledger_rebuild  # noqa: E402
from tools.paper_trading_cli import run_paper_trading_matching  # noqa: E402, I001

logger = logging.getLogger(__name__)


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
        approved_candidates = repository.list_pending_approved_candidates()
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
            cutoff=datetime.combine(business_date, time.max, tzinfo=timezone.utc),
        )
        session.commit()
        batch_id = batch.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    recovery_repository = _FreshSessionRecoveryRepository(storage)
    for approved_gap, approved_hash, _payload in approved_candidates:
        DataGapRecoveryService(repository=recovery_repository).execute_approved_gap(
            _detach_gap(approved_gap), approved_hash
        )
    alert_service = DataGapAlertService(repository=recovery_repository)
    results: list[Any] = []
    try:
        results = DataGapRecoveryService(
            repository=recovery_repository, alert_service=alert_service
        ).recover_unresolved_ordinary_gaps(gaps, batch_id=batch_id)
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
    recovery = {
        "date": business_date.isoformat(),
        "gap_count": len(results),
        "results": [asdict(item) for item in results],
    }
    successful_gap_ids = {item.gap_id for item in results if item.status in {"recovered", "skipped"}}
    recovery_work = [
        item
        for item in recovery_repository.list_batch_account_recovery(batch_id)
        if item["gap_id"] in successful_gap_ids
    ]
    retry_work = recovery_repository.list_retryable_recovery_work(
        datetime.combine(business_date, time.max, tzinfo=timezone.utc)
    )
    recovery_work.extend(item for item in retry_work if item not in recovery_work)
    recovery.update(
        run_paper_trading_account_recovery(
            affected_account_ids=sorted({item["account_id"] for item in recovery_work}),
            start_date=business_date,
            end_date=business_date,
            recovery_work=recovery_work,
            storage=storage,
            alert_service=alert_service,
        )
    )
    return recovery


def run_paper_trading_account_recovery(
    *,
    affected_account_ids: list[int],
    start_date: date,
    end_date: date,
    rebuild_account: Any | None = None,
    recalculate_snapshots: Any | None = None,
    recovery_work: list[dict[str, Any]] | None = None,
    storage: Any | None = None,
    alert_service: Any | None = None,
) -> dict[str, Any]:
    """Recover affected accounts independently, preserving completed steps on retry.

    The injectable ``rebuild_account(...)`` and ``recalculate_snapshots(...)``
    callbacks are retained for unit-level orchestration tests; production uses
    the concrete services wired below.
    """
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    if not affected_account_ids:
        return {"recovered_account_ids": [], "failed_account_ids": []}
    ledger_runner: Callable[[int, date], Any]
    snapshot_runner: Callable[[int, date, date], Any]
    if rebuild_account is None or recalculate_snapshots is None:
        if storage is None:
            storage = get_storage()
        assert storage.Session is not None
        session_factory = storage.Session

        def runtime_rebuild(account_id: int, account_start: date) -> Any:
            session = session_factory()
            try:
                repo = PaperTradingRepository(session)
                result = LedgerRebuildService(
                    repo,
                    StorageMarketDataProvider(storage, _DataAvailableCalendar()),
                    HkConnectMetadataProvider(session),
                ).rebuild_account_from(account_id, account_start, trigger_evidence={"source": "data_gap_recovery"})
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        def runtime_recalculate(account_id: int, account_start: date, account_end: date) -> Any:
            return SnapshotRecalculationService(
                session_factory,
                StorageMarketDataProvider(storage, _DataAvailableCalendar()),
            ).recalculate(account_id, account_start, account_end)

        ledger_runner = runtime_rebuild
        snapshot_runner = runtime_recalculate
    else:
        ledger_runner = rebuild_account
        snapshot_runner = recalculate_snapshots

    recovered: list[int] = []
    failed: list[int] = []
    errors: dict[int, str] = {}
    work_by_account: dict[int, list[dict[str, Any]]] = {}
    for item in recovery_work or []:
        work_by_account.setdefault(item["account_id"], []).append(item)
    for account_id in affected_account_ids:
        account_work = work_by_account.get(account_id)
        account_start = min((item["start_date"] for item in account_work or []), default=start_date)
        account_end = max((item["end_date"] for item in account_work or []), default=end_date)
        pending_ledger = list(account_work or [])
        pending_snapshot = list(account_work or [])
        ledger_committed = False
        ledger_persisted = False
        try:
            pending_ledger = [item for item in pending_ledger if item.get("gap_id") is not None]
            pending_snapshot = list(pending_ledger)
            if storage is not None and pending_ledger:
                progress_session = storage.Session()
                try:
                    progress_repo = DataGapRecoveryRepository(progress_session)

                    def needs_step(item: dict[str, Any], step: str) -> bool:
                        progress = progress_repo.get_account_progress(item["gap_id"], account_id)
                        return progress is None or progress.summary.get(step, {}).get("status") not in {
                            "completed",
                            "recovered",
                        }

                    pending_ledger = [item for item in pending_ledger if needs_step(item, "ledger")]
                    pending_snapshot = [item for item in pending_snapshot if needs_step(item, "snapshot")]
                finally:
                    progress_session.close()
            if pending_ledger:
                ledger_runner(account_id, account_start)
                ledger_committed = True
                _persist_account_steps(
                    storage,
                    pending_ledger,
                    account_id,
                    "ledger",
                    "completed",
                    {"start_date": account_start.isoformat()},
                )
                ledger_persisted = True
            if pending_snapshot:
                snapshot_runner(account_id, account_start, account_end)
                _persist_account_steps(
                    storage,
                    pending_snapshot,
                    account_id,
                    "snapshot",
                    "completed",
                    {"end_date": account_end.isoformat()},
                )
        except Exception as exc:  # noqa: BLE001
            failed.append(account_id)
            errors[account_id] = str(exc)
            if storage is not None and not (ledger_committed and not ledger_persisted):
                try:
                    _persist_account_steps(
                        storage,
                        account_work or [],
                        account_id,
                        "snapshot" if ledger_committed else "ledger",
                        "failed",
                        {"error": str(exc), "ledger_committed": ledger_committed},
                    )
                except Exception as persist_exc:  # noqa: BLE001
                    errors[account_id] = f"{exc}; progress persistence failed: {persist_exc}"
            if alert_service is not None:
                for item in account_work or []:
                    try:
                        gap = alert_service.repository.get_gap(item["gap_id"])
                        if gap is not None:
                            alert_service.send_account_recovery_failure(
                                gap, account_id=account_id, failure_class=type(exc).__name__.lower()
                            )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Data-gap account alert failed: gap_id=%s account_id=%s", item["gap_id"], account_id
                        )
            continue
        recovered.append(account_id)
    result: dict[str, Any] = {"recovered_account_ids": recovered, "failed_account_ids": failed}
    if errors:
        result["errors"] = errors
    return result


def _persist_account_steps(
    storage: Any, work: list[dict[str, Any]], account_id: int, step: str, status: str, evidence: dict[str, Any]
) -> None:
    if storage is None:
        return
    session = storage.Session()
    try:
        repository = DataGapRecoveryRepository(session)
        for item in work:
            repository.record_account_recovery_step(item["gap_id"], account_id, step, status, evidence)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _detach_gap(gap: Any) -> Any:
    """Detach recovery fields needed after the metadata session is closed."""
    return SimpleNamespace(
        id=gap.id,
        business_date=gap.business_date,
        stock_id=gap.stock_id,
        market=gap.market,
        adjust=gap.adjust,
        summary=dict(getattr(gap, "summary", {}) or {}),
        status=getattr(gap, "status", None),
        latest_candidate_hash=getattr(gap, "latest_candidate_hash", None),
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

    def record_candidate(self, *args: Any) -> Any:
        return self._call(lambda repository: repository.record_candidate(*args))

    def get_gap(self, gap_id: int, owner_user_id: int | None = None) -> Any:
        return self._call(lambda repository: repository.get_gap(gap_id, owner_user_id))

    def gap_evidence(self, gap_id: int, owner_user_id: int | None = None) -> dict[str, Any]:
        result = self._call(lambda repository: repository.gap_evidence(gap_id, owner_user_id))
        return cast(dict[str, Any], result)

    def escalate_gap(
        self,
        gap_id: int,
        user_id: int,
        user_snapshot: dict[str, Any],
        reason: str | None = None,
    ) -> Any:
        return self._call(lambda repository: repository.escalate_gap(gap_id, user_id, user_snapshot, reason=reason))

    def claim_alert(self, gap_id: int, cycle_key: str, evidence: dict[str, Any]) -> Any:
        return self._call(lambda repository: repository.claim_alert(gap_id, cycle_key, evidence))

    def update_alert_delivery(self, alert_id: int, state: Any, metadata: dict[str, Any]) -> Any:
        return self._call(lambda repository: repository.update_alert_delivery(alert_id, state, metadata))

    def resolve_gap(self, gap_id: int) -> None:
        self._call(lambda repository: repository.resolve_gap(gap_id))

    def execute_approved_candidate(self, gap_id: int, candidate_hash: str, callback: Callable[..., Any]) -> Any:
        return self._call(lambda repository: repository.execute_approved_candidate(gap_id, candidate_hash, callback))

    def finalize_batch(self, *args: Any, **kwargs: Any) -> Any:
        return self._call(lambda repository: repository.finalize_batch(*args, **kwargs))

    def list_batch_account_recovery(self, batch_id: int) -> list[dict[str, Any]]:
        result = self._call(lambda repository: repository.list_batch_account_recovery(batch_id))
        return cast(list[dict[str, Any]], result)

    def list_retryable_recovery_work(self, cutoff: datetime | None = None) -> list[dict[str, Any]]:
        result = self._call(lambda repository: repository.list_retryable_recovery_work(cutoff))
        return cast(list[dict[str, Any]], result)


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
