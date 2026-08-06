# Post-Close Forecast SSF MA20 Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separately scheduled 20:00 post-close DAG that validates finalized daily bars, synchronizes forecast/SSF workflow targets, evaluates only those targets, and blocks newly blackroom-banned stocks from sending alerts.

**Architecture:** Keep `monitor_stock_daily` unchanged. Add a focused completeness service that validates the logical A-share trading day from the daily-history DAG's Redis aggregate, extend storage with workflow-target query and atomic blackroom-disable primitives, then extend `run_monitor` with an optional durable workflow filter and workflow-specific alert guard. A new three-task Airflow DAG connects these services; `ForecastSSFMonitorSyncService` remains the regular candidate mutation boundary and supplies the synchronization summary.

**Tech Stack:** Python 3.11+, Airflow `DAG`/`PythonOperator`, pandas, existing SQLAlchemy storage helpers, pytest, unittest mocks, Ruff, and mypy.

## Global Constraints

- Use `uv run` for all Python and pytest commands.
- Preserve `monitor_stock_daily` schedule, dependencies, retries, task boundaries, and SLA.
- Do not make live provider, database, Airflow, or email calls in tests.
- Workflow ownership is `workflow: "forecast_ssf_ma20"`; only daily targets with that owner may be evaluated by the new workflow.
- A blackroom lookup failure is a monitor error; an active ban suppresses email and disables the workflow target.
- Triggered state is persisted only after email delivery succeeds.
- Candidate synchronization systemic failures must occur before candidate or target mutation, as enforced by the existing synchronizer.
- Do not modify unrelated worktree changes in `pyproject.toml`, `test/download/test_download_manager.py`, or `data/`.

---

## File Map

- Create: `monitor/daily_bar_completeness.py` — trading-day and finalized-bar verification boundary that reads the existing daily-history Redis aggregate.
- Create: `dags/forecast_ssf_ma20_post_close.py` — additive 20:00 DAG and task callables.
- Modify: `monitor/monitor_runner.py` — optional workflow filtering, pre-email blackroom check, evidence enrichment, and post-email state update semantics.
- Modify: `storage/storage_db.py` — workflow-filtered target query, target-linked candidate lookup, and atomic email-time blackroom disable transition.
- Create: `test/monitor/test_daily_bar_completeness.py` — completeness service tests with fake storage and market-calendar responses.
- Modify: `test/monitor/test_monitor_runner.py` — workflow filtering, blackroom, evidence, and email-failure tests.
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py` — storage primitive contract tests.
- Create: `test/dags/test_forecast_ssf_ma20_post_close.py` — DAG import, schedule, ordering, skip/failure short-circuit, and summary tests.
- Modify: `docs/stock_monitor.md` — document the new 20:00 workflow and operational summary after implementation is verified.

## Interfaces

- `verify_daily_bar_completeness(as_of_date: date, redis_client: Any = None) -> dict[str, Any]` returns a JSON-serializable result containing `trade_date`, `is_trading_day`, and `complete`; it raises on a trading-day missing, stale, warning, malformed, or failed daily-history aggregate.
- `run_monitor(frequency: str = "daily", workflow: str | None = None) -> MonitorSummary` preserves the old all-target behavior when `workflow is None` and filters by durable `target.workflow` otherwise.
- `StorageDb.load_monitor_targets(frequency: str | None = None, workflow: str | None = None) -> list[Any]` selects enabled monitor targets and applies the owner filter when supplied.
- `StorageDb.disable_forecast_ssf_target_for_blackroom(target_id: int, reason: str) -> bool` atomically disables the linked `forecast_ssf_ma20` target and records candidate state `blackroom` with the prior evidence augmented by lifecycle data.
- `sync_forecast_ssf_targets(**context) -> dict[str, Any]` returns the synchronization summary needed by the downstream monitor task through Airflow XCom.
- `run_forecast_ssf_daily_monitor(**context) -> dict[str, Any]` returns `daily_bar`, `synchronization`, and `monitor` summary sections and raises when the monitor reports errors.

### Task 1: Add A-Share Daily-Bar Completeness Service

**Files:**
- Create: `monitor/daily_bar_completeness.py`
- Test: `test/monitor/test_daily_bar_completeness.py`

**Interfaces:**
- Consumes: logical `date`, `stock.market.is_a_share_trade_date`, and Redis key `REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY` written by `dags/download_stock_history_daily.py`.
- Produces: `verify_daily_bar_completeness(as_of_date, redis_client=None)` for the DAG.

- [ ] **Step 1: Write failing tests for non-trading-day skip semantics and successful completeness.**

```python
def test_non_trading_day_returns_skip_result(monkeypatch):
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: False)
    result = completeness.verify_daily_bar_completeness(date(2026, 8, 8), redis_client=MagicMock())
    assert result == {"trade_date": "2026-08-08", "is_trading_day": False, "complete": False, "status": "skipped"}


