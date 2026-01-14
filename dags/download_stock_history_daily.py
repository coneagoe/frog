import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

# Ensure project root is on sys.path (Airflow container mounts code at /opt/airflow/frog)
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.const import AdjustType, PeriodType  # noqa: E402


def _parse_alert_emails(raw: str) -> list[str]:
    return [
        email.strip() for email in raw.replace(";", ",").split(",") if email.strip()
    ]


ALERT_EMAILS = _parse_alert_emails(
    os.environ.get("ALERT_EMAILS") or os.environ.get("MAIL_RECEIVERS") or ""
)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# DAG 默认参数
default_args = {
    "owner": "frog",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1, tzinfo=LOCAL_TZ),
    "email": ALERT_EMAILS,
    "email_on_failure": bool(ALERT_EMAILS),
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "download_stock_history_hfq_weekdays",
    default_args=default_args,
    description="Weekdays stock history HFQ download",
    schedule="0 16 * * 1-5",  # 每个工作日下午4点执行
    catchup=False,
    max_active_runs=1,
)


MAX_PARTITIONS = 16
_DEFAULT_PARTITION_COUNT = 4


def get_partition_count() -> int:
    """Partition count for Airflow tasks.

    Priority:
    1) Env var DOWNLOAD_PROCESS_COUNT
    2) Airflow Variable DOWNLOAD_PROCESS_COUNT (read at runtime)
    3) Default (4)
    """

    def _parse_int(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    env_value = os.getenv("DOWNLOAD_PROCESS_COUNT")
    parsed = _parse_int(env_value)
    if parsed is not None:
        return max(1, parsed)

    try:
        from airflow.models import Variable

        var_value = Variable.get("DOWNLOAD_PROCESS_COUNT", default_var=None)
    except Exception:
        var_value = None

    parsed = _parse_int(var_value)
    if parsed is not None:
        return max(1, parsed)

    return _DEFAULT_PARTITION_COUNT


def download_stock_history_hfq_partition_task(*, partition_id: int, **context):
    """工作日下载A股HFQ历史数据（分片任务，最多16片）。"""
    # Import heavy modules inside the task to keep DAG parsing fast.
    from common import is_a_market_open_today
    from common.const import COL_STOCK_ID
    from download import DownloadManager
    from storage import get_storage

    if not is_a_market_open_today():
        raise AirflowSkipException("A股市场今日休市，跳过下载任务")

    partition_count = min(get_partition_count(), MAX_PARTITIONS)
    if partition_id >= partition_count:
        raise AirflowSkipException(
            f"partition_id={partition_id} >= partition_count={partition_count}, skip"
        )

    start_date = "2010-01-01"
    end_date = datetime.now(tz=LOCAL_TZ).date().isoformat()

    df_stocks = get_storage().load_general_info_stock()
    if df_stocks is None or df_stocks.empty:
        raise Exception("无法获取股票基本信息数据")

    stock_ids = df_stocks[COL_STOCK_ID].tolist()
    my_ids = [
        sid
        for idx, sid in enumerate(stock_ids)
        if (idx % partition_count) == partition_id
    ]

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
            print(
                f"[HFQ p{partition_id:02d}] 进度: {idx}/{total} "
                f"(failed={len(failed_ids)})"
            )

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"HFQ 分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return (
        f"A股HFQ历史数据下载成功完成: partition={partition_id}/{partition_count}, "
        f"count={total}"
    )


for _pid in range(MAX_PARTITIONS):
    PythonOperator(
        task_id=f"download_stock_history_hfq_p{_pid:02d}",
        python_callable=download_stock_history_hfq_partition_task,
        op_kwargs={"partition_id": _pid},
        dag=dag,
    )
