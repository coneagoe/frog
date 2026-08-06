import importlib
import json
import sys
import types
from datetime import date, datetime
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = ROOT / "dags"


class FakeAirflowSkipException(Exception):
    pass


class FakeDAG:
    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs


class FakePythonOperator:
    instances: ClassVar[list["FakePythonOperator"]] = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs
        self.task_id = kwargs.get("task_id")
        self.upstream: list[Any] = []
        self.downstream: list[Any] = []
        FakePythonOperator.instances.append(self)

    def __rshift__(self, other: Any) -> Any:
        self.downstream.append(other)
        other.upstream.append(self)
        return other


@pytest.fixture()
def post_close_module(monkeypatch):
    FakePythonOperator.instances = []
    monkeypatch.syspath_prepend(str(DAGS_DIR))
    monkeypatch.setenv("FROG_PROJECT_ROOT", str(ROOT))

    airflow_module = types.ModuleType("airflow")
    setattr(airflow_module, "DAG", FakeDAG)
    airflow_exceptions = types.ModuleType("airflow.exceptions")
    setattr(airflow_exceptions, "AirflowSkipException", FakeAirflowSkipException)
    airflow_operators = types.ModuleType("airflow.operators")
    airflow_python = types.ModuleType("airflow.operators.python")
    setattr(airflow_python, "PythonOperator", FakePythonOperator)

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.exceptions", airflow_exceptions)
    monkeypatch.setitem(sys.modules, "airflow.operators", airflow_operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", airflow_python)

    sys.modules.pop("forecast_ssf_ma20_post_close", None)
    module = importlib.import_module("forecast_ssf_ma20_post_close")
    yield module
    sys.modules.pop("forecast_ssf_ma20_post_close", None)


def test_post_close_dag_schedule_and_order(post_close_module):
    tasks = {task.task_id: task for task in FakePythonOperator.instances}

    assert post_close_module.dag.kwargs["schedule"] == "0 20 * * *"
    assert post_close_module.dag.kwargs["max_active_runs"] == 1
    assert post_close_module.dag.kwargs["catchup"] is False
    assert tasks["sync_forecast_ssf_targets"].upstream == [tasks["verify_daily_bar_completeness"]]
    assert tasks["run_forecast_ssf_daily_monitor"].upstream == [tasks["sync_forecast_ssf_targets"]]


def test_completeness_skips_non_trading_days(monkeypatch, post_close_module):
    monkeypatch.setattr(
        "monitor.daily_bar_completeness.verify_daily_bar_completeness",
        lambda as_of_date: {"trade_date": as_of_date.isoformat(), "status": "skipped"},
    )

    with pytest.raises(FakeAirflowSkipException):
        post_close_module.verify_daily_bar_completeness_task(logical_date=datetime(2026, 8, 8))


def test_completeness_failure_prevents_sync_construction(monkeypatch, post_close_module):
    monkeypatch.setattr(
        "monitor.daily_bar_completeness.verify_daily_bar_completeness",
        MagicMock(side_effect=RuntimeError("daily bars incomplete")),
    )
    service = MagicMock()
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(RuntimeError, match="daily bars incomplete"):
        post_close_module.verify_daily_bar_completeness_task(logical_date=datetime(2026, 8, 7))

    service.assert_not_called()


def test_monitor_returns_structured_summary_for_empty_success(monkeypatch, post_close_module):
    sync_result = {"success": True, "code": "OK", "message": "empty", "data": {"created": 0}}
    sync_service = MagicMock()
    sync_service.return_value.sync.return_value = sync_result
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", sync_service)
    monitor_summary = types.SimpleNamespace(total=0, triggered=0, skipped=0, errors=0, error_details=[])
    monitor = MagicMock(return_value=monitor_summary)
    monkeypatch.setattr("monitor.monitor_runner.run_monitor", monitor)

    sync_json = post_close_module.sync_forecast_ssf_targets(logical_date=datetime(2026, 8, 7))
    xcom_values = {
        "verify_daily_bar_completeness": json.dumps({"trade_date": "2026-08-07", "status": "success"}),
        "sync_forecast_ssf_targets": sync_json,
    }
    task_instance = MagicMock()
    task_instance.xcom_pull.side_effect = lambda task_ids: xcom_values[task_ids]
    context = {"ti": task_instance, "logical_date": datetime(2026, 8, 7)}
    result = post_close_module.run_forecast_ssf_daily_monitor(**context)

    assert json.loads(sync_json) == sync_result
    assert result == {
        "daily_bar": {"trade_date": "2026-08-07", "status": "success"},
        "synchronization": sync_result,
        "monitor": {"total": 0, "triggered": 0, "skipped": 0, "errors": 0, "error_details": []},
    }
    monitor.assert_called_once_with(frequency="daily", workflow="forecast_ssf_ma20")


def test_monitor_raises_on_monitor_errors(monkeypatch, post_close_module):
    monkeypatch.setattr(
        "monitor.monitor_runner.run_monitor",
        lambda **kwargs: types.SimpleNamespace(total=1, triggered=0, skipped=0, errors=1, error_details=["boom"]),
    )
    xcom_pull = MagicMock(return_value=json.dumps({"success": True}))
    context = {"ti": MagicMock(xcom_pull=xcom_pull), "logical_date": date(2026, 8, 7)}

    with pytest.raises(Exception, match="boom"):
        post_close_module.run_forecast_ssf_daily_monitor(**context)