def test_complete_trading_day_returns_success(monkeypatch):
    redis_client = MagicMock()
    redis_client.get.return_value = '{"date":"2026-08-06","result":"success","status":"success","missing_symbols":[]}'
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: True)
    result = completeness.verify_daily_bar_completeness(date(2026, 8, 6), redis_client=redis_client)
    assert result["complete"] is True
    assert result["trade_date"] == "2026-08-06"


def test_incomplete_trading_day_raises_before_workflow_mutation(monkeypatch):
    redis_client = MagicMock()
    redis_client.get.return_value = '{"date":"2026-08-06","result":"success","status":"warning","missing_symbols":["600001"]}'
    monkeypatch.setattr(completeness, "is_a_share_trade_date", lambda _: True)
    with pytest.raises(RuntimeError, match="daily bars incomplete"):
        completeness.verify_daily_bar_completeness(date(2026, 8, 6), redis_client=redis_client)
```

- [ ] **Step 2: Run the focused tests and verify they fail for the missing module/API.**

Run: `uv run pytest test/monitor/test_daily_bar_completeness.py -q`

Expected: FAIL because `monitor.daily_bar_completeness` and its verification boundary do not exist.

- [ ] **Step 3: Implement the minimal service and storage adapter.**

Use `is_a_share_trade_date(as_of_date)` to determine whether the date is an A-share trading day. Return a skipped result for non-trading days. On trading days read and JSON-decode `REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY`; require exact date equality, `result == "success"`, `status == "success"`, and an empty `missing_symbols` list. Raise `RuntimeError` with decoded provider evidence for a missing, malformed, stale, warning, or failed aggregate. Do not perform candidate or target writes in this module.

- [ ] **Step 4: Run the focused tests and lint the new module.**

Run: `uv run pytest test/monitor/test_daily_bar_completeness.py -q`

Expected: PASS.

Run: `uv run ruff check monitor/daily_bar_completeness.py test/monitor/test_daily_bar_completeness.py`

Expected: PASS.

- [ ] **Step 5: Commit the completeness boundary.**

```bash
git add monitor/daily_bar_completeness.py test/monitor/test_daily_bar_completeness.py
git commit -m "Add daily bar completeness verification"
```

### Task 2: Add Workflow Storage Primitives

**Files:**
- Modify: `storage/storage_db.py:1552-1560, 2301-2310`
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py`

**Interfaces:**
- Consumes: `StockMonitorTarget`, `ForecastSSFCandidate`, and the existing workflow ownership identity.
- Produces: workflow-filtered enabled target loading, candidate lookup by monitor target ID, and `disable_forecast_ssf_target_for_blackroom`.

- [ ] **Step 1: Write failing storage contract tests.**

