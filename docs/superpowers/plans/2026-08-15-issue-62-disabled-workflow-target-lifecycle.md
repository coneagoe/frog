# Disabled Workflow Target Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain workflow-owned forecast SSF monitor targets through lifecycle disablement, recover the same target on requalification, and visibly fail synchronization only after independent stock transitions finish.

**Architecture:** `StorageDb` owns candidate-link validation and candidate/target mutations in a single stock transaction. `ForecastSSFMonitorSyncService` classifies lifecycle outcomes, invokes that storage boundary per stock, and aggregates persistence failures into a post-processing exception. `run_monitor` uses the same retaining-disable primitive for its single alert-time blackroom guard.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy, pytest, Ruff, mypy, PostgreSQL test container.

## Global Constraints

- Use `uv run` for Python commands; use `tools/run_tests.sh` for PostgreSQL integration coverage.
- Preserve `monitor_stock_daily` schedule, dependencies, retries, task boundary, and SLA.
- Do not change `close_cross_ma` evaluation or `price_cross_ma` behavior.
- Keep `forecast_ssf_ma20` lifecycle ownership restricted to A-share daily workflow targets.
- Do not reset an existing target's `last_state` during candidate creation, disablement, recovery, pause handling, or metadata refresh.
- Do not repair invalid historic candidate-to-target links; reject them without mutation.
- Mock external providers and blackroom collaborators in unit tests.

---

## File Structure

- `storage/storage_db.py`: transactional candidate/target lifecycle mutation and strict link validation.
- `test/storage/test_forecast_ssf_candidate_storage.py`: SQLite and PostgreSQL-compatible storage contract tests for retained links, atomic rollbacks, pauses, and edge-state preservation.
- `monitor/forecast_ssf_monitor_sync.py`: candidate lifecycle orchestration, structured per-stock errors, and partial-failure exception.
- `test/monitor/test_forecast_ssf_monitor_sync.py`: service-boundary lifecycle, recovery, deferral, and partial-failure tests.
- `monitor/monitor_runner.py`: one alert-time blackroom check and retaining-disable failure handling.
- `test/monitor/test_monitor_runner.py`: alert suppression, shared transition usage, and exactly-one-check behavior.
- `test/dags/test_forecast_ssf_ma20_sync.py`: propagation of the synchronization partial-failure signal through the existing task boundary.
- `docs/stock_monitor.md`: update only if implementation introduces a user-visible error/result contract absent from the current lifecycle documentation.

### Task 1: Make Storage Lifecycle Transitions Retaining And Atomic

**Files:**
- Modify: `storage/storage_db.py:2782-3058`
- Test: `test/storage/test_forecast_ssf_candidate_storage.py:171-369, 792-894`

**Interfaces:**
- Consumes: `ForecastSSFCandidate`, `StockMonitorTarget`, `ForecastSSFCandidateState`, and the existing `forecast_ssf_ma20` workflow identity.
- Produces: `StorageDb.transition_forecast_ssf_candidate_with_workflow_target(stock_code: str, market: str, report_end_date: date, state: str, state_reason: str, evidence: dict[str, Any], target_enabled: bool) -> Any` for existing linked candidates; it returns the retained target or raises on invalid linkage/persistence failure.
- Produces: `StorageDb.disable_forecast_ssf_target_for_blackroom(target_id: int, reason: str) -> bool`, implemented through the same transaction-local linkage contract.

- [ ] **Step 1: Write failing retention and edge-state tests**

