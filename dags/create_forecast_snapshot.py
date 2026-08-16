"""Manually create an immutable forecast snapshot for an explicit date range."""

import os
import re
import sys
from datetime import date
from typing import Any

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import get_default_args  # noqa: E402, I001
from forecast_snapshot import ForecastSnapshotRequest  # noqa: E402
from forecast_snapshot import create_forecast_snapshot_service as ForecastSnapshotService  # noqa: E402


DATE_PARAMETERS = ("report_end_date", "announcement_start_date", "announcement_end_date")


def _parse_date(conf: dict[str, Any], parameter: str) -> date:
    value = conf.get(parameter)
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError(f"invalid or missing parameter: {parameter}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid parameter: {parameter}") from exc


def _default_request_from_context(context: dict[str, Any]) -> ForecastSnapshotRequest:
    logical_date = context.get("logical_date")
    year = getattr(logical_date, "year", None)
    if not isinstance(year, int):
        raise ValueError("invalid or missing parameter: logical_date")
    return ForecastSnapshotRequest(date(year - 1, 12, 31), date(year, 1, 1), date(year, 4, 30))


def _request_from_context(context: dict[str, Any]) -> ForecastSnapshotRequest:
    dag_run = context.get("dag_run")
    if dag_run is None:
        raise ValueError("missing parameter: dag_run")

    conf = getattr(dag_run, "conf", None)
    if conf is None:
        return _default_request_from_context(context)
    if not isinstance(conf, dict):
        raise ValueError("invalid parameter: dag_run.conf")

    supplied_parameters = {parameter for parameter in DATE_PARAMETERS if parameter in conf}
    if not supplied_parameters:
        return _default_request_from_context(context)
    if supplied_parameters != set(DATE_PARAMETERS):
        missing_parameter = next(parameter for parameter in DATE_PARAMETERS if parameter not in supplied_parameters)
        raise ValueError(f"invalid or missing parameter: {missing_parameter}")

    report_end_date = _parse_date(conf, "report_end_date")
    announcement_start_date = _parse_date(conf, "announcement_start_date")
    announcement_end_date = _parse_date(conf, "announcement_end_date")
    if announcement_end_date < announcement_start_date:
        raise ValueError("invalid parameter: announcement_end_date")
    return ForecastSnapshotRequest(report_end_date, announcement_start_date, announcement_end_date)


def create_forecast_snapshot(**context: Any) -> dict[str, int | str | None]:
    request = _request_from_context(context)
    summary = ForecastSnapshotService().create_snapshot(request)
    if summary.status == "completed":
        return summary.to_dict()
    raise RuntimeError(f"forecast snapshot failed: run_id={summary.run_id}; failure_detail={summary.failure_detail}")


dag = DAG(
    "create_forecast_snapshot",
    default_args=get_default_args(),
    description="手动创建指定公告日期范围的业绩预告快照",
    schedule=None,
    catchup=False,
    tags=["forecast", "manual"],
)

PythonOperator(
    task_id="create_forecast_snapshot",
    python_callable=create_forecast_snapshot,
    dag=dag,
)
