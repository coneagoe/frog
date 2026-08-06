# Forecast SSF Sync-Only Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 15:05 forecast SSF DAG only synchronize candidate-derived monitor targets, while the existing 15:30 daily monitor remains the sole MA20 evaluator and alert sender.

**Architecture:** Replace the three-stage 20:00 post-close DAG with one 15:05 candidate-sync task. Synchronization physically deletes only owned `forecast_ssf_ma20` daily monitor targets that are conclusively ineligible, while retaining candidate evidence. Extend ordinary unfiltered daily monitoring so any workflow-owned target receives the same blackroom guard and evidence enrichment previously limited to explicitly scoped runs.

**Tech Stack:** Python 3.11+, Airflow `DAG`/`PythonOperator`, SQLAlchemy storage, pytest, unittest mocks, Ruff, and mypy.

## Global Constraints

- Use `uv run` for all Python and pytest commands.
- The new DAG is named `forecast_ssf_ma20_sync`, scheduled at `5 15 * * *`, with `catchup=False` and `max_active_runs=1`.
- The new DAG only synchronizes candidates; it does not validate daily bars, calculate MA20, evaluate monitor targets, or send email.
- Preserve `monitor_stock_daily` schedule `30 15 * * *`, retries, SLA, monitor task, and countdown path; remove only its forecast SSF synchronization task and dependency.
- A conclusively ineligible, blackroom-blocked, delisted, superseded, or absent workflow candidate physically deletes only its owned daily monitor target; its candidate record and evidence remain.
- Missing, stale, or failed shareholder evidence remains `deferred` and preserves an existing workflow target.
- Every `forecast_ssf_ma20` target receives pre-email blackroom rechecks and evidence enrichment even during ordinary `run_monitor(frequency="daily")`; manual targets preserve old behavior.
- Triggered state is persisted only after email delivery succeeds.
- Tests mock all provider, database, Airflow, and email integrations.

---

## File Map

- Modify: `dags/forecast_ssf_ma20_post_close.py` — rename/rework to one 15:05 candidate sync DAG.
- Create: `dags/forecast_ssf_ma20_sync.py` — final DAG path; remove obsolete post-close module once tests use the final module.
- Modify: `dags/monitor_stock_daily.py` — remove only forecast SSF sync callable, operator, and upstream edge.
- Modify: `monitor/forecast_ssf_monitor_sync.py` — replace owned-target disable transitions with atomic candidate-update-and-target-delete transitions.
- Modify: `storage/storage_db.py` — add atomic delete-with-candidate-transition and email-time delete-with-blackroom-transition helpers.
- Modify: `monitor/monitor_runner.py` — identify target-level workflow ownership independently of the optional runner filter.
- Modify: `test/dags/test_forecast_ssf_ma20_post_close.py` — replace with tests for the final sync-only DAG module.
- Modify: `test/dags/test_monitor_stock_daily.py` — assert no forecast sync task/edge and unchanged monitor/countdown behavior.
- Modify: `test/monitor/test_forecast_ssf_monitor_sync.py` — assert owned target deletion and candidate evidence retention.
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py` — assert atomic deletion and candidate transition behavior.
- Modify: `test/monitor/test_monitor_runner.py` — assert unfiltered workflow target blackroom/evidence behavior without affecting manual targets.
- Modify: `docs/stock_monitor.md` — document the 15:05 sync-only DAG and target deletion lifecycle.

## Interfaces

- `ForecastSSFMonitorSyncService.sync(as_of_date: date) -> dict[str, Any]` returns its existing structured summary, with `deleted` replacing `disabled` for physical target removal.
- `StorageDb.delete_forecast_ssf_target_with_candidate_transition(target_id: int, state: str, reason: str, evidence: dict[str, Any]) -> bool` atomically deletes the owned target and persists its linked candidate state/evidence with `monitor_target_id=None`.
- `StorageDb.delete_forecast_ssf_target_for_blackroom(target_id: int, reason: str) -> bool` atomically deletes the owned target and persists the linked candidate `blackroom` transition.
- `run_monitor(frequency: str = "daily", workflow: str | None = None) -> MonitorSummary` applies workflow alert protection whenever `target.workflow == "forecast_ssf_ma20"`, whether or not the caller supplies a filter.
- `sync_forecast_ssf_targets(**context: Any) -> str` returns the JSON-serialized synchronization result or raises for a failed result.

### Task 1: Add Atomic Workflow Target Deletion

**Files:**
- Modify: `storage/storage_db.py`
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py`