```python
def test_load_monitor_targets_filters_enabled_targets_by_workflow(sqlite_storage):
    workflow_target = _create_target(sqlite_storage, workflow="forecast_ssf_ma20")
    _create_target(sqlite_storage, workflow=None)
    assert [target.id for target in sqlite_storage.load_monitor_targets("daily", "forecast_ssf_ma20")] == [workflow_target.id]


def test_blackroom_disable_updates_target_and_linked_candidate_atomically(sqlite_storage):
    target, candidate = _create_linked_forecast_ssf_target(sqlite_storage, enabled=True, state="eligible")
    assert sqlite_storage.disable_forecast_ssf_target_for_blackroom(target.id, "active_blackroom") is True
    assert sqlite_storage.get_monitor_target(target.id).enabled is False
    saved = sqlite_storage.get_forecast_ssf_candidate_for_target(target.id)
    assert saved.state == "blackroom"
    assert saved.state_reason == "active_blackroom"
    assert saved.evidence["lifecycle"]["state"] == "blackroom"
```

- [ ] **Step 2: Run the targeted storage tests to verify they fail.**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -q`

Expected: FAIL because the workflow filter, candidate lookup, and atomic blackroom primitive do not exist.

- [ ] **Step 3: Implement minimal storage methods.**

Extend `load_monitor_targets` and its underlying list query with optional `workflow`; preserve calls that pass only `frequency`. Add `get_forecast_ssf_candidate_for_target(target_id)` returning the linked candidate or `None`. Add `disable_forecast_ssf_target_for_blackroom(target_id, reason)` that opens one transaction, verifies the target is the `forecast_ssf_ma20` owner, disables it, loads the linked candidate, updates it to `blackroom` with `state_reason=reason`, preserves existing evidence, and writes lifecycle date/state/reason/previous-state evidence. Return `False` for a missing target or unlinked candidate; never mutate a manual target.

- [ ] **Step 4: Run storage tests and static checks.**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -q`

Expected: PASS.

Run: `uv run ruff check storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py`

Expected: PASS.

- [ ] **Step 5: Commit the storage primitives.**

```bash
git add storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py
git commit -m "Add workflow monitor storage operations"
```

### Task 3: Harden Workflow-Scoped Monitor Alerts

**Files:**
- Modify: `monitor/monitor_runner.py:20-156`
- Modify: `test/monitor/test_monitor_runner.py`

**Interfaces:**
- Consumes: `target.workflow`, `BlackroomService.is_banned`, `StorageDb.disable_forecast_ssf_target_for_blackroom`, and `StorageDb.get_forecast_ssf_candidate_for_target`.
- Produces: `run_monitor(frequency="daily", workflow="forecast_ssf_ma20")` and workflow alert bodies containing available candidate evidence.

- [ ] **Step 1: Add failing tests for workflow filtering and target metadata.**

```python
def test_run_monitor_filters_by_workflow():
    owned = _make_target(id=1)
    owned.workflow = "forecast_ssf_ma20"
    manual = _make_target(id=2)
    manual.workflow = None
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [owned, manual]
    with patch("monitor.monitor_runner.get_storage", return_value=storage), \
         patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0), \
         patch("monitor.monitor_runner.fetch_history_df", return_value=None), \
         patch("monitor.monitor_runner.send_email"):
        summary = run_monitor(workflow="forecast_ssf_ma20")
    assert summary.total == 1
    assert storage.load_monitor_targets.call_args.kwargs == {"frequency": "daily", "workflow": "forecast_ssf_ma20"}
```

- [ ] **Step 2: Add failing tests for the pre-email blackroom guard.**

```python
def test_banned_workflow_target_is_disabled_without_email():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    storage.get_forecast_ssf_candidate_for_target.return_value = _candidate_evidence()
    blackroom = MagicMock()
    blackroom.is_banned.return_value = {"success": True, "data": {"banned": True}}
    with patch("monitor.monitor_runner.get_storage", return_value=storage), \
         patch("monitor.monitor_runner.BlackroomService", return_value=blackroom), \
         patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0), \
         patch("monitor.monitor_runner.fetch_history_df", return_value=None), \
         patch("monitor.monitor_runner.send_email") as email:
        summary = run_monitor(workflow="forecast_ssf_ma20")
    email.assert_not_called()
    storage.disable_forecast_ssf_target_for_blackroom.assert_called_once_with(target.id, "active_blackroom")
    assert summary.skipped == 1
```

