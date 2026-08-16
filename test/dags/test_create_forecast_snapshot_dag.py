import importlib
import sys
import types
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

from forecast_snapshot import ForecastSnapshotSummary

ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = ROOT / "dags"


class FakeDAG:
    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs


class FakePythonOperator:
    instances: ClassVar[list["FakePythonOperator"]] = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs
        self.task_id = kwargs["task_id"]
        FakePythonOperator.instances.append(self)


@pytest.fixture()
def snapshot_module(monkeypatch):
    FakePythonOperator.instances = []
    monkeypatch.syspath_prepend(str(DAGS_DIR))
    monkeypatch.setenv("FROG_PROJECT_ROOT", str(ROOT))

    airflow_module = types.ModuleType("airflow")
    airflow_module.__path__ = []
    airflow_sdk = types.ModuleType("airflow.sdk")
    airflow_sdk.__dict__["DAG"] = FakeDAG
    airflow_providers = types.ModuleType("airflow.providers")
    airflow_providers.__path__ = []
    airflow_standard = types.ModuleType("airflow.providers.standard")
    airflow_standard.__path__ = []
    airflow_operators = types.ModuleType("airflow.providers.standard.operators")
    airflow_operators.__path__ = []
    airflow_python = types.ModuleType("airflow.providers.standard.operators.python")
    airflow_python.__dict__["PythonOperator"] = FakePythonOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.sdk", airflow_sdk)
    monkeypatch.setitem(sys.modules, "airflow.providers", airflow_providers)
    monkeypatch.setitem(sys.modules, "airflow.providers.standard", airflow_standard)
    monkeypatch.setitem(sys.modules, "airflow.providers.standard.operators", airflow_operators)
    monkeypatch.setitem(sys.modules, "airflow.providers.standard.operators.python", airflow_python)

    sys.modules.pop("create_forecast_snapshot", None)
    module = importlib.import_module("create_forecast_snapshot")
    yield module
    sys.modules.pop("create_forecast_snapshot", None)


def valid_context() -> dict[str, Any]:
    return {
        "logical_date": datetime(2026, 7, 3, 6, 0),
        "dag_run": SimpleNamespace(
            conf={
                "report_end_date": "2026-06-30",
                "announcement_start_date": "2026-07-01",
                "announcement_end_date": "2026-07-02",
            }
        ),
    }


def test_snapshot_dag_is_manual_and_has_one_task(snapshot_module):
    assert snapshot_module.dag.kwargs["schedule"] is None
    assert snapshot_module.dag.kwargs["catchup"] is False
    assert set(task.task_id for task in FakePythonOperator.instances) == {"create_forecast_snapshot"}


def test_snapshot_callable_builds_parsed_request_and_returns_completed_summary(monkeypatch, snapshot_module):
    summary = ForecastSnapshotSummary(7, 1, "completed", 2, 2, 3, 3, 0, 0, None)
    service = MagicMock()
    service.create_snapshot.return_value = summary
    monkeypatch.setattr(snapshot_module, "ForecastSnapshotService", lambda: service)

    result = snapshot_module.create_forecast_snapshot(**valid_context())

    assert result == summary.to_dict()
    assert service.create_snapshot.call_args.args[0] == snapshot_module.ForecastSnapshotRequest(
        date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)
    )


@pytest.mark.parametrize("conf", ({}, None))
def test_snapshot_callable_defaults_empty_configuration_to_recent_annual_window(monkeypatch, snapshot_module, conf):
    summary = ForecastSnapshotSummary(7, 1, "completed", 120, 120, 3, 3, 0, 0, None)
    service = MagicMock()
    service.create_snapshot.return_value = summary
    monkeypatch.setattr(snapshot_module, "ForecastSnapshotService", lambda: service)

    result = snapshot_module.create_forecast_snapshot(
        logical_date=datetime(2026, 8, 16, 12, 30), dag_run=SimpleNamespace(conf=conf)
    )

    assert result == summary.to_dict()
    assert service.create_snapshot.call_args.args[0] == snapshot_module.ForecastSnapshotRequest(
        date(2025, 12, 31), date(2026, 1, 1), date(2026, 4, 30)
    )


