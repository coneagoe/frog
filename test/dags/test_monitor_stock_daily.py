import importlib
import sys
import types
from datetime import datetime
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
        self.downstream: list[Any] = []
        FakePythonOperator.instances.append(self)

    def __rshift__(self, other: Any) -> Any:
        self.downstream.append(other)
        return other


@pytest.fixture()
def monitor_stock_daily_module(monkeypatch):
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

    sys.modules.pop("monitor_stock_daily", None)
    module = importlib.import_module("monitor_stock_daily")
    yield module
    sys.modules.pop("monitor_stock_daily", None)


def test_sync_shareholder_selling_blackroom_uses_logical_date(monkeypatch, monitor_stock_daily_module):
    service = MagicMock()
    service.return_value.sync.return_value = {
        "success": True,
        "code": "OK",
        "message": "sync completed",
        "data": {"added": 2, "skipped": 1},
    }
    monkeypatch.setattr(
        "monitor.shareholder_selling_punishment.ShareholderSellingPunishmentService",
        service,
    )

    result = monitor_stock_daily_module.sync_shareholder_selling_blackroom(logical_date=datetime(2026, 6, 3, 15, 30))

    service.return_value.sync.assert_called_once_with(start_date="20260603", end_date="20260603", ban_days=180)
    assert "股东减持黑屋同步完成" in result
    assert "added=2" in result


def test_sync_shareholder_selling_blackroom_failure_raises(monkeypatch, monitor_stock_daily_module):
    service = MagicMock()
    service.return_value.sync.return_value = {
        "success": False,
        "code": "STORAGE_ERROR",
        "message": "boom",
        "data": None,
    }
    monkeypatch.setattr(
        "monitor.shareholder_selling_punishment.ShareholderSellingPunishmentService",
        service,
    )

    with pytest.raises(Exception, match="STORAGE_ERROR: boom"):
        monitor_stock_daily_module.sync_shareholder_selling_blackroom(logical_date=datetime(2026, 6, 3, 15, 30))


def test_countdown_blackroom_records_calls_service(monkeypatch, monitor_stock_daily_module):
    service = MagicMock()
    service.return_value.run.return_value = {
        "success": True,
        "code": "OK",
        "message": "countdown completed",
        "data": {"updated": 3},
    }
    monkeypatch.setattr("monitor.blackroom_countdown.BlackroomCountdownService", service)

    result = monitor_stock_daily_module.countdown_blackroom_records()

    service.return_value.run.assert_called_once_with()
    assert "黑屋倒计时完成" in result
    assert "updated" in result


def test_countdown_blackroom_records_failure_raises(monkeypatch, monitor_stock_daily_module):
    service = MagicMock()
    service.return_value.run.return_value = {
        "success": False,
        "code": "STORAGE_ERROR",
        "message": "boom",
        "data": None,
    }
    monkeypatch.setattr("monitor.blackroom_countdown.BlackroomCountdownService", service)

    with pytest.raises(Exception, match="STORAGE_ERROR: boom"):
        monitor_stock_daily_module.countdown_blackroom_records()


def test_shareholder_sync_is_not_downstream_of_daily_monitor():
    source = (DAGS_DIR / "monitor_stock_daily.py").read_text(encoding="utf-8")

    assert "daily_monitor_task >> sync_shareholder_selling_task" not in source
    assert "sync_shareholder_selling_task >> countdown_blackroom_task" in source
    assert "daily_monitor_task >> countdown_blackroom_task" in source


def test_dag_runs_every_calendar_day(monitor_stock_daily_module):
    assert monitor_stock_daily_module.dag.kwargs["schedule"] == "30 15 * * *"