```python
def test_lifecycle_disable_retains_target_link_and_last_state(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    db.update_monitor_target_state(target.id, True)

    updated = db.transition_forecast_ssf_candidate_with_workflow_target(
        stock_code="600001", market="A", report_end_date=date(2025, 12, 31),
        state="ineligible", state_reason="ssf_holder_not_found",
        evidence={"lifecycle": {"state": "ineligible"}}, target_enabled=False,
    )

    saved = db.get_forecast_ssf_candidate_for_target(target.id)
    assert updated.id == target.id
    assert (db.get_monitor_target(target.id).enabled, db.get_monitor_target(target.id).last_state) == (False, True)
    assert (saved.state, saved.monitor_target_id) == ("ineligible", target.id)


def test_lifecycle_transition_rejects_stale_link_without_mutation(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, candidate = _create_linked_forecast_ssf_target(db, enabled=True, state="eligible")
    db.delete_monitor_target(target.id)

    with pytest.raises(ValueError, match="linked workflow target"):
        db.transition_forecast_ssf_candidate_with_workflow_target(
            "600001", "A", candidate.report_end_date, "blackroom", "active_blackroom", {"after": True}, False
        )

    saved = db.list_forecast_ssf_candidates()[0]
    assert (saved.state, saved.monitor_target_id, saved.evidence) == ("eligible", target.id, {"forecast": {"ann_date": "2026-01-15"}})
```

- [ ] **Step 2: Run the new storage tests to verify failure**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -k 'lifecycle_disable_retains or lifecycle_transition_rejects_stale' -v`

Expected: FAIL because `transition_forecast_ssf_candidate_with_workflow_target` does not exist.

- [ ] **Step 3: Add transaction-local candidate and target validation**

```python
def transition_forecast_ssf_candidate_with_workflow_target(
    self, stock_code: str, market: str, report_end_date: date, state: str,
    state_reason: str, evidence: dict[str, Any], target_enabled: bool,
) -> Any:
    self._validate_monitor_enum_value(market, "market", MonitorMarket)
    self._validate_monitor_enum_value(state, "state", ForecastSSFCandidateState)
    self.ensure_monitor_targets_table()
    # In one session.begin() block: load the candidate by stock/market, require
    # its linked daily forecast_ssf_ma20 target, update candidate fields while
    # retaining monitor_target_id, set target.enabled unless target.paused, and flush.
```

Validate target ownership, daily frequency, and exactly one candidate referring to the target before assigning any mutable field. Raise `ValueError` for an invalid relationship. Preserve `target.last_state`; do not accept or propagate a reset flag on this existing-target transition. Keep rollback and session cleanup consistent with the existing transaction helpers.

- [ ] **Step 4: Route blackroom disablement and existing upserts through the no-reset rules**

```python
def disable_forecast_ssf_target_for_blackroom(self, target_id: int, reason: str) -> bool:
    # Load the candidate and target only inside the lifecycle transaction,
    # merge lifecycle evidence from that candidate, then request target_enabled=False.
```

Keep the public boolean result for an absent/unowned target, but reject duplicate or stale candidate linkage with an exception. Ensure `upsert_forecast_ssf_candidate_with_workflow_target()` sends `reset_last_state=False` for every existing target update; retain `False` initialization only when it creates a new target.

- [ ] **Step 5: Add storage coverage for all transition variants**

```python
@pytest.mark.parametrize("state,enabled", [("blackroom", False), ("delisted_or_unlisted", False), ("eligible", True)])
def test_lifecycle_transition_preserves_retained_target_identity(tmp_path, state, enabled):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=not enabled, state="eligible")
    db.update_monitor_target_state(target.id, True)

    updated = db.transition_forecast_ssf_candidate_with_workflow_target(
        "600001", "A", date(2025, 12, 31), state, "test_transition", {"state": state}, enabled
    )

    candidate = db.get_forecast_ssf_candidate_for_target(target.id)
    persisted = db.get_monitor_target(target.id)
    assert (updated.id, candidate.monitor_target_id) == (target.id, target.id)
    assert (persisted.enabled, persisted.last_state) == (enabled, True)


def test_lifecycle_transition_paused_target_records_candidate_but_stays_disabled(tmp_path):
    db = _sqlite_storage(tmp_path)
    target, _ = _create_linked_forecast_ssf_target(db, enabled=True, state="blackroom")
    db.set_workflow_monitor_target_paused(target.id, paused=True)

    db.transition_forecast_ssf_candidate_with_workflow_target(
        "600001", "A", date(2025, 12, 31), "paused", "manual_pause",
        {"evaluation": {"state": "eligible", "reason": "ssf_holder_match"}}, True,
    )

    persisted = db.get_monitor_target(target.id)
    assert (persisted.paused, persisted.enabled) == (True, False)