def test_snapshot_callable_defaults_missing_configuration_to_recent_annual_window(monkeypatch, snapshot_module):
    summary = ForecastSnapshotSummary(7, 1, "completed", 120, 120, 3, 3, 0, 0, None)
    service = MagicMock()
    service.create_snapshot.return_value = summary
    monkeypatch.setattr(snapshot_module, "ForecastSnapshotService", lambda: service)

    snapshot_module.create_forecast_snapshot(logical_date=date(2026, 8, 16), dag_run=SimpleNamespace())

    assert service.create_snapshot.call_args.args[0] == snapshot_module.ForecastSnapshotRequest(
        date(2025, 12, 31), date(2026, 1, 1), date(2026, 4, 30)
    )


@pytest.mark.parametrize(
    ("context", "parameter"),
    [
        ({}, "dag_run"),
        *(
            (
                {
                    "logical_date": valid_context()["logical_date"],
                    "dag_run": SimpleNamespace(
                        conf={key: value for key, value in valid_context()["dag_run"].conf.items() if key != parameter}
                    ),
                },
                parameter,
            )
            for parameter in ("report_end_date", "announcement_start_date", "announcement_end_date")
        ),
        *(
            (
                {
                    "logical_date": valid_context()["logical_date"],
                    "dag_run": SimpleNamespace(
                        conf={
                            **valid_context()["dag_run"].conf,
                            parameter: value,
                        }
                    ),
                },
                parameter,
            )
            for parameter in ("report_end_date", "announcement_start_date", "announcement_end_date")
            for value in (None, 20260701)
        ),
        (
            {
                "logical_date": valid_context()["logical_date"],
                "dag_run": SimpleNamespace(
                    conf={
                        "report_end_date": "20260630",
                        "announcement_start_date": "2026-07-01",
                        "announcement_end_date": "2026-07-02",
                    }
                ),
            },
            "report_end_date",
        ),
        (
            {
                "logical_date": valid_context()["logical_date"],
                "dag_run": SimpleNamespace(
                    conf={
                        "report_end_date": "2026-06-30",
                        "announcement_start_date": "2026-07-02",
                        "announcement_end_date": "2026-07-01",
                    }
                ),
            },
            "announcement_end_date",
        ),
    ],
)
def test_snapshot_callable_rejects_invalid_configuration_before_constructing_service(
    monkeypatch, snapshot_module, context, parameter
):
    service_factory = MagicMock()
    monkeypatch.setattr(snapshot_module, "ForecastSnapshotService", service_factory)

    with pytest.raises(ValueError, match=parameter):
        snapshot_module.create_forecast_snapshot(**context)

    service_factory.assert_not_called()


def test_snapshot_callable_rejects_empty_configuration_without_logical_date(monkeypatch, snapshot_module):
    service_factory = MagicMock()
    monkeypatch.setattr(snapshot_module, "ForecastSnapshotService", service_factory)

    with pytest.raises(ValueError, match="logical_date"):
        snapshot_module.create_forecast_snapshot(dag_run=SimpleNamespace(conf={}))

    service_factory.assert_not_called()


def test_snapshot_callable_raises_persisted_failed_summary_detail(monkeypatch, snapshot_module):
    summary = ForecastSnapshotSummary(8, 2, "failed", 2, 1, 3, 3, 0, 0, "2026-07-02: RuntimeError: unavailable")
    service = MagicMock()
    service.create_snapshot.return_value = summary
    monkeypatch.setattr(snapshot_module, "ForecastSnapshotService", lambda: service)

    with pytest.raises(RuntimeError, match="run_id=8.*2026-07-02: RuntimeError: unavailable"):
        snapshot_module.create_forecast_snapshot(**valid_context())