**Interfaces:**
- Consumes: owned `StockMonitorTarget`, linked `ForecastSSFCandidate`, lifecycle evidence, and SQLAlchemy transaction handling.
- Produces: `delete_forecast_ssf_target_with_candidate_transition(...)` and `delete_forecast_ssf_target_for_blackroom(...)`.

- [ ] **Step 1: Write failing storage tests for deletion transitions.**

```python
def test_delete_transition_removes_owned_target_and_retains_candidate(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, _candidate = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    evidence = {"lifecycle": {"state": "ineligible", "reason": "ssf_holder_not_found"}}

    assert db.delete_forecast_ssf_target_with_candidate_transition(
        target.id, "ineligible", "ssf_holder_not_found", evidence
    ) is True

    assert db.get_monitor_target(target.id) is None
    candidate = db.get_forecast_ssf_candidate_for_target(target.id)
    assert candidate is None
    saved = db.list_forecast_ssf_candidates()[0]
    assert (saved.state, saved.state_reason, saved.monitor_target_id) == ("ineligible", "ssf_holder_not_found", None)


def test_blackroom_delete_rolls_back_candidate_when_target_delete_fails(tmp_path, monkeypatch):
    db = _sqlite_storage(tmp_path)
    target, _candidate = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    monkeypatch.setattr(db, "_delete_workflow_target_in_transaction", MagicMock(side_effect=RuntimeError("delete failed")))

    with pytest.raises(RuntimeError, match="delete failed"):
        db.delete_forecast_ssf_target_for_blackroom(target.id, "active_blackroom")

    assert db.get_monitor_target(target.id) is not None
    assert db.list_forecast_ssf_candidates()[0].state == "eligible"
```

- [ ] **Step 2: Run tests to verify the deletion APIs are missing.**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -q`

Expected: FAIL because the deletion transition APIs do not exist.

- [ ] **Step 3: Implement atomic target deletion and candidate transition.**

Within one SQLAlchemy transaction, verify the target exists and has `workflow == "forecast_ssf_ma20"`; reject duplicate candidate links as the existing code does; update the linked candidate state, reason, evidence, and `monitor_target_id=None`; then delete the target. Return `False` for a missing, unowned, or unlinked target. Make `delete_forecast_ssf_target_for_blackroom` build lifecycle evidence with `previous_state` and delegate to this primitive.

- [ ] **Step 4: Run targeted storage tests and static checks.**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -q`

Expected: PASS.

Run: `uv run ruff check storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py`

Expected: PASS.

- [ ] **Step 5: Commit the deletion primitive.**

```bash
git add storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py
```

### Task 2: Make Synchronization Delete Retired Targets

**Files:**
- Modify: `monitor/forecast_ssf_monitor_sync.py`
- Modify: `test/monitor/test_forecast_ssf_monitor_sync.py`

**Interfaces:**
- Consumes: Task 1 deletion primitive and existing candidate evidence/state decisions.
- Produces: synchronization results with `deleted` target count and no enabled target for conclusively excluded workflow candidates.

- [ ] **Step 1: Write failing deletion-behavior tests.**

```python
def test_blackroom_candidate_deletes_linked_owned_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate(target_id=17)]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    blackroom = MagicMock(is_banned=lambda *_: _blackroom(banned=True))

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    storage.delete_forecast_ssf_target_with_candidate_transition.assert_called_once()
    assert result["data"]["deleted"] == 1


def test_deferred_candidate_preserves_linked_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate(target_id=17)]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_latest_top10_floatholders.return_value = pd.DataFrame()

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())).sync(
        date(2026, 1, 20)
    )

    storage.delete_forecast_ssf_target_with_candidate_transition.assert_not_called()
```