```

Also retain tests for wrong workflow, non-daily target, missing target, duplicate linked candidates, and a forced flush failure that proves candidate and target rollback together.

- [ ] **Step 6: Run focused storage tests**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -v`

Expected: PASS.

- [ ] **Step 7: Commit storage lifecycle support**

```bash
git add storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py
git commit -m "feat: retain forecast workflow targets through lifecycle changes"
```

### Task 2: Isolate Sync Failures Per Stock And Preserve Retained Targets

**Files:**
- Modify: `monitor/forecast_ssf_monitor_sync.py:32-484`
- Test: `test/monitor/test_forecast_ssf_monitor_sync.py:225-1029`

**Interfaces:**
- Consumes: `StorageDb.transition_forecast_ssf_candidate_with_workflow_target(stock_code: str, market: str, report_end_date: date, state: str, state_reason: str, evidence: dict[str, Any], target_enabled: bool) -> Any` from Task 1.
- Produces: `ForecastSSFMonitorSyncPartialFailure(summary: dict[str, Any])`, with public `.summary` and an exception message that identifies the number of failed stock transitions.
- Produces: `ForecastSSFMonitorSyncService.sync(as_of_date: date) -> dict[str, Any]` on success, or raises `ForecastSSFMonitorSyncPartialFailure` after all independent stocks were attempted.

- [ ] **Step 1: Write failing partial-failure and recovery tests**

```python
def test_sync_continues_after_one_transition_failure_then_raises_structured_partial_failure():
    storage = _storage(_forecasts("600001", "600002"))
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")
    storage.transition_forecast_ssf_candidate_with_workflow_target.side_effect = [RuntimeError("write failed"), _target(18)]

    with pytest.raises(ForecastSSFMonitorSyncPartialFailure) as raised:
        ForecastSSFMonitorSyncService(storage, MagicMock(is_banned=lambda *_: _blackroom())).sync(date(2026, 1, 20))

    assert raised.value.summary["errors"] == [{"stock_code": "600001", "state": "eligible", "reason": "ssf_holder_match", "exception_type": "RuntimeError", "message": "write failed"}]
    assert storage.transition_forecast_ssf_candidate_with_workflow_target.call_count == 2


def test_sync_requalification_reuses_disabled_target_without_resetting_last_state():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate(target_id=17, state="blackroom")]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")
    storage.transition_forecast_ssf_candidate_with_workflow_target.return_value = _target(17, enabled=True)

    ForecastSSFMonitorSyncService(storage, MagicMock(is_banned=lambda *_: _blackroom())).sync(date(2026, 1, 20))

    call = storage.transition_forecast_ssf_candidate_with_workflow_target.call_args.kwargs
    assert (call["stock_code"], call["state"], call["target_enabled"]) == ("600001", "eligible", True)
    assert storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
```

- [ ] **Step 2: Run the new service tests to verify failure**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'partial_failure or requalification_reuses' -v`

Expected: FAIL because the partial-failure exception and transition call path do not exist.

- [ ] **Step 3: Add the structured partial-failure exception and per-stock wrapper**

```python
class ForecastSSFMonitorSyncPartialFailure(RuntimeError):
    def __init__(self, summary: dict[str, Any]) -> None:
        self.summary = summary
        super().__init__(f"forecast SSF synchronization had {len(summary['errors'])} stock transition failure(s)")


def _record_transition_error(summary: dict[str, Any], stock_code: str, state: str, reason: str, exc: Exception) -> None:
    summary["errors"].append({
        "stock_code": stock_code, "state": state, "reason": reason,
        "exception_type": type(exc).__name__, "message": str(exc),
    })
