# Monitor Blackroom DAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shareholder-selling blackroom sync and blackroom countdown tasks to the existing daily monitor DAG.

**Architecture:** Extend `dags/monitor_stock_daily.py` with two small task callables and two `PythonOperator`s. Keep shareholder-selling sync independent of the trading-day-gated `run_daily_monitor`; keep countdown downstream of both sync and daily monitor so it does not run until both upstream branches are complete when they run.

**Tech Stack:** Python 3.11+, Airflow DAG/PythonOperator, pytest, existing monitor services.

---

## File Structure

- Modify `dags/monitor_stock_daily.py`: add date formatting helper, service task callables, Airflow operators, and dependencies.
- Create `test/dags/test_monitor_stock_daily.py`: DAG callable and source-structure tests with stubbed Airflow modules.
- Keep `monitor/shareholder_selling_punishment.py` and `monitor/blackroom_countdown.py` unchanged.

### Task 1: Add DAG Tests First

**Files:**
- Create: `test/dags/test_monitor_stock_daily.py`
- Read-only reference: `dags/monitor_stock_daily.py`

- [ ] **Step 1: Write failing tests**

Create `test/dags/test_monitor_stock_daily.py` with this content:

```python
import importlib
import os
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = ROOT / "dags"


class FakeAirflowSkipException(Exception):
    pass


class FakeDAG:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class FakePythonOperator:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.task_id = kwargs.get("task_id")
        self.downstream = []
        FakePythonOperator.instances.append(self)

    def __rshift__(self, other):
        self.downstream.append(other)
        return other


@pytest.fixture()
def monitor_stock_daily_module(monkeypatch):
    FakePythonOperator.instances = []
    monkeypatch.syspath_prepend(str(DAGS_DIR))
    monkeypatch.setenv("FROG_PROJECT_ROOT", str(ROOT))

    airflow_module = types.ModuleType("airflow")
    airflow_module.DAG = FakeDAG
    airflow_exceptions = types.ModuleType("airflow.exceptions")
    airflow_exceptions.AirflowSkipException = FakeAirflowSkipException
    airflow_operators = types.ModuleType("airflow.operators")
    airflow_python = types.ModuleType("airflow.operators.python")
    airflow_python.PythonOperator = FakePythonOperator

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

    result = monitor_stock_daily_module.sync_shareholder_selling_blackroom(
        logical_date=datetime(2026, 6, 3, 15, 30)
    )

    service.return_value.sync.assert_called_once_with(
        start_date="20260603", end_date="20260603", ban_days=180
    )
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
        monitor_stock_daily_module.sync_shareholder_selling_blackroom(
            logical_date=datetime(2026, 6, 3, 15, 30)
        )


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
poetry run pytest test/dags/test_monitor_stock_daily.py -v
```

Expected: tests fail because `sync_shareholder_selling_blackroom` and `countdown_blackroom_records` are not defined in `monitor_stock_daily.py`.

### Task 2: Implement Daily Monitor DAG Tasks

**Files:**
- Modify: `dags/monitor_stock_daily.py`
- Test: `test/dags/test_monitor_stock_daily.py`

- [ ] **Step 1: Add imports and helper functions**

Update `dags/monitor_stock_daily.py` so the top imports include JSON and datetime typing:

```python
import json
import os
import sys
from datetime import datetime
from typing import Any
```

After `run_daily_monitor`, add:

```python
def _format_logical_date(context: dict[str, Any]) -> str:
    logical_date = context.get("logical_date") or context.get("execution_date")
    if isinstance(logical_date, datetime):
        return logical_date.strftime("%Y%m%d")
    return datetime.now().strftime("%Y%m%d")


def _raise_if_failed(result: dict[str, Any], task_name: str) -> None:
    if result.get("success"):
        return
    code = result.get("code", "UNKNOWN")
    message = result.get("message", "")
    raise Exception(f"{task_name} failed: {code}: {message}")
```

- [ ] **Step 2: Add service task callables**

Still in `dags/monitor_stock_daily.py`, add:

```python
def sync_shareholder_selling_blackroom(**context):
    """Sync shareholder-selling announcements into blackroom bans every scheduled day."""
    from monitor.shareholder_selling_punishment import ShareholderSellingPunishmentService

    run_date = _format_logical_date(context)
    result = ShareholderSellingPunishmentService().sync(
        start_date=run_date,
        end_date=run_date,
        ban_days=180,
    )
    _raise_if_failed(result, "股东减持黑屋同步")

    data = result.get("data") or {}
    return (
        "股东减持黑屋同步完成: "
        f"date={run_date}, fetched={data.get('fetched', 0)}, "
        f"unique_stocks={data.get('unique_stocks', 0)}, "
        f"added={data.get('added', 0)}, skipped={data.get('skipped', 0)}"
    )


def countdown_blackroom_records(**context):
    """Update blackroom remaining-day countdown values."""
    from monitor.blackroom_countdown import BlackroomCountdownService

    result = BlackroomCountdownService().run()
    _raise_if_failed(result, "黑屋倒计时")
    return f"黑屋倒计时完成: {json.dumps(result.get('data'), ensure_ascii=False)}"
```

- [ ] **Step 3: Name existing operator and add new operators**

Replace the existing anonymous `PythonOperator(...)` at the bottom of `dags/monitor_stock_daily.py` with:

```python
daily_monitor_task = PythonOperator(
    task_id="run_daily_monitor",
    python_callable=run_daily_monitor,
    dag=dag,
)

sync_shareholder_selling_task = PythonOperator(
    task_id="sync_shareholder_selling_blackroom",
    python_callable=sync_shareholder_selling_blackroom,
    dag=dag,
)

countdown_blackroom_task = PythonOperator(
    task_id="countdown_blackroom_records",
    python_callable=countdown_blackroom_records,
    dag=dag,
)

sync_shareholder_selling_task >> countdown_blackroom_task
daily_monitor_task >> countdown_blackroom_task
```

- [ ] **Step 4: Run focused DAG tests**

Run:

```bash
poetry run pytest test/dags/test_monitor_stock_daily.py -v
```

Expected: all tests in `test/dags/test_monitor_stock_daily.py` pass.

### Task 3: Verify Existing Behavior

**Files:**
- Test: `test/dags/test_monitor_stock_daily.py`
- Existing tests: `test/monitor/test_shareholder_selling_punishment.py`, `test/monitor/test_blackroom_countdown.py`

- [ ] **Step 1: Run related tests**

Run:

```bash
poetry run pytest test/dags/test_monitor_stock_daily.py test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_countdown.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run formatter/checker subset**

Run:

```bash
poetry run black dags/monitor_stock_daily.py test/dags/test_monitor_stock_daily.py
poetry run isort dags/monitor_stock_daily.py test/dags/test_monitor_stock_daily.py
poetry run flake8 --max-line-length=120 dags/monitor_stock_daily.py test/dags/test_monitor_stock_daily.py
```

Expected: formatting tools complete and flake8 reports no issues.

## Self-Review

- Spec coverage: Tasks cover DAG task creation, independent shareholder-selling sync, countdown dependency, logical-date formatting, service failure handling, and tests.
- Placeholder scan: No placeholder implementation steps remain.
- Type consistency: Task callable names and operator variable names match the tests and dependency assertions.
- Commit note: This repository instruction says not to commit unless explicitly requested, so this plan intentionally omits commit execution.
