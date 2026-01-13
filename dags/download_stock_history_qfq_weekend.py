import os
import sys
from datetime import datetime, timedelta

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

# DAG 默认参数
default_args = {
    "owner": "frog",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email": ALERT_EMAILS,
    "email_on_failure": bool(ALERT_EMAILS),
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# 创建 DAG（周末 QFQ）
dag = DAG(
    "download_stock_history_qfq_weekend",
    default_args=default_args,
    description="Weekend stock history QFQ download",
    schedule="0 3 * * 0",  # 每周日凌晨3点执行
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


def reset_stock_history_qfq_table(**context):
    """清空A股QFQ历史数据表（周末全量重建）。"""
    # Import inside task to keep DAG parsing fast.
    from common.const import SecurityType
    from storage import get_storage, get_table_name

    table_name = get_table_name(SecurityType.STOCK, PeriodType.DAILY, AdjustType.QFQ)
    get_storage().drop_table(table_name)
    return f"cleared table: {table_name}"


def download_stock_history_qfq_partition_task(*, partition_id: int, **context):
    """周末下载A股QFQ历史数据（分片任务，最多16片）。"""
    # Import heavy modules inside the task to keep DAG parsing fast.
    from common.const import COL_STOCK_ID
    from download import DownloadManager
    from storage import get_storage

    partition_count = min(get_partition_count(), MAX_PARTITIONS)
    if partition_id >= partition_count:
        raise AirflowSkipException(
            f"partition_id={partition_id} >= partition_count={partition_count}, skip"
        )

    start_date = "2010-01-01"
    end_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

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
            adjust=AdjustType.QFQ,
        )
        if not ok:
            failed_ids.append(stock_id)

        if idx % 50 == 0 or idx == total:
            print(
                f"[QFQ p{partition_id:02d}] 进度: {idx}/{total} "
                f"(failed={len(failed_ids)})"
            )

    if failed_ids:
        preview = ",".join(failed_ids[:10])
        raise Exception(
            f"QFQ 分片下载失败: partition={partition_id}/{partition_count}, "
            f"failed={len(failed_ids)}/{total}, ids(sample)={preview}"
        )

    return (
        f"A股QFQ历史数据下载成功完成: partition={partition_id}/{partition_count}, "
        f"count={total}"
    )


task_reset_stock_history_qfq = PythonOperator(
    task_id="reset_stock_history_qfq",
    python_callable=reset_stock_history_qfq_table,
    dag=dag,
)

for _pid in range(MAX_PARTITIONS):
    task = PythonOperator(
        task_id=f"download_stock_history_qfq_p{_pid:02d}",
        python_callable=download_stock_history_qfq_partition_task,
        op_kwargs={"partition_id": _pid},
        dag=dag,
    )
    task_reset_stock_history_qfq >> task
