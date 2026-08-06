"""Post-close orchestration for the forecast SSF MA20 monitor workflow."""

import json
import os
import sys
from datetime import date, datetime
from typing import Any

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import get_default_args  # noqa: E402, I001


def _as_of_date(context: dict[str, Any]) -> date:
    logical_date = context.get("logical_date") or context.get("execution_date")
    if isinstance(logical_date, datetime):
        return logical_date.date()
    if isinstance(logical_date, date):
        return logical_date
    return datetime.now().date()


def verify_daily_bar_completeness_task(**context: Any) -> str:
    """Verify daily bars and skip the workflow on non-trading days."""
    from monitor.daily_bar_completeness import verify_daily_bar_completeness

    result = verify_daily_bar_completeness(as_of_date=_as_of_date(context))
    if result.get("status") == "skipped":
        raise AirflowSkipException("非交易日，跳过业绩预增社保基金收盘后工作流")
    return json.dumps(result, ensure_ascii=False)


def sync_forecast_ssf_targets(**context: Any) -> str:
    """Synchronize workflow targets after daily-bar completeness succeeds."""
    from monitor.forecast_ssf_monitor_sync import ForecastSSFMonitorSyncService

    result = ForecastSSFMonitorSyncService().sync(as_of_date=_as_of_date(context))
    if not result.get("success"):
        raise RuntimeError(
            f"forecast SSF target synchronization failed: {result.get('code', 'UNKNOWN')}: "
            f"{result.get('message', '')}"
        )
    return json.dumps(result, ensure_ascii=False)


def run_forecast_ssf_daily_monitor(**context: Any) -> dict[str, Any]:
    """Run the workflow monitor and return all stage summaries."""
    task_instance = context["ti"]
    daily_bar = json.loads(task_instance.xcom_pull(task_ids="verify_daily_bar_completeness"))
    synchronization = json.loads(task_instance.xcom_pull(task_ids="sync_forecast_ssf_targets"))

    from monitor.monitor_runner import run_monitor

    summary = run_monitor(frequency="daily", workflow="forecast_ssf_ma20")
    monitor = {
        "total": summary.total,
        "triggered": summary.triggered,
        "skipped": summary.skipped,
        "errors": summary.errors,
        "error_details": summary.error_details,
    }
    if summary.errors:
        raise RuntimeError(f"forecast SSF daily monitor failed: {summary.error_details}")
    return {"daily_bar": daily_bar, "synchronization": synchronization, "monitor": monitor}


dag = DAG(
    "forecast_ssf_ma20_post_close",
    default_args=get_default_args(),
    description="收盘后编排业绩预增社保基金 MA20 监控工作流",
    schedule="0 20 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["forecast_ssf_ma20"],
)

verify_daily_bar_completeness_operator = PythonOperator(
    task_id="verify_daily_bar_completeness",
    python_callable=verify_daily_bar_completeness_task,
    dag=dag,
)

sync_forecast_ssf_targets_operator = PythonOperator(
    task_id="sync_forecast_ssf_targets",
    python_callable=sync_forecast_ssf_targets,
    dag=dag,
)

run_forecast_ssf_daily_monitor_operator = PythonOperator(
    task_id="run_forecast_ssf_daily_monitor",
    python_callable=run_forecast_ssf_daily_monitor,
    dag=dag,
)

verify_daily_bar_completeness_operator >> sync_forecast_ssf_targets_operator >> run_forecast_ssf_daily_monitor_operator
