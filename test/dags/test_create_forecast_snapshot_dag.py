import importlib
import sys
import types
from datetime import date
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
    airflow_module.__dict__["DAG"] = FakeDAG
    airflow_operators = types.ModuleType("airflow.operators")
    airflow_python = types.ModuleType("airflow.operators.python")
    airflow_python.__dict__["PythonOperator"] = FakePythonOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.operators", airflow_operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", airflow_python)

    sys.modules.pop("create_forecast_snapshot", None)
    module = importlib.import_module("create_forecast_snapshot")
    yield module
    sys.modules.pop("create_forecast_snapshot", None)


def valid_context() -> dict[str, Any]:
    return {
        "dag_run": SimpleNamespace(
            conf={
                "report_end_date": "2026-06-30",
                "announcement_start_date": "2026-07-01",
                "announcement_end_date": "2026-07-02",
            }
        )
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


@pytest.mark.parametrize(
    ("context", "parameter"),
    [
        ({}, "dag_run"),
        *(
            (
                {
                    "dag_run": SimpleNamespace(
                        conf={key: value for key, value in valid_context()["dag_run"].conf.items() if key != parameter}
                    )
                },
                parameter,
            )
            for parameter in ("report_end_date", "announcement_start_date", "announcement_end_date")
        ),
        *(
            (
                {
                    "dag_run": SimpleNamespace(
                        conf={
                            **valid_context()["dag_run"].conf,
                            parameter: value,
                        }
                    )
                },
                parameter,
            )
            for parameter in ("report_end_date", "announcement_start_date", "announcement_end_date")
            for value in (None, 20260701)
        ),
        (
            {
                "dag_run": SimpleNamespace(
                    conf={
                        "report_end_date": "20260630",
                        "announcement_start_date": "2026-07-01",
                        "announcement_end_date": "2026-07-02",
                    }
                )
            },
            "report_end_date",
        ),
        (
            {
                "dag_run": SimpleNamespace(
                    conf={
                        "report_end_date": "2026-06-30",
                        "announcement_start_date": "2026-07-02",
                        "announcement_end_date": "2026-07-01",
                    }
                )
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


def test_snapshot_callable_raises_persisted_failed_summary_detail(monkeypatch, snapshot_module):
    summary = ForecastSnapshotSummary(8, 2, "failed", 2, 1, 3, 3, 0, 0, "2026-07-02: RuntimeError: unavailable")
    service = MagicMock()
    service.create_snapshot.return_value = summary
    monkeypatch.setattr(snapshot_module, "ForecastSnapshotService", lambda: service)

    with pytest.raises(RuntimeError, match="run_id=8.*2026-07-02: RuntimeError: unavailable"):
        snapshot_module.create_forecast_snapshot(**valid_context())
