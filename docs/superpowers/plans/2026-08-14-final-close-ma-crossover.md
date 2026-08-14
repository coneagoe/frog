# Final-Close MA Crossover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, final-HFQ-bar `close_cross_ma` alerts for daily A-share targets while preserving all legacy monitor behavior.

**Architecture:** Keep numerical crossover evaluation in `monitor.condition`; introduce a storage-only HFQ history helper in `monitor.price_fetcher`; and route only the new condition through that helper in `monitor.monitor_runner`. The daily DAG converts its Airflow data interval end to `Asia/Shanghai` and forwards that date as `run_monitor(..., as_of_date=...)` without changing task edges.

**Tech Stack:** Python 3.11+, pandas, NumPy, SQLAlchemy storage interface, Airflow DAG callables, pytest, Ruff, mypy.

## Global Constraints

- Use `uv run` for Python commands in this repository.
- Do not change `monitor_stock_daily` schedule, dependencies, retries, task boundaries, or SLA.
- `close_cross_ma` is daily A-share-only and uses `AdjustType.HFQ` storage data through the explicit evaluation date.
- `close_cross_ma` never calls a realtime price provider.
- Preserve `price_cross_ma` and `price_vs_ma` validation, retrieval, evaluation, and alert behavior.
- Do not migrate or remove persisted `price_vs_ma` targets.
- `INSUFFICIENT_DATA` must send no email and must not change `last_state` or `triggered_at`.
- Mock all external providers; do not use live provider calls in tests.

---

## File Structure

- `monitor/condition.py`: pure final-close numerical crossover evaluation using an already validated 21-bar HFQ series.
- `monitor/condition_validation.py`: accepts the new condition schema without changing legacy schemas.
- `monitor/monitor_target_service.py`: renders a human-readable `close_cross_ma` target label.
- `monitor/price_fetcher.py`: loads deterministic A-share HFQ daily history exclusively from storage.
- `monitor/monitor_runner.py`: resolves China-local evaluation date, selects the final-close retrieval path, skips realtime pricing, and preserves state for insufficient results.
- `dags/monitor_stock_daily.py`: converts Airflow interval end into the China-local business date and forwards it to the runner.
- `docs/stock_monitor.md`: documents the new final-close condition alongside existing monitor conditions.
- `test/monitor/test_condition.py`: numerical crossover boundary tests.
- `test/monitor/test_condition_validation.py`: accepted/rejected condition schema tests.
- `test/monitor/test_monitor_target_service.py`: label regression for the new condition.
- `test/monitor/test_price_fetcher.py`: storage-only HFQ retrieval contract test.
- `test/monitor/test_monitor_runner.py`: no-realtime, stale-data, alert, and state-preservation runner tests.
- `test/dags/test_monitor_stock_daily.py`: China-local evaluation-date forwarding and unchanged task topology tests.

### Task 1: Add The Condition Contract And Pure Crossover Evaluation

**Files:**
- Modify: `monitor/condition.py:49-136`
- Modify: `monitor/condition_validation.py:5-35`
- Modify: `monitor/monitor_target_service.py:34-59`
- Test: `test/monitor/test_condition.py`
- Test: `test/monitor/test_condition_validation.py`
- Test: `test/monitor/test_monitor_target_service.py`

**Interfaces:**
- Consumes: `evaluate_condition(condition: dict, current_price: Optional[float], history_df: Optional[pd.DataFrame], change_pct: Optional[float] = None) -> ConditionResult` and `COL_CLOSE`.
- Produces: `evaluate_condition()` accepts `{"type": "close_cross_ma", "direction": "above", "period": 20}` and returns `TRIGGERED`, `NOT_TRIGGERED`, or `INSUFFICIENT_DATA` from the final 21 supplied close values.

- [ ] **Step 1: Write failing condition and validation tests**

```python
def test_close_cross_ma_requires_a_real_upward_crossover():
    condition = {"type": "close_cross_ma", "direction": "above", "period": 20}
    history = _make_prices([10.0] * 20 + [11.0])

    assert evaluate_condition(condition, current_price=None, history_df=history) == ConditionResult.TRIGGERED


def test_close_cross_ma_allows_previous_equality_but_rejects_current_equality():
    condition = {"type": "close_cross_ma", "direction": "above", "period": 20}

    assert evaluate_condition(condition, None, _make_prices([10.0] * 20 + [11.0])) == ConditionResult.TRIGGERED
    assert evaluate_condition(condition, None, _make_prices([10.0] * 21)) == ConditionResult.NOT_TRIGGERED


def test_close_cross_ma_rejects_missing_or_short_close_series():
    condition = {"type": "close_cross_ma", "direction": "above", "period": 20}

    assert evaluate_condition(condition, None, _make_prices([10.0] * 20)) == ConditionResult.INSUFFICIENT_DATA
    assert evaluate_condition(condition, None, _make_prices([10.0] * 20 + [float("nan")])) == ConditionResult.INSUFFICIENT_DATA


def test_validate_condition_accepts_close_cross_ma():
    condition = {"type": "close_cross_ma", "direction": "above", "period": 20}

    assert validate_condition(condition) == condition
```

