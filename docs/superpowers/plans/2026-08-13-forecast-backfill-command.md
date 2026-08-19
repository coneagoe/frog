# Forecast Backfill Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operator CLI that backfills forecast records across an inclusive natural-date range and reports complete, auditable outcomes.

**Architecture:** A new standalone script follows the existing `tools/` entrypoint pattern: it places the repository root on `sys.path`, parses arguments, initializes configuration, then drives one `DownloadManager` over the selected range. Small importable helpers isolate range resolution and structured-result aggregation, while `main` owns argument parsing, stdout reporting, and process exit status.

**Tech Stack:** Python 3.11+, `argparse`, standard-library `datetime`, existing `conf.parse_config`, `DownloadManager`, and pytest mocks.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Add `tools/backfill_forecast.py` and `test/tools/test_backfill_forecast.py` only; do not change the download manager, forecast storage, or Airflow DAG.
- Use natural calendar days, not an A-share trading calendar.
- The default range is inclusive from `2026-01-01` through `date.today() - timedelta(days=7)`.
- Explicit `--start-date` and `--end-date` are ISO `YYYY-MM-DD`, must be supplied together, and are inclusive.
- Invalid or incomplete date arguments and an inverted range must be argparse validation failures with exit code `2`.
- A date succeeds only when `ForecastDownloadResult.saved` is true; successful results with zero source rows or zero A-share rows count as empty dates.
- Process every selected date despite failed outcomes, then exit `1` when any date failed and `0` otherwise.
- Initialize through `conf.parse_config()` before creating `DownloadManager`.

---

### Task 1: Forecast Backfill Command

**Files:**
- Create: `tools/backfill_forecast.py`
- Create: `test/tools/test_backfill_forecast.py`

**Interfaces:**
- Consumes: `conf.parse_config() -> None` and `DownloadManager.download_forecast(ann_date: str) -> ForecastDownloadResult` where the result has `announcement_date`, `source_rows`, `a_share_rows`, and `saved` attributes.
- Produces: `resolve_dates(start_date: date | None, end_date: date | None, today: date | None = None) -> list[date]`, `backfill_forecast(announcement_dates: list[date], manager: DownloadManager) -> tuple[dict[str, int], list[str]]`, and `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing tests for default and explicit inclusive date ranges**

```python
from datetime import date

from tools import backfill_forecast as command


def test_resolve_dates_uses_default_start_and_seven_day_lag():
    dates = command.resolve_dates(today=date(2026, 8, 13))

    assert dates[0] == date(2026, 1, 1)
    assert dates[-1] == date(2026, 8, 6)
    assert len(dates) == 218


def test_resolve_dates_includes_explicit_boundaries():
    assert command.resolve_dates(date(2026, 8, 1), date(2026, 8, 3)) == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]
```

- [ ] **Step 2: Run the focused date-range tests to verify they fail**

Run: `uv run pytest test/tools/test_backfill_forecast.py -k resolve_dates -v`

Expected: FAIL because `tools.backfill_forecast` and its public helpers do not exist.

- [ ] **Step 3: Implement date parsing, validation, and inclusive date resolution**

```python
def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}") from exc


def resolve_dates(
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    today: date | None = None,
) -> list[date]:
    if (start_date is None) != (end_date is None):
        raise ValueError("--start-date and --end-date must be supplied together")
    if start_date is None:
        start_date = date(2026, 1, 1)
        end_date = (today or date.today()) - timedelta(days=7)
    assert end_date is not None
    if start_date > end_date:
        raise ValueError("--start-date must not be later than --end-date")
    return [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]
```

Create an `argparse.ArgumentParser` with the two optional arguments using `_parse_date` as their `type`. In `main`, call `parser.error(str(exc))` for `ValueError` from `resolve_dates` so invalid paired or ordered boundaries return argparse's exit code `2`.

- [ ] **Step 4: Run the focused date-range tests to verify they pass**

Run: `uv run pytest test/tools/test_backfill_forecast.py -k resolve_dates -v`

Expected: PASS.

- [ ] **Step 5: Write failing tests for aggregate outcomes, reporting, and operational exit status**

```python
from types import SimpleNamespace