```

Change the summary’s `errors` from an integer to a list of structured records, and add an `error_count` if callers require a count. Wrap only calls that persist one stock lifecycle transition. Do not catch snapshot, record-load, listing, or blackroom preflight failures; those must still abort before mutation. After current and retired candidates have been processed, raise the new exception when structured errors are non-empty.

- [ ] **Step 4: Replace detached fallback persistence with the Task 1 transition**

```python
# For every existing candidate with monitor_target_id, request one storage
# transition using the computed state, reason, merged evidence, and desired
# target_enabled value. Do not call the detached candidate-upsert method with
# monitor_target_id=None when target linkage is invalid or persistence fails.
# when target linkage is invalid or persistence fails.
```

Use the storage transition for conclusive disablement, deferred evidence refresh, paused outcomes, and recovery. Preserve `monitor_target_id` and require the retained target for those paths. Keep target creation limited to newly qualifying stocks without an existing candidate/target relationship. Remove service-side `reset_last_state` calculation and pass `False` to legacy creation/upsert paths that remain necessary.

- [ ] **Step 5: Update lifecycle-focused tests to assert retained semantics**

Replace delete-oriented test names/assertions with retention assertions. Add tests for blackroom, non-SSF, snapshot omission, delisted/unlisted, and reporting-period supersession that verify the transition requests disabled state and preserves the original target ID. Add deferred active/paused tests and a failed retired-candidate transition alongside a succeeding independent stock.

- [ ] **Step 6: Run focused synchronization tests**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -v`

Expected: PASS.

- [ ] **Step 7: Commit synchronization lifecycle behavior**

```bash
git add monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
git commit -m "feat: report partial forecast target lifecycle failures"
```

### Task 3: Use One Alert-Time Blackroom Guard And Surface Sync Failure In The DAG

**Files:**
- Modify: `monitor/monitor_runner.py:154-183`
- Modify: `test/monitor/test_monitor_runner.py:102-120, 525-645`
- Modify: `test/dags/test_forecast_ssf_ma20_sync.py:115-138`
- Modify: `docs/stock_monitor.md:27-37` only if the final exception/result wording needs operator documentation.

**Interfaces:**
- Consumes: `StorageDb.disable_forecast_ssf_target_for_blackroom(target_id: int, reason: str) -> bool` from Task 1.
- Consumes: `ForecastSSFMonitorSyncPartialFailure` from Task 2 through the unmodified DAG service call.
- Produces: one blackroom check per trigger candidate before email, with no email or target edge-state update when banned or when lifecycle persistence fails.

- [ ] **Step 1: Write failing monitor and DAG tests**

```python
def test_workflow_alert_loads_evidence_after_one_clear_blackroom_check():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    storage.get_forecast_ssf_candidate_for_target.return_value = _candidate_evidence()
    blackroom = MagicMock()
    blackroom.is_banned.return_value = {"success": True, "data": {"banned": False}}

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    email.assert_called_once()
    assert blackroom.is_banned.call_count == 1
    assert summary.triggered == 1


def test_sync_task_propagates_partial_failure(monkeypatch, sync_module):
    service = MagicMock()
    service.return_value.sync.side_effect = ForecastSSFMonitorSyncPartialFailure({"errors": [{"stock_code": "600001"}]})
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(ForecastSSFMonitorSyncPartialFailure):
        sync_module.sync_forecast_ssf_targets(**monday_sync_context())
```

- [ ] **Step 2: Run the new monitor and DAG tests to verify failure**

Run: `uv run pytest test/monitor/test_monitor_runner.py -k 'one_clear_blackroom_check' -v && uv run pytest test/dags/test_forecast_ssf_ma20_sync.py -k partial_failure -v`

Expected: monitor test FAILS because the runner performs two successful checks; DAG test may require importing the new exception first.

- [ ] **Step 3: Remove the duplicate lookup after evidence retrieval**