Add a target-label test asserting an empty-note `close_cross_ma` target renders as `收盘价上穿20日均线`.

- [ ] **Step 2: Run the new focused tests and verify failure**

Run: `uv run pytest test/monitor/test_condition.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py -v`

Expected: FAIL because `close_cross_ma` is unsupported by validation and evaluation.

- [ ] **Step 3: Implement the minimal condition branch**

```python
elif ctype == "close_cross_ma":
    period = int(condition["period"])
    if history_df is None or len(history_df) < period + 1:
        return ConditionResult.INSUFFICIENT_DATA
    closes = pd.to_numeric(history_df[COL_CLOSE], errors="coerce").iloc[-(period + 1) :]
    if closes.isna().any():
        return ConditionResult.INSUFFICIENT_DATA
    previous_close = float(closes.iloc[-2])
    current_close = float(closes.iloc[-1])
    previous_ma = float(closes.iloc[:-1].mean())
    current_ma = float(closes.iloc[1:].mean())
    return (
        ConditionResult.TRIGGERED
        if previous_close <= previous_ma and current_close > current_ma
        else ConditionResult.NOT_TRIGGERED
    )
```

Accept `close_cross_ma` in `validate_condition` only when `direction` is `above` and `period` is a positive integer. Do not allow `below`, because this issue defines only the upward-crossover contract. Add the target-label branch without changing existing label branches.

- [ ] **Step 4: Run focused condition and target-service tests**

Run: `uv run pytest test/monitor/test_condition.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py -v`

Expected: PASS, including existing `price_cross_ma` and `price_vs_ma` tests.

- [ ] **Step 5: Commit the pure-condition change**

```bash
git add monitor/condition.py monitor/condition_validation.py monitor/monitor_target_service.py test/monitor/test_condition.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py
git commit -m "feat: add final close MA crossover condition"
```

### Task 2: Add Storage-Only HFQ Final-Close History Retrieval

**Files:**
- Modify: `monitor/price_fetcher.py:1-250`
- Test: `test/monitor/test_price_fetcher.py`

**Interfaces:**
- Consumes: `get_storage().load_history_data_stock(stock_id, period, adjust, start_date, end_date)`, `PeriodType.DAILY`, `AdjustType.HFQ`, `COL_DATE`, and `COL_CLOSE`.
- Produces: `fetch_final_close_history_df(stock_code: str, as_of_date: date, min_periods: int) -> Optional[pd.DataFrame]`, sorted ascending and returning `None` when fewer than `min_periods` rows exist.

- [ ] **Step 1: Write a failing storage-only retrieval test**

```python
def test_fetch_final_close_history_uses_hfq_storage_only(monkeypatch):
    storage = SimpleNamespace(
        load_history_data_stock=MagicMock(
            return_value=pd.DataFrame({"日期": ["2026-06-02", "2026-06-03"], "收盘": [10.0, 11.0]})
        )
    )
    monkeypatch.setattr("monitor.price_fetcher.get_storage", lambda: storage)
    monkeypatch.setattr(
        "monitor.price_fetcher._fetch_a_share_daily_history_from_tushare",
        lambda *_args: pytest.fail("final-close history must not call Tushare"),
    )

    result = fetch_final_close_history_df("600519", date(2026, 6, 3), min_periods=2)

    storage.load_history_data_stock.assert_called_once_with(
        stock_id="600519",
        period=PeriodType.DAILY,
        adjust=AdjustType.HFQ,
        start_date="2026-05-28",
        end_date="2026-06-03",
    )
    assert list(result["日期"]) == ["2026-06-02", "2026-06-03"]
```

Use the production calendar multiplier to derive the expected start date, rather than introducing a separate window policy. Add a second test for an empty or too-short storage result returning `None`.

- [ ] **Step 2: Run the focused price-fetcher test and verify failure**

Run: `uv run pytest test/monitor/test_price_fetcher.py -v`

Expected: FAIL with an import error for `fetch_final_close_history_df`.

- [ ] **Step 3: Implement the storage-only helper**

```python
def fetch_final_close_history_df(
    stock_code: str, as_of_date: date, min_periods: int
) -> Optional[pd.DataFrame]:
    start_day = as_of_date - timedelta(days=min_periods * _CALENDAR_MULTIPLIER)
    df = get_storage().load_history_data_stock(
        stock_id=stock_code,
        period=PeriodType.DAILY,
        adjust=AdjustType.HFQ,
        start_date=start_day.isoformat(),
        end_date=as_of_date.isoformat(),
    )
    if df is None or len(df) < min_periods:
        return None
    return df.sort_values(by=COL_DATE).reset_index(drop=True)
```

