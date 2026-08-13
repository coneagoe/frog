# Rolling Daily Forecast Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily 18:00 Asia/Shanghai Airflow DAG that refreshes the latest 30 natural forecast-announcement dates and exposes aggregate results.

**Architecture:** Create a standalone, one-task DAG which derives its end date from Airflow's local data interval and loops over an inclusive natural-date window. The task consumes the existing `DownloadManager.download_forecast` structured result, accumulates operational statistics for successful dates, logs the failed summary and raises on the first unsuccessful date so Airflow's existing retry and alert policy applies.

**Tech Stack:** Python 3.11+, Apache Airflow `DAG` and `PythonOperator`, `datetime`, `zoneinfo`, pytest, unittest.mock, Ruff, uv.

## Global Constraints

- Change only `dags/download_forecast_daily.py` and `test/dags/test_download_forecast_daily.py`; do not add the forecast backfill CLI.
- Use `schedule="0 18 * * *"`, `get_default_args()`, `LOCAL_TZ`, `catchup=False`, and `max_active_runs=1`.
- Derive the run end date from `context["data_interval_end"].in_timezone(LOCAL_TZ).date()`; do not use the A-share trading calendar.
- Refresh exactly the inclusive current date plus the preceding 29 natural dates and invoke `DownloadManager.download_forecast(ann_date=YYYYMMDD)` once for each until a failure.
- A result is successful only when `ForecastDownloadResult.saved` is true; zero source rows or zero A-share rows with `saved=True` are valid empty outcomes.
- Return a JSON-serializable summary only after all dates succeed. On failure, log the aggregate summary and raise `RuntimeError` including the failed announcement date.
- Do not modify forecast normalization, persistence, `forecast_ssf_ma20_sync`, daily monitors, their schedules, dependencies, retries, SLA, or selection logic.
- Mock `DownloadManager.download_forecast`; tests must not call TuShare or storage.
- Use `uv run` for every Python, pytest, Ruff, and mypy command.

---

### Task 1: Add The Rolling Forecast DAG And Its Tests

**Files:**
- Create: `dags/download_forecast_daily.py`
- Create: `test/dags/test_download_forecast_daily.py`

**Interfaces:**
- Consumes: `dags.common_dags.LOCAL_TZ`, `dags.common_dags.get_default_args()`, and `download.DownloadManager`.
- Consumes: `DownloadManager.download_forecast(ann_date: str) -> ForecastDownloadResult`, whose result exposes `announcement_date: str`, `source_rows: int`, `a_share_rows: int`, and `saved: bool`.
- Produces: `_announcement_dates(context: dict[str, Any]) -> list[date]`, returning the chronological 30-date natural-day window.
- Produces: `download_forecast(**context: Any) -> dict[str, Any]`, returning a JSON-serializable all-success summary or raising `RuntimeError` for the first unsuccessful result.
- Produces: Airflow DAG `download_forecast_daily` with one `PythonOperator`, task ID `download_forecast`.

- [ ] **Step 1: Write the failing mocked-Airflow DAG tests**

Create `test/dags/test_download_forecast_daily.py` with the Airflow test doubles used by `test/dags/test_forecast_ssf_ma20_sync.py`, then add the tests below. The fixture imports the module by its filename after injecting the fake `airflow`, `airflow.operators`, and `airflow.operators.python` modules.

```python
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
    manager.download_forecast.side_effect = [
        types.SimpleNamespace(announcement_date="20260712", source_rows=2, a_share_rows=1, saved=True),
        types.SimpleNamespace(announcement_date="20260713", source_rows=0, a_share_rows=0, saved=True),
    ] + [
        types.SimpleNamespace(announcement_date=f"202607{day:02d}", source_rows=1, a_share_rows=1, saved=True)
        for day in range(14, 32)
    ] + [
        types.SimpleNamespace(announcement_date=f"202608{day:02d}", source_rows=1, a_share_rows=1, saved=True)
        for day in range(1, 11)
    ]
    monkeypatch.setattr(forecast_module, "DownloadManager", lambda: manager)

    result = forecast_module.download_forecast(**local_window_context())

    assert result == {
        "announcement_dates": ["20260712", "20260713", *[f"202607{day:02d}" for day in range(14, 32)], *[f"202608{day:02d}" for day in range(1, 11)]],
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


def test_download_forecast_raises_on_first_unsaved_date(monkeypatch, forecast_module):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        types.SimpleNamespace(announcement_date="20260712", source_rows=1, a_share_rows=1, saved=True),
        types.SimpleNamespace(announcement_date="20260713", source_rows=0, a_share_rows=0, saved=False),
    ]
    monkeypatch.setattr(forecast_module, "DownloadManager", lambda: manager)

    with pytest.raises(RuntimeError, match="20260713"):
        forecast_module.download_forecast(**local_window_context())

    assert manager.download_forecast.call_count == 2
```