- [ ] **Step 2: Run focused sync tests and verify they fail.**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -q`

Expected: FAIL because the synchronizer still calls the disable/upsert path for conclusive exclusions.

- [ ] **Step 3: Replace only conclusive exclusion transitions.**

For blackroom, no-SSF holder, delisted/unlisted, reporting-period supersession, and qualified-universe retirement, invoke the Task 1 deletion primitive when the candidate link matches the owned target. Persist the candidate with `monitor_target_id=None` when no target exists or the ownership/link verification fails. Keep deferred holder-query, missing-disclosure, and stale-disclosure paths target-preserving. Rename the summary count from `disabled` to `deleted`, and update tests accordingly.

- [ ] **Step 4: Run focused sync and storage regression tests.**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit synchronization deletion behavior.**

```bash
git add monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
```

### Task 3: Apply Workflow Protection In Ordinary Monitor Runs

**Files:**
- Modify: `monitor/monitor_runner.py`
- Modify: `test/monitor/test_monitor_runner.py`

**Interfaces:**
- Consumes: `target.workflow`, Task 1 `delete_forecast_ssf_target_for_blackroom`, and candidate evidence lookup.
- Produces: workflow blackroom protection and evidence enrichment for both filtered and ordinary daily runs.

- [ ] **Step 1: Write failing unfiltered-run tests.**

```python
def test_unfiltered_daily_run_rechecks_workflow_target_blackroom_before_email():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    blackroom = MagicMock(is_banned=lambda *_: {"success": True, "data": {"banned": True}})

    with patch("monitor.monitor_runner.get_storage", return_value=storage), \
         patch("monitor.monitor_runner.BlackroomService", return_value=blackroom), \
         patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0), \
         patch("monitor.monitor_runner.fetch_history_df", return_value=None), \
         patch("monitor.monitor_runner.send_email") as email:
        summary = run_monitor(frequency="daily")

    email.assert_not_called()
    storage.delete_forecast_ssf_target_for_blackroom.assert_called_once_with(target.id, "active_blackroom")
    assert summary.skipped == 1


def test_unfiltered_daily_run_leaves_manual_target_without_blackroom_lookup():
    target = _make_target(last_state=False)
    target.workflow = None
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with patch("monitor.monitor_runner.get_storage", return_value=storage), \
         patch("monitor.monitor_runner.BlackroomService") as blackroom, \
         patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0), \
         patch("monitor.monitor_runner.fetch_history_df", return_value=None), \
         patch("monitor.monitor_runner.send_email"):
        run_monitor(frequency="daily")

    blackroom.assert_not_called()
```

- [ ] **Step 2: Run monitor tests and verify they fail.**

Run: `uv run pytest test/monitor/test_monitor_runner.py -q`

Expected: FAIL because current protection is enabled only when the caller supplies `workflow`.

- [ ] **Step 3: Scope guards per target, not per invocation.**

Load targets with the optional caller filter as today. For each target, set `is_forecast_ssf_workflow = target.workflow == "forecast_ssf_ma20"`; only then construct/use the blackroom service, load candidate evidence, recheck immediately before email, and call `delete_forecast_ssf_target_for_blackroom`. If deletion returns `False`, raise a monitor error instead of reporting a successful skip. Preserve manual target behavior, alert state update ordering, and automatic reset behavior.

- [ ] **Step 4: Run monitor and sync tests with static checks.**

Run: `uv run pytest test/monitor/test_monitor_runner.py test/monitor/test_forecast_ssf_monitor_sync.py -q`

Expected: PASS.

Run: `uv run ruff check monitor/monitor_runner.py test/monitor/test_monitor_runner.py`

Expected: PASS.

- [ ] **Step 5: Commit ordinary-run workflow protection.**

```bash
git add monitor/monitor_runner.py test/monitor/test_monitor_runner.py
```

### Task 4: Replace Post-Close Orchestration With 15:05 Sync

**Files:**
- Delete: `dags/forecast_ssf_ma20_post_close.py`
- Create: `dags/forecast_ssf_ma20_sync.py`
- Delete: `test/dags/test_forecast_ssf_ma20_post_close.py`
- Create: `test/dags/test_forecast_ssf_ma20_sync.py`
- Modify: `dags/monitor_stock_daily.py`
- Modify: `test/dags/test_monitor_stock_daily.py`
- Modify: `docs/stock_monitor.md`

**Interfaces:**
- Consumes: `ForecastSSFMonitorSyncService.sync(as_of_date)` and `is_a_share_trade_date(as_of_date)`.
- Produces: DAG `forecast_ssf_ma20_sync` with one task, `sync_forecast_ssf_targets`.

- [ ] **Step 1: Write failing 15:05 sync DAG tests.**

```python
def test_sync_dag_schedule_and_single_task(sync_module):
    tasks = {task.task_id: task for task in FakePythonOperator.instances}
    assert sync_module.dag.kwargs["schedule"] == "5 15 * * *"
    assert sync_module.dag.kwargs["max_active_runs"] == 1
    assert set(tasks) == {"sync_forecast_ssf_targets"}


