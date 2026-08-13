import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from download.download_manager import ForecastDownloadResult
from tools import backfill_forecast

ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = ROOT / "dags"


class FakeAirflowDateTime(datetime):
    def in_timezone(self, tz):
        return self.astimezone(tz)


class FakeDAG:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class FakePythonOperator:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


@pytest.fixture()
def daily_module(monkeypatch):
    monkeypatch.syspath_prepend(str(DAGS_DIR))
    monkeypatch.setenv("FROG_PROJECT_ROOT", str(ROOT))
    airflow = types.ModuleType("airflow")
    airflow.DAG = FakeDAG
    airflow_operators = types.ModuleType("airflow.operators")
    airflow_python = types.ModuleType("airflow.operators.python")
    airflow_python.PythonOperator = FakePythonOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow)
    monkeypatch.setitem(sys.modules, "airflow.operators", airflow_operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", airflow_python)
    sys.modules.pop("download_forecast_daily", None)
    module = importlib.import_module("download_forecast_daily")
    yield module
    sys.modules.pop("download_forecast_daily", None)


def local_window_context():
    return {"data_interval_end": FakeAirflowDateTime(2026, 8, 10, 10, tzinfo=timezone.utc)}


def test_workflows_aggregate_saved_and_empty_results_consistently(monkeypatch, daily_module, capsys):
    rolling_manager = MagicMock()
    rolling_manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260712", 2, 1, True),
        ForecastDownloadResult("20260713", 0, 0, True),
        *[ForecastDownloadResult(f"date-{offset}", 1, 1, True) for offset in range(28)],
    ]
    monkeypatch.setattr(daily_module, "DownloadManager", lambda: rolling_manager)

    rolling_summary = daily_module.download_forecast(**local_window_context())

    backfill_manager = MagicMock()
    backfill_manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260801", 2, 1, True),
        ForecastDownloadResult("20260802", 0, 0, True),
        ForecastDownloadResult("20260803", 1, 1, True),
    ]
    monkeypatch.setattr(backfill_forecast, "parse_config", lambda: None)
    monkeypatch.setattr(backfill_forecast, "DownloadManager", lambda: backfill_manager)

    assert backfill_forecast.main(["--start-date", "2026-08-01", "--end-date", "2026-08-03"]) == 0
    assert rolling_summary["successful_dates"] == 30
    assert rolling_summary["empty_dates"] == 1
    assert rolling_summary["failed_dates"] == 0
    assert rolling_summary["source_rows"] == 30
    assert rolling_summary["a_share_rows"] == 29
    assert rolling_manager.download_forecast.call_count == 30
    assert rolling_manager.download_forecast.call_args_list[0] == call(ann_date="20260712")
    assert rolling_manager.download_forecast.call_args_list[-1] == call(ann_date="20260810")
    assert backfill_manager.download_forecast.call_args_list == [
        call(ann_date="20260801"),
        call(ann_date="20260802"),
        call(ann_date="20260803"),
    ]
    assert capsys.readouterr().out == (
        "requested_dates=3 successful_dates=3 empty_dates=1 failed_dates=0 source_rows=3 a_share_rows=2\n"
    )


def test_daily_workflow_stops_on_first_unsaved_result(monkeypatch, daily_module):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260712", 1, 1, True),
        ForecastDownloadResult("20260713", 0, 0, False),
    ]
    monkeypatch.setattr(daily_module, "DownloadManager", lambda: manager)

    with pytest.raises(RuntimeError, match="20260713"):
        daily_module.download_forecast(**local_window_context())

    assert manager.download_forecast.call_count == 2


def test_backfill_workflow_continues_and_reports_unsaved_result(monkeypatch, capsys):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260801", 1, 1, True),
        ForecastDownloadResult("20260802", 0, 0, False),
        ForecastDownloadResult("20260803", 3, 0, True),
    ]
    monkeypatch.setattr(backfill_forecast, "parse_config", lambda: None)
    monkeypatch.setattr(backfill_forecast, "DownloadManager", lambda: manager)

    assert backfill_forecast.main(["--start-date", "2026-08-01", "--end-date", "2026-08-03"]) == 1
    assert manager.download_forecast.call_count == 3
    assert capsys.readouterr().out == (
        "requested_dates=3 successful_dates=2 empty_dates=1 failed_dates=1 "
        "source_rows=4 a_share_rows=1\n"
        "failed_announcement_dates=20260802\n"
    )