- [ ] **Step 2: Run the focused test module and confirm it fails before implementation**

Run:

```bash
uv run pytest test/dags/test_download_forecast_daily.py -v
```

Expected: FAIL during import because `dags/download_forecast_daily.py` does not exist.

- [ ] **Step 3: Create the standalone daily forecast DAG**

Create `dags/download_forecast_daily.py` with the following implementation. Keep the `DownloadManager` import at module level because the focused tests replace it directly.

```python
"""18:00 daily refresh of recent forecast announcement dates."""

import logging
import os
import sys
from datetime import date, timedelta
from typing import Any, cast

from airflow import DAG
from airflow.operators.python import PythonOperator

project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dags.common_dags import LOCAL_TZ, get_default_args  # noqa: E402, I001
from download import DownloadManager  # noqa: E402


def _announcement_dates(context: dict[str, Any]) -> list[date]:
    end_date = cast(date, context["data_interval_end"].in_timezone(LOCAL_TZ).date())
    return [end_date - timedelta(days=offset) for offset in range(29, -1, -1)]


def download_forecast(**context: Any) -> dict[str, Any]:
    announcement_dates = _announcement_dates(context)
    manager = DownloadManager()
    summary: dict[str, Any] = {
        "announcement_dates": [item.strftime("%Y%m%d") for item in announcement_dates],
        "requested_dates": len(announcement_dates),
        "successful_dates": 0,
        "empty_dates": 0,
        "failed_dates": 0,
        "source_rows": 0,
        "a_share_rows": 0,
    }

    for announcement_date in announcement_dates:
        result = manager.download_forecast(ann_date=announcement_date.strftime("%Y%m%d"))
        if not result.saved:
            summary["failed_dates"] += 1
            logging.error("Daily forecast download failed: summary=%s", summary)
            raise RuntimeError(f"forecast download failed for {result.announcement_date}")

        summary["successful_dates"] += 1
        summary["source_rows"] += result.source_rows
        summary["a_share_rows"] += result.a_share_rows
        if result.source_rows == 0 or result.a_share_rows == 0:
            summary["empty_dates"] += 1

    logging.info("Daily forecast download completed: summary=%s", summary)
    return summary


dag = DAG(
    "download_forecast_daily",
    default_args=get_default_args(),
    description="每日刷新最近30天业绩预告数据",
    schedule="0 18 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["forecast"],
)

PythonOperator(
    task_id="download_forecast",
    python_callable=download_forecast,
    dag=dag,
)
```

- [ ] **Step 4: Run the focused test module and confirm it passes**

Run:

```bash
uv run pytest test/dags/test_download_forecast_daily.py -v
```

Expected: all five tests PASS.

- [ ] **Step 5: Run formatting, linting, type checking, and related regression tests**

Run:

```bash
uv run ruff format --check dags/download_forecast_daily.py test/dags/test_download_forecast_daily.py
uv run ruff check dags/download_forecast_daily.py test/dags/test_download_forecast_daily.py
uv run mypy dags/download_forecast_daily.py
uv run pytest test/dags/test_download_forecast_daily.py test/dags/test_forecast_ssf_ma20_sync.py test/download/test_download_manager.py
```

Expected: every command exits with status 0.

- [ ] **Step 6: Inspect the scoped diff and commit the completed DAG**

Run:

```bash
git diff --check
git diff -- dags/download_forecast_daily.py test/dags/test_download_forecast_daily.py
git status --short
```

Confirm only the two task files are staged, then commit:

```bash
git add dags/download_forecast_daily.py test/dags/test_download_forecast_daily.py
git commit -m "feat: add daily forecast ingestion"
```
