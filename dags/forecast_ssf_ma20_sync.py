"""15:05 synchronization for forecast SSF MA20 monitor targets."""

import json
import os
import sys
from datetime import date, datetime
from typing import Any, cast

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from airflow.sdk.exceptions import AirflowSkipException

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import LOCAL_TZ, get_default_args  # noqa: E402, I001
from stock.market import is_a_share_trade_date  # noqa: E402


def _as_of_date(context: dict[str, Any]) -> date:
    data_interval_end = context.get("data_interval_end")
    if data_interval_end is not None:
        return cast(date, data_interval_end.in_timezone(LOCAL_TZ).date())

    logical_date = context.get("logical_date") or context.get("execution_date")
    if isinstance(logical_date, datetime):
        return logical_date.date()
    if isinstance(logical_date, date):
        return logical_date
    return datetime.now().date()


def sync_forecast_ssf_targets(**context: Any) -> str:
    """Synchronize forecast SSF targets on A-share trading days."""
    as_of_date = _as_of_date(context)
    if not is_a_share_trade_date(as_of_date):
        raise AirflowSkipException(f"A股{as_of_date.isoformat()}休市，跳过任务")

    from monitor.forecast_ssf_monitor_sync import ForecastSSFMonitorSyncService

    result = ForecastSSFMonitorSyncService().sync(as_of_date=as_of_date)
    if not result.get("success"):
        raise RuntimeError(
            f"forecast SSF target synchronization failed: {result.get('code', 'UNKNOWN')}: {result.get('message', '')}"
        )
    return json.dumps(result, ensure_ascii=False)


dag = DAG(
    "forecast_ssf_ma20_sync",
    default_args=get_default_args(),
    description="15:05同步业绩预增社保基金 MA20 监控目标",
    schedule="5 15 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["forecast_ssf_ma20"],
)

sync_forecast_ssf_targets_operator = PythonOperator(
    task_id="sync_forecast_ssf_targets",
    python_callable=sync_forecast_ssf_targets,
    dag=dag,
)