Do not modify `fetch_history_df`: its A-share TuShare preference is legacy behavior that must remain unchanged.

- [ ] **Step 4: Run focused price-fetcher tests**

Run: `uv run pytest test/monitor/test_price_fetcher.py -v`

Expected: PASS, including the existing test that `fetch_history_df` prefers TuShare daily A-share data.

- [ ] **Step 5: Commit the storage retrieval change**

```bash
git add monitor/price_fetcher.py test/monitor/test_price_fetcher.py
git commit -m "feat: load final close history from HFQ storage"
```

### Task 3: Route Final-Close Targets Through The Monitor Runner

**Files:**
- Modify: `monitor/monitor_runner.py:1-162`
- Test: `test/monitor/test_monitor_runner.py`

**Interfaces:**
- Consumes: `fetch_final_close_history_df(stock_code: str, as_of_date: date, min_periods: int) -> Optional[pd.DataFrame]` and the `ConditionResult` contract from Task 1.
- Produces: `run_monitor(frequency: str = "daily", workflow: str | None = None, as_of_date: date | None = None) -> MonitorSummary` with deterministic final-close behavior.

- [ ] **Step 1: Write failing runner tests**

```python
def test_final_close_runner_uses_hfq_storage_and_never_fetches_realtime_price():
    target = _make_target(condition={"type": "close_cross_ma", "direction": "above", "period": 20})
    history = pd.DataFrame({"日期": pd.date_range(end="2026-06-03", periods=21), "收盘": [10.0] * 20 + [11.0]})
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", return_value=history) as fetch_final,
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily", as_of_date=date(2026, 6, 3))

    fetch_final.assert_called_once_with("600519", date(2026, 6, 3), min_periods=21)
    realtime.assert_not_called()
    email.assert_called_once()
    assert summary.triggered == 1


def test_final_close_stale_bar_preserves_state_and_sends_no_email():
    target = _make_target(last_state=True, condition={"type": "close_cross_ma", "direction": "above", "period": 20})
    stale_history = pd.DataFrame({"日期": pd.date_range("2026-05-05", periods=21), "收盘": [10.0] * 20 + [11.0]})
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", return_value=stale_history),
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily", as_of_date=date(2026, 6, 3))

    realtime.assert_not_called()
    email.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()
    assert summary.skipped == 1
```

Add tests for a non-A target and missing close values returning skipped/no-email/no-state-update. Retain and run the existing tests proving `price_cross_ma` consumes realtime pricing when present and falls back to its history close when realtime is missing.

- [ ] **Step 2: Run focused runner tests and verify failure**

Run: `uv run pytest test/monitor/test_monitor_runner.py -v`

Expected: FAIL because the runner has no `as_of_date` parameter or final-close retrieval path.

- [ ] **Step 3: Implement final-close dispatch and date validation**

Add `as_of_date: date | None = None` to `run_monitor`. For `close_cross_ma`, require `frequency == "daily"` and `target.market == "A"`; otherwise set the result to `INSUFFICIENT_DATA` without calling any provider. Resolve omitted dates with `datetime.now(ZoneInfo("Asia/Shanghai")).date()`.

For valid final-close targets, call `fetch_final_close_history_df(target.stock_code, evaluation_date, min_periods=period + 1)`. Parse `COL_DATE` using `pd.to_datetime(..., errors="coerce")`; return `INSUFFICIENT_DATA` if parsing fails or the final normalized date is not `evaluation_date`. Pass the validated history to `evaluate_condition` with `current_price=None`. For an alert, extract the current close from the final HFQ row and pass it to `_send_alert`.

Keep all existing `_build_history_for_condition`, `fetch_current_price`, `_resolve_current_price`, and `change_pct` logic for every non-`close_cross_ma` condition unchanged. Preserve the existing early `INSUFFICIENT_DATA` `continue`, which guarantees no state mutation or email.

- [ ] **Step 4: Run focused runner and monitor regression tests**

Run: `uv run pytest test/monitor/test_monitor_runner.py test/monitor/test_condition.py test/monitor/test_price_fetcher.py -v`

Expected: PASS. Confirm legacy realtime `price_cross_ma` tests remain green and final-close insufficient-data tests leave storage state untouched.

- [ ] **Step 5: Commit the runner integration**

```bash
git add monitor/monitor_runner.py test/monitor/test_monitor_runner.py
git commit -m "feat: evaluate final close MA crossovers"
```