- [ ] **Step 3: Add failing tests for evidence enrichment and email failure.**

Assert the sent body contains `report_end_date`, `p_change_min`, forecast `ann_date`, `matched_holder`, and shareholder `ann_date` from the candidate evidence. Make `send_email` raise and assert `update_monitor_target_state` is not called and `summary.errors == 1`.

- [ ] **Step 4: Run the new focused tests to verify they fail.**

Run: `uv run pytest test/monitor/test_monitor_runner.py -q`

Expected: FAIL because `run_monitor` has no workflow argument and no pre-email workflow guard/evidence path.

- [ ] **Step 5: Implement the minimal runner changes.**

Add `workflow: str | None = None` to `run_monitor`. Prefer the storage query's workflow filter when available; retain a defensive `target.workflow == workflow` filter for fake/legacy storage results. Instantiate `BlackroomService` only for workflow-scoped runs. Immediately before `_send_alert`, call `is_banned(target.stock_code, target.market)` and treat unsuccessful responses as errors. For a successful ban, disable the target through the existing target update boundary and skip state/alert updates. Load the linked forecast candidate evidence through the existing storage API, pass it into `_send_alert`, append only present evidence fields, call `send_email`, and update the triggered state afterward. Preserve current non-workflow behavior and auto-reset semantics.

- [ ] **Step 6: Run all monitor tests and lint/type-check touched modules.**

Run: `uv run pytest test/monitor/test_monitor_runner.py test/monitor/test_forecast_ssf_monitor_sync.py -q`

Expected: PASS.

Run: `uv run ruff check monitor/monitor_runner.py test/monitor/test_monitor_runner.py`

Expected: PASS.

- [ ] **Step 7: Commit the workflow alert integration.**

```bash
git add monitor/monitor_runner.py test/monitor/test_monitor_runner.py
git commit -m "Guard workflow alerts against blackroom bans"
```

### Task 4: Add The 20:00 Post-Close DAG

**Files:**
- Create: `dags/forecast_ssf_ma20_post_close.py`
- Create: `test/dags/test_forecast_ssf_ma20_post_close.py`
- Modify: `docs/stock_monitor.md`

**Interfaces:**
- Consumes: `verify_daily_bar_completeness`, `ForecastSSFMonitorSyncService.sync`, and `run_monitor(frequency="daily", workflow="forecast_ssf_ma20")`.
- Produces: Airflow DAG `forecast_ssf_ma20_post_close` with task IDs `verify_daily_bar_completeness`, `sync_forecast_ssf_targets`, and `run_forecast_ssf_daily_monitor`.

- [ ] **Step 1: Write failing DAG import, schedule, and dependency tests.**

```python
def test_post_close_dag_schedule_and_order(post_close_module):
    tasks = {task.task_id: task for task in FakePythonOperator.instances}
    assert post_close_module.dag.kwargs["schedule"] == "0 20 * * *"
    assert post_close_module.dag.kwargs["max_active_runs"] == 1
    assert tasks["sync_forecast_ssf_targets"].upstream == [tasks["verify_daily_bar_completeness"]]
    assert tasks["run_forecast_ssf_daily_monitor"].upstream == [tasks["sync_forecast_ssf_targets"]]
```

- [ ] **Step 2: Write failing callable tests for skip, short-circuit, empty result, and structured summary.**

Mock the completeness function to return `status="skipped"` and assert `AirflowSkipException`; make it raise and assert sync is never constructed; return a valid empty sync result and a zero-count `MonitorSummary`, then assert the final result has `daily_bar`, `synchronization`, and `monitor` sections and does not raise.

- [ ] **Step 3: Run focused DAG tests to verify they fail.**

Run: `uv run pytest test/dags/test_forecast_ssf_ma20_post_close.py -q`

Expected: FAIL because the new DAG module and task callables do not exist.

- [ ] **Step 4: Implement the additive DAG.**