def test_sync_task_skips_non_trading_day(monkeypatch, sync_module):
    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: False)
    service = MagicMock()
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(FakeAirflowSkipException):
        sync_module.sync_forecast_ssf_targets(logical_date=datetime(2026, 8, 8, 15, 5))

    service.assert_not_called()


def test_daily_monitor_has_no_forecast_sync_upstream(monitor_stock_daily_module):
    tasks = {task.task_id: task for task in FakePythonOperator.instances}
    assert "sync_forecast_ssf_targets" not in tasks
    assert tasks["run_daily_monitor"].upstream == []
```

- [ ] **Step 2: Run DAG tests and verify they fail.**

Run: `uv run pytest test/dags/test_forecast_ssf_ma20_sync.py test/dags/test_monitor_stock_daily.py -q`

Expected: FAIL because the old post-close DAG remains and the old daily DAG still owns the forecast sync task.

- [ ] **Step 3: Implement the sync-only DAG and remove duplicate synchronization.**

Create the new DAG with the same Airflow import bootstrap and `get_default_args` pattern. Resolve the task date from `logical_date`/`execution_date`, skip non-trading dates using `is_a_share_trade_date`, call the synchronizer, raise on `success=False`, and return `json.dumps(result, ensure_ascii=False)`. Delete the post-close DAG module and its tests. In `monitor_stock_daily.py`, delete only `sync_forecast_ssf_monitor_targets`, its `PythonOperator`, and `sync_forecast_ssf_targets_task >> daily_monitor_task`; leave schedule, monitor callable, shareholder-selling task, countdown task, and their dependency edges unchanged.

- [ ] **Step 4: Update operations documentation.**

Replace the 20:00/post-close description with `forecast_ssf_ma20_sync` at 15:05. State that it only synchronizes candidate-derived targets, that `monitor_stock_daily` scans those targets at 15:30, that conclusively ineligible workflow targets are deleted while candidate evidence remains, and that deferred evidence preserves targets.

- [ ] **Step 5: Run DAG regressions and lint.**

Run: `uv run pytest test/dags/test_forecast_ssf_ma20_sync.py test/dags/test_monitor_stock_daily.py -q`

Expected: PASS.

Run: `uv run ruff check dags/forecast_ssf_ma20_sync.py dags/monitor_stock_daily.py test/dags/test_forecast_ssf_ma20_sync.py test/dags/test_monitor_stock_daily.py`

Expected: PASS.

- [ ] **Step 6: Commit sync-only orchestration.**

```bash
git add dags/forecast_ssf_ma20_sync.py dags/monitor_stock_daily.py test/dags/test_forecast_ssf_ma20_sync.py test/dags/test_monitor_stock_daily.py docs/stock_monitor.md
```

### Task 5: Verify The Revised Workflow

**Files:**
- Modify only files listed above if verification finds a defect.

- [ ] **Step 1: Run the complete workflow-focused suite.**

Run: `uv run pytest test/dags/test_forecast_ssf_ma20_sync.py test/dags/test_monitor_stock_daily.py test/monitor/test_forecast_ssf_monitor_sync.py test/monitor/test_monitor_runner.py test/storage/test_forecast_ssf_candidate_storage.py -q`

Expected: PASS.

- [ ] **Step 2: Run repository quality checks.**

Run: `uv run ruff format .`

Expected: formatter completes; inspect that only intended files change.

Run: `uv run ruff check . && uv run mypy`

Expected: PASS.

- [ ] **Step 3: Run the full suite.**

Run: `uv run pytest test`

Expected: PASS.

- [ ] **Step 4: Review final behavior and diff.**

Run: `git status --short && git diff 601212f..HEAD -- dags monitor storage test docs/stock_monitor.md`

Confirm there is one 15:05 workflow target-mutation path, one 15:30 technical scan path, no 20:00 post-close DAG, no daily-bar-completeness dependency for candidate synchronization, physical deletion for conclusively ineligible workflow targets, and retained candidate audit evidence.