```python
if is_forecast_ssf_workflow:
    blackroom = BlackroomService(storage=storage)
    ban_result = blackroom.is_banned(target.stock_code, target.market)
    if not ban_result.get("success"):
        raise RuntimeError(ban_result.get("message") or "blackroom lookup failed")
    if ban_result.get("data", {}).get("banned"):
        if not storage.disable_forecast_ssf_target_for_blackroom(target.id, "active_blackroom"):
            raise RuntimeError("failed to disable forecast SSF target for active blackroom")
        summary.skipped += 1
        continue
    candidate = storage.get_forecast_ssf_candidate_for_target(target.id)
    evidence = getattr(candidate, "evidence", None) if candidate is not None else None
```

Keep this guard immediately before `_send_alert`. Preserve existing error handling so failed lookup or failed retaining-disable increments `summary.errors`, sends no email, and does not update monitor edge state.

- [ ] **Step 4: Confirm the DAG propagates partial failure without changing DAG topology**

Leave `sync_forecast_ssf_targets()` as the direct service-call boundary. Add the focused test proving the exception escapes the callable, so Airflow fails the task with the structured exception message. Do not add tasks, dependencies, retries, or schedule changes.

- [ ] **Step 5: Run focused monitor and DAG tests**

Run: `uv run pytest test/monitor/test_monitor_runner.py test/dags/test_forecast_ssf_ma20_sync.py -v`

Expected: PASS.

- [ ] **Step 6: Update operator documentation only when needed**

If the implementation’s partial-failure exception exposes a new operator-visible summary, add one Chinese sentence under the forecast SSF sync section stating that a stock-level persistence failure allows independent stocks to finish but makes the DAG fail with structured error detail. Otherwise, leave `docs/stock_monitor.md` unchanged because it already documents retaining-disable and deferred behavior.

- [ ] **Step 7: Commit alert guard and DAG coverage**

```bash
git add monitor/monitor_runner.py test/monitor/test_monitor_runner.py test/dags/test_forecast_ssf_ma20_sync.py
git add docs/stock_monitor.md  # Only when Step 6 changed it.
git commit -m "fix: retain forecast targets at alert-time blackroom guard"
```

### Task 4: Run Cross-Boundary Verification

**Files:**
- Verify only: `storage/storage_db.py`, `monitor/forecast_ssf_monitor_sync.py`, `monitor/monitor_runner.py`, associated focused tests, and any updated documentation.

**Interfaces:**
- Consumes: the completed storage, synchronization, monitor-runner, and DAG contracts from Tasks 1-3.
- Produces: verified issue #62 behavior across unit and PostgreSQL storage boundaries.

- [ ] **Step 1: Format and inspect modified Python files**

Run: `uv run ruff format storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/monitor_runner.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/monitor/test_monitor_runner.py test/dags/test_forecast_ssf_ma20_sync.py`

Expected: files are formatted without unrelated repository rewrites.

- [ ] **Step 2: Run focused unit suites**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/monitor/test_monitor_runner.py test/dags/test_forecast_ssf_ma20_sync.py -v`

Expected: PASS.

- [ ] **Step 3: Run PostgreSQL storage contract coverage**

Run: `tools/run_tests.sh test/storage/test_forecast_ssf_candidate_storage.py -v`

Expected: PASS with the isolated test database started by the repository runner.

- [ ] **Step 4: Run static checks**

Run: `uv run ruff check storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/monitor_runner.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/monitor/test_monitor_runner.py test/dags/test_forecast_ssf_ma20_sync.py && uv run mypy storage monitor`

Expected: PASS within the repository’s configured mypy scope.

- [ ] **Step 5: Review final change boundary and commit verification fixes**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only issue #62 files are staged or intentionally left as user-owned changes. If verification requires source/test/doc changes, commit only those files:

```bash
git add storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/monitor_runner.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/monitor/test_monitor_runner.py test/dags/test_forecast_ssf_ma20_sync.py
git add docs/stock_monitor.md  # Only when it changed in Task 3.
git commit -m "test: verify forecast workflow lifecycle retention"
```
