"""DAG for monitoring stock conditions after daily market close."""

import json
import os
import sys
from datetime import datetime
from typing import Any

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common_dags import get_default_args  # noqa: E402

from common import is_a_market_open_today  # noqa: E402


def run_daily_monitor(**context):
    """Evaluate daily-frequency monitor targets after market close."""
    if not is_a_market_open_today():
        raise AirflowSkipException("非交易日，跳过每日监控任务")

    from monitor.monitor_runner import run_monitor

    summary = run_monitor(frequency="daily")
    msg = (
        f"每日监控完成: 共{summary.total}个目标, "
        f"触发{summary.triggered}个, 跳过{summary.skipped}个, 错误{summary.errors}个"
    )
    if summary.errors:
        raise Exception(f"{msg}\n错误详情: {summary.error_details}")
    return msg


def _format_logical_date(context: dict[str, Any]) -> str:
    logical_date = context.get("logical_date") or context.get("execution_date")
    if isinstance(logical_date, datetime):
        return logical_date.strftime("%Y%m%d")
    return datetime.now().strftime("%Y%m%d")


def _raise_if_failed(result: dict[str, Any], task_name: str) -> None:
    if result.get("success"):
        return
    code = result.get("code", "UNKNOWN")
    message = result.get("message", "")
    raise Exception(f"{task_name} failed: {code}: {message}")


def sync_shareholder_selling_blackroom(**context):
    """Sync shareholder-selling announcements into blackroom bans every scheduled day."""
    from monitor.shareholder_selling_punishment import (
        ShareholderSellingPunishmentService,
    )

    run_date = _format_logical_date(context)
    result = ShareholderSellingPunishmentService().sync(
        start_date=run_date,
        end_date=run_date,
        ban_days=180,
    )
    _raise_if_failed(result, "股东减持黑屋同步")

    data = result.get("data") or {}
    return (
        "股东减持黑屋同步完成: "
        f"date={run_date}, fetched={data.get('fetched', 0)}, "
        f"unique_stocks={data.get('unique_stocks', 0)}, "
        f"added={data.get('added', 0)}, skipped={data.get('skipped', 0)}"
    )


def countdown_blackroom_records(**context):
    """Update blackroom remaining-day countdown values."""
    from monitor.blackroom_countdown import BlackroomCountdownService

    result = BlackroomCountdownService().run()
    _raise_if_failed(result, "黑屋倒计时")
    return f"黑屋倒计时完成: {json.dumps(result.get('data'), ensure_ascii=False)}"


dag = DAG(
    "monitor_stock_daily",
    default_args=get_default_args(),
    description="每日收盘后检查股票监控条件",
    schedule="30 15 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["monitor"],
)

daily_monitor_task = PythonOperator(
    task_id="run_daily_monitor",
    python_callable=run_daily_monitor,
    dag=dag,
)

sync_shareholder_selling_task = PythonOperator(
    task_id="sync_shareholder_selling_blackroom",
    python_callable=sync_shareholder_selling_blackroom,
    dag=dag,
)

countdown_blackroom_task = PythonOperator(
    task_id="countdown_blackroom_records",
    python_callable=countdown_blackroom_records,
    trigger_rule="none_failed_min_one_success",
    dag=dag,
)

sync_shareholder_selling_task >> countdown_blackroom_task
daily_monitor_task >> countdown_blackroom_task