### Task 4: Forward Airflow Business Date And Document The New Condition

**Files:**
- Modify: `dags/monitor_stock_daily.py:3-38`
- Modify: `docs/stock_monitor.md:17-20`
- Test: `test/dags/test_monitor_stock_daily.py`

**Interfaces:**
- Consumes: `dags.common_dags.LOCAL_TZ` and `run_monitor(frequency="daily", as_of_date: date | None = None)`.
- Produces: `run_daily_monitor(**context) -> str` forwards the China-local `data_interval_end.date()` to the runner while retaining the existing DAG objects and edges.

- [ ] **Step 1: Write a failing DAG forwarding test**

```python
def test_run_daily_monitor_forwards_china_local_interval_end(monkeypatch, monitor_stock_daily_module):
    monitor = MagicMock(return_value=SimpleNamespace(total=1, triggered=0, skipped=0, errors=0))
    monkeypatch.setattr("monitor.monitor_runner.run_monitor", monitor)
    monkeypatch.setattr("monitor_stock_daily.is_a_market_open_today", lambda: True)

    interval_end = datetime(2026, 6, 3, 16, 30, tzinfo=ZoneInfo("UTC"))
    monitor_stock_daily_module.run_daily_monitor(data_interval_end=interval_end)

    monitor.assert_called_once_with(frequency="daily", as_of_date=date(2026, 6, 4))
```

Also retain `test_daily_monitor_has_no_forecast_sync_upstream` and add an assertion that the operator task IDs and dependency edges remain exactly as currently defined.

- [ ] **Step 2: Run the daily-DAG test and verify failure**

Run: `uv run pytest test/dags/test_monitor_stock_daily.py -v`

Expected: FAIL because `run_daily_monitor` does not forward `as_of_date`.

- [ ] **Step 3: Implement China-local evaluation-date resolution**

Import `date` and `LOCAL_TZ`. Add a local helper that uses `context["data_interval_end"]` when present, converting Airflow-compatible datetime values with `.in_timezone(LOCAL_TZ).date()` and standard timezone-aware datetimes with `.astimezone(LOCAL_TZ).date()`. Fall back to `logical_date`/`execution_date` converted to `LOCAL_TZ`, then `datetime.now(LOCAL_TZ).date()`.

Call:

```python
summary = run_monitor(frequency="daily", as_of_date=_monitor_as_of_date(context))
```

Do not change the DAG declaration, task declarations, schedules, or `>>` edges. Add a concise `close_cross_ma` documentation bullet stating it is A-share daily only, reads final storage HFQ bars through the monitor business date, requires a real MA20 upward crossover, and preserves state when data is insufficient or stale.

- [ ] **Step 4: Run focused DAG and documentation-adjacent monitor tests**

Run: `uv run pytest test/dags/test_monitor_stock_daily.py test/monitor/test_monitor_runner.py -v`

Expected: PASS. The graph tests still show `run_daily_monitor` has no upstream forecast-sync task.

- [ ] **Step 5: Run final project checks for the changed surface**

Run: `uv run ruff format --check monitor/condition.py monitor/condition_validation.py monitor/monitor_target_service.py monitor/price_fetcher.py monitor/monitor_runner.py dags/monitor_stock_daily.py test/monitor/test_condition.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/test_price_fetcher.py test/monitor/test_monitor_runner.py test/dags/test_monitor_stock_daily.py`

Expected: PASS.

Run: `uv run ruff check monitor/condition.py monitor/condition_validation.py monitor/monitor_target_service.py monitor/price_fetcher.py monitor/monitor_runner.py dags/monitor_stock_daily.py test/monitor/test_condition.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/test_price_fetcher.py test/monitor/test_monitor_runner.py test/dags/test_monitor_stock_daily.py`

Expected: PASS.

Run: `uv run mypy monitor/condition.py monitor/condition_validation.py monitor/monitor_target_service.py monitor/price_fetcher.py monitor/monitor_runner.py dags/monitor_stock_daily.py`

Expected: PASS or only pre-existing diagnostics outside these files.

- [ ] **Step 6: Commit DAG forwarding and documentation**

```bash
git add dags/monitor_stock_daily.py docs/stock_monitor.md test/dags/test_monitor_stock_daily.py
git commit -m "feat: forward daily monitor evaluation date"
```

## Final Verification

- [ ] Run: `uv run pytest test/monitor/test_condition.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/test_price_fetcher.py test/monitor/test_monitor_runner.py test/dags/test_monitor_stock_daily.py -v`

Expected: PASS with the final-close, legacy-condition, storage-only, state-preservation, and DAG-topology contracts covered.

- [ ] Run: `git status --short`

Expected: only unrelated pre-existing workspace artifacts remain untracked; all Issue 59 implementation files are committed.
