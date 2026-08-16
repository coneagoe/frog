# Issue 64 Forecast SSF Workflow Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add focused regression evidence and operator documentation for the completed forecast SSF close-crossover workflow.

**Architecture:** Keep production behavior unchanged unless the new regression exposes a gap. Add one monitor-runner public-seam regression for retained `last_state` across disable/re-enable and later final-close crossover, then update `docs/stock_monitor.md` for operator-facing semantics and run focused verification suites.

**Tech Stack:** Python 3.12, pytest, pandas, SQLAlchemy storage tests, Ruff, mypy, repository test runner `tools/run_tests.sh` for PostgreSQL-dependent tests.

## Global Constraints

- Use `uv run` for Python commands in this repo; do not use bare `python` or `python3` for project tasks.
- Use `tools/run_tests.sh` for PostgreSQL-dependent storage coverage.
- Do not change DAG schedule, dependencies, retries, task boundaries, or SLA.
- Preserve existing storage contracts and migration mechanics.
- The workflow is research/monitoring only and must not issue orders or make execution decisions.
- Follow TDD: write failing tests before production changes.

---

## File Structure

- Modify `test/monitor/test_monitor_runner.py`: add the cross-boundary regression for disabled/re-enabled target state and later HFQ final-close crossover.
- Modify `docs/stock_monitor.md`: clarify snapshot coverage limits, completed-snapshot selection, listing/ST limitations, retained target lifecycle, HFQ final-close crossover semantics, and no automatic trade execution.
- Modify `monitor/monitor_runner.py` only if the new regression fails for a real production behavior gap.

---

### Task 1: Add Monitor-Runner Regression

**Files:**
- Modify: `test/monitor/test_monitor_runner.py`
- Maybe modify: `monitor/monitor_runner.py`

**Interfaces:**
- Consumes: `run_monitor(frequency: str = "daily", workflow: str | None = None, as_of_date: date | None = None) -> MonitorSummary`
- Consumes: `fetch_final_close_history_df(stock_code, as_of_date, min_periods=21)` patched by test.
- Produces: regression evidence that retained `last_state=True` suppresses immediate re-enable alerts and that auto reset plus later valid upward close crossover alerts once.

- [ ] **Step 1: Write the failing test**

Add this test near the existing `close_cross_ma` monitor-runner tests:

```python
def _close_history(end: str, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({COL_DATE: pd.date_range(end=end, periods=len(closes)), COL_CLOSE: closes})


def test_reenabled_workflow_target_above_ma_waits_for_later_close_crossover():
    target = _make_target(
        condition={"type": "close_cross_ma", "direction": "above", "period": 20},
        last_state=True,
        reset_mode="auto",
    )
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    histories = [
        _close_history("2026-06-03", [10.0] * 20 + [11.0]),
        _close_history("2026-06-04", [10.0] * 20 + [9.0]),
        _close_history("2026-06-05", [10.0] * 20 + [11.0]),
    ]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", side_effect=histories) as fetch_final,
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.BlackroomService") as blackroom,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        first = run_monitor(workflow="forecast_ssf_ma20", as_of_date=date(2026, 6, 3))
        target.last_state = False
        second = run_monitor(workflow="forecast_ssf_ma20", as_of_date=date(2026, 6, 4))
        third = run_monitor(workflow="forecast_ssf_ma20", as_of_date=date(2026, 6, 5))

    assert fetch_final.call_count == 3
    realtime.assert_not_called()
    assert storage.update_monitor_target_state.call_args_list == [
        ((1, False), {"triggered_at": None}),
        ((1, True), {"triggered_at": storage.update_monitor_target_state.call_args_list[1].kwargs["triggered_at"]}),
    ]
    email.assert_called_once()
    blackroom.return_value.is_banned.assert_called_once_with("600519", "A")
    assert (first.triggered, first.skipped, first.errors) == (0, 0, 0)
    assert (second.triggered, second.skipped, second.errors) == (0, 0, 0)
    assert (third.triggered, third.skipped, third.errors) == (1, 0, 0)
```

- [ ] **Step 2: Run test to verify it fails or proves existing behavior**

Run: `uv run pytest test/monitor/test_monitor_runner.py::test_reenabled_workflow_target_above_ma_waits_for_later_close_crossover -v`

Expected if incomplete: FAIL because immediate re-enable alerts or later crossover does not alert exactly once. If it passes immediately, record that existing behavior already satisfies the regression and keep the test as coverage.

- [ ] **Step 3: Write minimal implementation only if needed**

If the test fails, update only `monitor/monitor_runner.py` so `close_cross_ma` uses `evaluate_condition` on HFQ final closes, preserves state on insufficient data, auto-resets only when condition clears, and alerts only on `False -> True`.

- [ ] **Step 4: Run monitor-runner focused tests**

Run: `uv run pytest test/monitor/test_monitor_runner.py -v`

Expected: PASS.

---

### Task 2: Update Operator Documentation

**Files:**
- Modify: `docs/stock_monitor.md`

**Interfaces:**
- Consumes: workflow behavior from issues #59-#63.
- Produces: operator documentation for issue #64 acceptance criteria.

- [ ] **Step 1: Update docs**

Edit `docs/stock_monitor.md` so it explicitly states:

- Snapshot ingestion verifies every requested announcement date in the explicit range; empty dates are successful coverage, failed runs are diagnostics only and are not selectable.
- Later synchronization windows select only completed snapshots whose announcement end date is not later than the business date.
- Candidate screening currently supports listed, non-ST A-share stocks only.
- Disabled workflow targets are retained with candidate linkage and can reuse the same target after requalification without resetting `last_state`.
- `close_cross_ma` uses stored HFQ final closes and triggers only on `previous_close <= previous_ma20` and `current_close > current_ma20`.
- The workflow is research/monitoring only; it does not place orders, size positions, or make execution decisions.

- [ ] **Step 2: Review docs for stale `price_vs_ma` operator examples**

Run: `grep -n "price_vs_ma\|自动下单\|交易执行" docs/stock_monitor.md`

Expected: no stale instruction implying active `price_vs_ma` use or automatic execution.

---

### Task 3: Focused Verification

**Files:**
- No expected source modifications.

**Interfaces:**
- Consumes: tests and docs from Tasks 1-2.
- Produces: final evidence for issue #64 acceptance criteria.

- [ ] **Step 1: Run focused public-seam suites**

Run: `uv run pytest test/monitor/test_monitor_runner.py test/monitor/test_forecast_ssf_monitor_sync.py test/tools/test_create_forecast_snapshot.py test/dags/test_create_forecast_snapshot_dag.py test/dags/test_forecast_ssf_ma20_sync.py -v`

Expected: PASS.

- [ ] **Step 2: Run PostgreSQL-dependent storage coverage through repository runner**

Run: `tools/run_tests.sh test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/storage/test_enum_migration.py -v`

Expected: PASS or environment-blocked with a concrete service error to report.

- [ ] **Step 3: Run formatting, lint, and relevant type checks**

Run:

```bash
uv run ruff format test/monitor/test_monitor_runner.py docs/stock_monitor.md
uv run ruff check test/monitor/test_monitor_runner.py monitor/monitor_runner.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 4: Run simplify review**

Use the `simplify` skill to review touched code for behavior-preserving clarity improvements. Apply only targeted simplifications that preserve issue #64 scope.

## Self-Review

- Spec coverage: Task 1 covers the cross-boundary disable/re-enable regression; Task 2 covers operator docs; Task 3 covers public-seam suites and PostgreSQL runner requirements.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: all named functions and paths already exist except the new local test helper.