Follow `dags/monitor_stock_daily.py` bootstrap and `get_default_args` conventions. Resolve the logical date from `logical_date`/`execution_date`, call the completeness service, skip non-trading days, push the completeness result through the task return value, pull the synchronization result from XCom in the monitor callable, and serialize all summary sections with `json.dumps(..., ensure_ascii=False)`. Raise on failed service responses or monitor `errors > 0`. Set `schedule="0 20 * * *"`, `catchup=False`, `max_active_runs=1`, and a focused tag such as `forecast_ssf_ma20`.

- [ ] **Step 5: Update operator documentation.**

Add a short section to `docs/stock_monitor.md` documenting the DAG name, 20:00 schedule, ordered stages, valid-empty behavior, and the structured summary fields. Do not alter existing CLI or workflow lifecycle semantics.

- [ ] **Step 6: Run DAG tests, relevant regression tests, and lint.**

Run: `uv run pytest test/dags/test_forecast_ssf_ma20_post_close.py test/dags/test_monitor_stock_daily.py test/monitor/test_monitor_runner.py -q`

Expected: PASS.

Run: `uv run ruff check dags/forecast_ssf_ma20_post_close.py monitor/daily_bar_completeness.py monitor/monitor_runner.py test/dags/test_forecast_ssf_ma20_post_close.py test/monitor/test_daily_bar_completeness.py test/monitor/test_monitor_runner.py`

Expected: PASS.

- [ ] **Step 7: Commit the DAG and documentation.**

```bash
git add dags/forecast_ssf_ma20_post_close.py test/dags/test_forecast_ssf_ma20_post_close.py docs/stock_monitor.md
git commit -m "Add post-close forecast SSF MA20 DAG"
```

### Task 5: Full Verification And Documentation Review

**Files:**
- Modify only files already listed above if verification exposes a defect.

- [ ] **Step 1: Run the focused subsystem suite.**

Run: `uv run pytest test/dags/test_forecast_ssf_ma20_post_close.py test/dags/test_monitor_stock_daily.py test/monitor/test_daily_bar_completeness.py test/monitor/test_monitor_runner.py test/monitor/test_forecast_ssf_monitor_sync.py -q`

Expected: PASS.

- [ ] **Step 2: Run repository formatting, lint, and type checks.**

Run: `uv run ruff format .`

Expected: formatter completes; inspect that only intended files change.

Run: `uv run ruff check .`

Expected: PASS.

Run: `uv run mypy`

Expected: PASS, or report pre-existing unrelated errors without changing unrelated files.

- [ ] **Step 3: Run the full test suite.**

Run: `uv run pytest test`

Expected: PASS.

- [ ] **Step 4: Review the final diff and worktree.**

Run: `git status --short && git diff HEAD~4..HEAD -- dags monitor storage test docs/stock_monitor.md`

Confirm `monitor_stock_daily.py` is unchanged, unrelated user files are not staged, the new DAG is scheduled at 20:00, and all issue acceptance criteria map to tested behavior.

- [ ] **Step 5: Run the repository documentation workflow if preparing an integration commit.**

Use the repository `update_doc` skill to inspect current changes and update only affected documentation before any later commit or merge flow.

## Verification Matrix

- Daily-bar completeness: `test_daily_bar_completeness.py` and DAG short-circuit tests.
- Ordered post-close orchestration: `test_forecast_ssf_ma20_post_close.py` dependency assertions.
- Structured empty success: final callable test with empty synchronization data.
- Systemic sync failure before mutation/evaluation: DAG callable and existing sync tests.
- Per-stock deferrals visible: existing `test_forecast_ssf_monitor_sync.py` regression tests plus returned synchronization summary.
- Workflow-only evaluation: runner workflow filter test.
- Pre-email blackroom recheck: runner banned and lookup-failure tests.
- Evidence-rich alert: runner email body assertions.
- Email failure state preservation: runner exception test.
- Existing DAG stability: `test_monitor_stock_daily.py` schedule/dependency tests.
