import importlib
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = ROOT / "dags"


class FakeAirflowDateTime(datetime):
    def in_timezone(self, tz):
        return self.astimezone(tz)


def monday_sync_context() -> dict[str, Any]:
    return {
        "data_interval_end": FakeAirflowDateTime(2026, 8, 10, 7, 5, tzinfo=timezone.utc),
        "logical_date": FakeAirflowDateTime(2026, 8, 9, 7, 5, tzinfo=timezone.utc),
    }


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
        FakePythonOperator.instances.append(self)


@pytest.fixture()
def sync_module(monkeypatch):
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

    sys.modules.pop("forecast_ssf_ma20_sync", None)
    module = importlib.import_module("forecast_ssf_ma20_sync")
    yield module
    sys.modules.pop("forecast_ssf_ma20_sync", None)


def test_sync_dag_schedule_and_single_task(sync_module):
    tasks = {task.task_id: task for task in FakePythonOperator.instances}

    assert sync_module.dag.kwargs["schedule"] == "5 15 * * *"
    assert sync_module.dag.kwargs["max_active_runs"] == 1
    assert set(tasks) == {"sync_forecast_ssf_targets"}


def test_sync_task_skips_non_trading_day(monkeypatch, sync_module):
    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: False)
    service = MagicMock()
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(FakeAirflowSkipException):
        sync_module.sync_forecast_ssf_targets(**monday_sync_context())

    service.assert_not_called()


def test_sync_task_uses_interval_end_local_date_and_returns_json(monkeypatch, sync_module):
    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: True)
    service = MagicMock()
    service.return_value.sync.return_value = {"success": True, "data": {"created": 1}}
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    result = sync_module.sync_forecast_ssf_targets(**monday_sync_context())

    service.return_value.sync.assert_called_once_with(as_of_date=datetime(2026, 8, 10).date())
    assert json.loads(result) == {"success": True, "data": {"created": 1}}


def test_sync_task_falls_back_to_logical_date_without_interval_end(monkeypatch, sync_module):
    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: True)
    service = MagicMock()
    service.return_value.sync.return_value = {"success": True}
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    sync_module.sync_forecast_ssf_targets(logical_date=datetime(2026, 8, 7, 15, 5))

    service.return_value.sync.assert_called_once_with(as_of_date=datetime(2026, 8, 7).date())


def test_sync_task_raises_when_service_fails(monkeypatch, sync_module):
    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: True)
    service = MagicMock()
    service.return_value.sync.return_value = {
        "success": False,
        "code": "STORAGE_ERROR",
        "message": "boom",
    }
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(RuntimeError, match="STORAGE_ERROR: boom"):
        sync_module.sync_forecast_ssf_targets(**monday_sync_context())


def test_sync_task_propagates_no_eligible_snapshot_failure(monkeypatch, sync_module):
    from monitor.forecast_ssf_monitor_sync import NoEligibleForecastSnapshotError

    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: True)
    service = MagicMock()
    service.return_value.sync.side_effect = NoEligibleForecastSnapshotError("no completed forecast snapshot eligible")
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(NoEligibleForecastSnapshotError, match="no completed forecast snapshot eligible"):
        sync_module.sync_forecast_ssf_targets(**monday_sync_context())


def test_sync_task_propagates_partial_failure(monkeypatch, sync_module):
    from monitor.forecast_ssf_monitor_sync import ForecastSSFMonitorSyncPartialFailure

    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: True)
    service = MagicMock()
    service.return_value.sync.side_effect = ForecastSSFMonitorSyncPartialFailure({"errors": [{"stock_code": "600001"}]})
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(ForecastSSFMonitorSyncPartialFailure):
        sync_module.sync_forecast_ssf_targets(**monday_sync_context())
