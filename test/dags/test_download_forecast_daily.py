import importlib
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
def forecast_module(monkeypatch):
    FakePythonOperator.instances = []
    monkeypatch.syspath_prepend(str(DAGS_DIR))
    monkeypatch.setenv("FROG_PROJECT_ROOT", str(ROOT))

    airflow_module = types.ModuleType("airflow")
    airflow_module.DAG = FakeDAG
    airflow_operators = types.ModuleType("airflow.operators")
    airflow_python = types.ModuleType("airflow.operators.python")
    airflow_python.PythonOperator = FakePythonOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.operators", airflow_operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", airflow_python)

    sys.modules.pop("download_forecast_daily", None)
    module = importlib.import_module("download_forecast_daily")
    yield module
    sys.modules.pop("download_forecast_daily", None)


def local_window_context() -> dict[str, Any]:
    return {"data_interval_end": FakeAirflowDateTime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)}


def test_forecast_dag_schedule_and_single_task(forecast_module):
    tasks = {task.task_id: task for task in FakePythonOperator.instances}

    assert forecast_module.dag.kwargs["schedule"] == "0 18 * * *"
    assert forecast_module.dag.kwargs["max_active_runs"] == 1
    assert set(tasks) == {"download_forecast"}


def test_announcement_dates_use_local_interval_end_and_include_thirty_natural_days(forecast_module):
    dates = forecast_module._announcement_dates(local_window_context())

    assert [item.isoformat() for item in dates] == [
        "2026-07-12",
        "2026-07-13",
        "2026-07-14",
        "2026-07-15",
        "2026-07-16",
        "2026-07-17",
        "2026-07-18",
        "2026-07-19",
        "2026-07-20",
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
        "2026-07-24",
        "2026-07-25",
        "2026-07-26",
        "2026-07-27",
        "2026-07-28",
        "2026-07-29",
        "2026-07-30",
        "2026-07-31",
        "2026-08-01",
        "2026-08-02",
        "2026-08-03",
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
        "2026-08-07",
        "2026-08-08",
        "2026-08-09",
        "2026-08-10",
    ]


def test_download_forecast_returns_aggregate_statistics(monkeypatch, forecast_module):
    manager = MagicMock()
    manager.download_forecast.side_effect = (
        [
            types.SimpleNamespace(announcement_date="20260712", source_rows=2, a_share_rows=1, saved=True),
            types.SimpleNamespace(announcement_date="20260713", source_rows=0, a_share_rows=0, saved=True),
        ]
        + [
            types.SimpleNamespace(announcement_date=f"202607{day:02d}", source_rows=1, a_share_rows=1, saved=True)
            for day in range(14, 32)
        ]
        + [
            types.SimpleNamespace(announcement_date=f"202608{day:02d}", source_rows=1, a_share_rows=1, saved=True)
            for day in range(1, 11)
        ]
    )
    monkeypatch.setattr(forecast_module, "DownloadManager", lambda: manager)

    result = forecast_module.download_forecast(**local_window_context())

    assert result == {
        "announcement_dates": [
            "20260712",
            "20260713",
            *[f"202607{day:02d}" for day in range(14, 32)],
            *[f"202608{day:02d}" for day in range(1, 11)],
        ],
        "requested_dates": 30,
        "successful_dates": 30,
        "empty_dates": 1,
        "failed_dates": 0,
        "source_rows": 30,
        "a_share_rows": 29,
    }
    assert manager.download_forecast.call_count == 30
    assert manager.download_forecast.call_args_list[0].kwargs == {"ann_date": "20260712"}
    assert manager.download_forecast.call_args_list[-1].kwargs == {"ann_date": "20260810"}


def test_download_forecast_accepts_zero_a_share_rows_as_empty_success(monkeypatch, forecast_module):
    manager = MagicMock()
    manager.download_forecast.return_value = types.SimpleNamespace(
        announcement_date="20260712", source_rows=3, a_share_rows=0, saved=True
    )
    monkeypatch.setattr(forecast_module, "DownloadManager", lambda: manager)

    result = forecast_module.download_forecast(**local_window_context())

    assert result["successful_dates"] == 30
    assert result["empty_dates"] == 30
    assert result["failed_dates"] == 0
    assert result["source_rows"] == 90
    assert result["a_share_rows"] == 0


def test_download_forecast_logs_failed_result_statistics_and_stops_on_first_unsaved_date(
    monkeypatch, caplog, forecast_module
):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        types.SimpleNamespace(announcement_date="20260712", source_rows=1, a_share_rows=1, saved=True),
        types.SimpleNamespace(announcement_date="20260713", source_rows=3, a_share_rows=0, saved=False),
    ]
    monkeypatch.setattr(forecast_module, "DownloadManager", lambda: manager)

    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError, match="20260713"):
            forecast_module.download_forecast(**local_window_context())

    assert caplog.records[-1].args == {
        "announcement_dates": [
            "20260712",
            "20260713",
            *[f"202607{day:02d}" for day in range(14, 32)],
            *[f"202608{day:02d}" for day in range(1, 11)],
        ],
        "requested_dates": 30,
        "successful_dates": 1,
        "empty_dates": 1,
        "failed_dates": 1,
        "source_rows": 4,
        "a_share_rows": 1,
    }

    assert manager.download_forecast.call_count == 2