def test_main_reports_complete_summary_and_continues_after_failed_date(monkeypatch, capsys):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        SimpleNamespace(announcement_date="20260801", source_rows=2, a_share_rows=2, saved=True),
        SimpleNamespace(announcement_date="20260802", source_rows=0, a_share_rows=0, saved=False),
        SimpleNamespace(announcement_date="20260803", source_rows=3, a_share_rows=0, saved=True),
    ]
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "DownloadManager", lambda: manager)

    assert command.main(["--start-date", "2026-08-01", "--end-date", "2026-08-03"]) == 1

    assert manager.download_forecast.call_args_list == [
        call(ann_date="20260801"), call(ann_date="20260802"), call(ann_date="20260803")
    ]
    assert capsys.readouterr().out == (
        "requested_dates=3 successful_dates=2 empty_dates=1 failed_dates=1 "
        "source_rows=5 a_share_rows=2\nfailed_announcement_dates=20260802\n"
    )


def test_main_returns_zero_for_successful_empty_results(monkeypatch, capsys):
    manager = MagicMock()
    manager.download_forecast.return_value = SimpleNamespace(
        announcement_date="20260801", source_rows=0, a_share_rows=0, saved=True
    )
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "DownloadManager", lambda: manager)

    assert command.main(["--start-date", "2026-08-01", "--end-date", "2026-08-01"]) == 0
    assert "successful_dates=1 empty_dates=1 failed_dates=0" in capsys.readouterr().out
```

Also add parameterized tests that call `command.main` with one boundary, an inverted pair, and an invalid ISO date. Use `pytest.raises(SystemExit) as exc_info` and assert `exc_info.value.code == 2` for each case.

- [ ] **Step 6: Run the aggregate and validation tests to verify they fail**

Run: `uv run pytest test/tools/test_backfill_forecast.py -k "main or validation" -v`

Expected: FAIL because the command has no aggregation, reporting, or parser-error handling.

- [ ] **Step 7: Implement aggregation, reporting, and entrypoint behavior**

```python
def backfill_forecast(announcement_dates: list[date], manager: DownloadManager) -> tuple[dict[str, int], list[str]]:
    summary = {
        "requested_dates": len(announcement_dates), "successful_dates": 0,
        "empty_dates": 0, "failed_dates": 0, "source_rows": 0, "a_share_rows": 0,
    }
    failed_announcement_dates: list[str] = []
    for announcement_date in announcement_dates:
        result = manager.download_forecast(ann_date=announcement_date.strftime("%Y%m%d"))
        summary["source_rows"] += result.source_rows
        summary["a_share_rows"] += result.a_share_rows
        if result.saved:
            summary["successful_dates"] += 1
            if result.source_rows == 0 or result.a_share_rows == 0:
                summary["empty_dates"] += 1
        else:
            summary["failed_dates"] += 1
            failed_announcement_dates.append(result.announcement_date)
    return summary, failed_announcement_dates
```

In `main`, call `parse_config()`, instantiate `DownloadManager`, call `backfill_forecast`, then print exactly one summary line in this field order: `requested_dates`, `successful_dates`, `empty_dates`, `failed_dates`, `source_rows`, `a_share_rows`. Print `failed_announcement_dates=` followed by comma-joined dates only when failures exist. Return `1` when `summary["failed_dates"]` is nonzero, otherwise `0`. Add the normal `if __name__ == "__main__": raise SystemExit(main())` script entrypoint and the repository-root `sys.path` bootstrap used by other standalone tools.

- [ ] **Step 8: Run the complete focused command test file**

Run: `uv run pytest test/tools/test_backfill_forecast.py -v`

Expected: PASS.

- [ ] **Step 9: Run lint and affected regression tests**

Run: `uv run ruff format --check tools/backfill_forecast.py test/tools/test_backfill_forecast.py && uv run ruff check tools/backfill_forecast.py test/tools/test_backfill_forecast.py && uv run pytest test/tools/test_backfill_forecast.py test/download/test_download_manager.py test/dags/test_download_forecast_daily.py`

Expected: all commands exit `0`; no formatting, lint, or forecast-contract regression failures.

- [ ] **Step 10: Commit the implementation**

```bash
git add tools/backfill_forecast.py test/tools/test_backfill_forecast.py
```
