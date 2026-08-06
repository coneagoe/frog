# Workflow Candidate Lifecycle Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable operator pause controls and complete the forecast SSF candidate lifecycle without allowing incomplete or systemic data failures to activate or disable targets incorrectly.

**Architecture:** Extend `StockMonitorTarget` with a migrated `paused` control that is distinct from `enabled`, and make storage expose atomic workflow target/candidate transitions. The forecast SSF synchronizer will classify every current or persisted candidate from validated source data, preserve enabled targets for per-stock shareholder deferrals, and enforce pause, retirement, reporting-period, and listing rules through the existing workflow-owned daily target identity. The monitor target service and CLI will provide explicit pause/resume commands for workflow targets only.

**Tech Stack:** Python 3.11+, SQLAlchemy, SQLite/PostgreSQL-compatible DDL, pandas, pytest, argparse, Ruff, mypy.

## Global Constraints

- Use `uv run` for every Python command.
- `paused` is a durable operator control separate from `enabled`; resume clears only `paused` and never enables immediately.
- Only a daily target with durable `workflow == "forecast_ssf_ma20"` is mutable through the forecast SSF lifecycle. Pause/resume controls accept only workflow-owned targets and do not permit manual targets.
- Manual targets and workflow targets with another frequency or workflow remain untouched.
- A paused target continues to receive fresh candidate evidence but cannot be auto-enabled; its persisted candidate state remains `paused` while `evidence["evaluation"]` records the evaluated automatic outcome.
- Candidate states are exactly `eligible`, `ineligible`, `deferred`, `blackroom`, `paused`, and `delisted_or_unlisted`; every transition records `as_of_date`, state, reason, and prior state when changed.
- Missing, stale, or failed shareholder disclosures defer that stock and never change the enablement of an existing workflow target.
- A forecast load/validation, blackroom preflight, or listing-validation failure raises before candidate or target mutation.
- A newer reporting period disables and records `reporting_period_superseded` in its promotion run; fresh evaluation of the new period occurs only in the next successful synchronization.
- Existing target/candidate writes remain atomic; a paired target update failure rolls back its candidate write.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLA.

---

## File Structure

- `storage/model/stock_monitor_target.py`: durable `paused` ORM mapping and default.
- `storage/storage_db.py`: legacy schema migration, workflow-only pause/resume storage primitive, target upsert pause protection, listing-status lookup, and atomic candidate/target transition support.
- `monitor/monitor_target_service.py`: validated workflow-only pause/resume API and paused serialization.
- `monitor/forecast_ssf_monitor_sync.py`: lifecycle evidence, validated preflight, pause-aware eligibility, promotion retirement, and delisted/unlisted retirement.
- `tools/stock_monitor_cli.py`: `target pause` and `target resume` subcommands.
- `test/storage/test_forecast_ssf_candidate_storage.py`: migration and transaction-level behavior.
- `test/monitor/test_monitor_target_service.py`: service control and payload behavior.
- `test/monitor/test_forecast_ssf_monitor_sync.py`: lifecycle decision and no-mutation contracts.
- `test/tools/test_stock_monitor_cli.py`: CLI command wiring and exit behavior.
- `docs/stock_monitor.md`: operator-facing pause/resume and workflow lifecycle semantics.

### Task 1: Persist Pause State And Restrict Its Mutation

**Files:**
- Modify: `storage/model/stock_monitor_target.py`
- Modify: `storage/storage_db.py:2187-2583`
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py`

**Interfaces:**
- Produces: `StockMonitorTarget.paused: Mapped[bool]`, nullable false with default/server default `false`.
- Produces: `StorageDb.set_workflow_monitor_target_paused(target_id: int, paused: bool) -> Any | None`.
- Produces: `_ensure_workflow_monitor_target_identity() -> None` that adds and backfills `paused=false` before ORM access to legacy tables.
- Consumes: existing durable workflow identity `(stock_code, market, frequency, workflow)` and `StockMonitorTarget` transaction conventions.

- [ ] **Step 1: Write failing storage tests for pause migration and workflow-only controls**

Add tests that create a legacy SQLite `stock_monitor_targets` table without both `workflow` and `paused`, call `ensure_monitor_targets_table()`, and assert the migrated target has `paused is False`. Add workflow and manual targets, then assert pause atomically sets the workflow target to `paused=True, enabled=False`, resume sets only `paused=False` while retaining `enabled=False`, and a manual target raises `ValueError` without mutation.

```python
def test_pause_resume_migrates_legacy_targets_and_preserves_disabled_resume(tmp_path):
    db = _legacy_monitor_target_storage(tmp_path)
    # Insert a legacy marker-bearing row, then run the migration gate.
    db.ensure_monitor_targets_table()

    target = db.get_monitor_target(1)
    assert target.paused is False
    paused = db.set_workflow_monitor_target_paused(target.id, paused=True)
    resumed = db.set_workflow_monitor_target_paused(target.id, paused=False)

    assert (paused.paused, paused.enabled) == (True, False)
    assert (resumed.paused, resumed.enabled) == (False, False)


def test_pause_rejects_manual_target_without_mutation(tmp_path):
    db = _sqlite_storage(tmp_path)
    manual = db.create_monitor_target("600001", "A", {"price": {"above": 10}})

    with pytest.raises(ValueError, match="workflow"):
        db.set_workflow_monitor_target_paused(manual.id, paused=True)

    assert db.get_monitor_target(manual.id).enabled is True
```

- [ ] **Step 2: Run the focused storage tests to verify failure**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -k 'pause or resume or legacy' -v`

Expected: FAIL because `paused` is not mapped or migrated and the storage control method does not exist.

- [ ] **Step 3: Add the schema field and ordered legacy migration**

In `StockMonitorTarget`, add the durable field adjacent to `enabled`:

```python
paused: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False,
    default=False,
    server_default=text("false"),
    comment="是否由操作员暂停自动启用",
)
```

In `_ensure_workflow_monitor_target_identity()`, add a `paused BOOLEAN NOT NULL DEFAULT false` column when inspection does not find `paused`, after the existing `workflow` upgrade and before any session query. Keep `paused` out of generic `update_monitor_target()` allowed fields so a caller cannot pause a manual target through `target update`.

- [ ] **Step 4: Implement the transaction-safe workflow pause primitive**

Add the method after `find_workflow_monitor_target()`. It must call `ensure_monitor_targets_table()`, query by ID in one session transaction, return `None` for an absent ID, reject `workflow is None` with `ValueError("only workflow monitor targets can be paused or resumed")`, and apply these exact updates:

```python
if paused:
    target.paused = True
    target.enabled = False
else:
    target.paused = False
session.flush()
```

Do not alter `last_state`, `condition`, candidate data, or `enabled` during resume. Refresh the target after commit and return it.

- [ ] **Step 5: Protect paused targets in workflow upserts**

Update `_upsert_workflow_monitor_target_in_transaction()` so an existing target with `paused is True` never receives `enabled=True` from an automatic upsert:

```python
target.enabled = False if target.paused else enabled
```

For a newly inserted target, explicitly include `"paused": False` in the record. Ensure every branch that checks whether a target changed compares effective rather than requested enablement. Add a compact test that an existing `paused=True` workflow target remains `enabled=False` when an automatic upsert requests `enabled=True`.

- [ ] **Step 6: Run storage regression coverage**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py -v`

Expected: PASS, covering pause migration/default, manual isolation, durable workflow identity, workflow upsert behavior, and candidate-target rollback.

- [ ] **Step 7: Commit the persistence and control layer**

```bash
git add storage/model/stock_monitor_target.py storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py
```

### Task 2: Expose Explicit Pause And Resume Operations

**Files:**
- Modify: `monitor/monitor_target_service.py:82-375`
- Modify: `tools/stock_monitor_cli.py:57-125,269-311`
- Modify: `test/monitor/test_monitor_target_service.py`
- Modify: `test/tools/test_stock_monitor_cli.py`

**Interfaces:**
- Consumes: `StorageDb.set_workflow_monitor_target_paused(target_id: int, paused: bool) -> Any | None` from Task 1.
- Produces: `MonitorTargetService.pause(target_id: int) -> dict[str, Any]` and `MonitorTargetService.resume(target_id: int) -> dict[str, Any]`.
- Produces: CLI commands `stock-monitor target pause --target-id <id>` and `stock-monitor target resume --target-id <id>`.
- Produces: serialized targets with `"paused": bool`.

- [ ] **Step 1: Write failing service and CLI tests**

Add service tests for a successful pause, successful resume that returns `enabled=False, paused=False`, manual-target validation failure from storage, and missing target. Add CLI tests that assert command parsing calls `service.pause(1)` and `service.resume(1)`, and that the existing code-to-exit mapping is preserved.

```python
def test_pause_delegates_to_workflow_storage_and_serializes_state():
    storage = MagicMock()
    storage.set_workflow_monitor_target_paused.return_value = _make_target(enabled=False, paused=True)

    result = MonitorTargetService(storage=storage).pause(1)

    assert result["success"] is True
    assert result["data"]["paused"] is True
    storage.set_workflow_monitor_target_paused.assert_called_once_with(1, paused=True)


def test_target_pause_command_calls_service_pause():
    service = MagicMock()
    service.pause.return_value = {"success": True, "code": "OK", "message": "target paused", "data": {"id": 1}}

    assert main(["target", "pause", "--target-id", "1"], service=service) == EXIT_OK
    service.pause.assert_called_once_with(1)
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `uv run pytest test/monitor/test_monitor_target_service.py test/tools/test_stock_monitor_cli.py -k 'pause or resume' -v`

Expected: FAIL because service methods and target subcommands are absent.

- [ ] **Step 3: Implement service methods and stable serialization**

Add methods that validate a positive integer ID, delegate to storage, and map missing IDs to `NOT_FOUND`. Permit `ValueError` from the workflow-only storage guard to become `VALIDATION_ERROR` without leaking a traceback:

```python
def pause(self, target_id: int) -> dict[str, Any]:
    return self._set_workflow_pause(target_id, paused=True, message="target paused")

def resume(self, target_id: int) -> dict[str, Any]:
    return self._set_workflow_pause(target_id, paused=False, message="target resumed")
```

Implement `_set_workflow_pause()` beside `set_target_status()`. Update `_make_target()` test fixtures and `_serialize_target()` to include `paused`; default `getattr(target, "paused", False)` preserves compatibility with mocks that do not set it.

- [ ] **Step 4: Wire dedicated CLI commands**

Add `pause` and `resume` parsers under `target`, each with required integer `--target-id`. Extend the target dispatch immediately after `update`:

```python
elif args.target_command == "pause":
    result = _svc.pause(args.target_id)
elif args.target_command == "resume":
    result = _svc.resume(args.target_id)
```

Do not add `paused` to `target update`; pause/resume must remain explicit workflow-only commands.

- [ ] **Step 5: Run service and CLI regression coverage**

Run: `uv run pytest test/monitor/test_monitor_target_service.py test/tools/test_stock_monitor_cli.py -v`

Expected: PASS, including existing add/update/delete/list/get/status behavior and new pause/resume commands.

- [ ] **Step 6: Commit operator controls**

```bash
git add monitor/monitor_target_service.py tools/stock_monitor_cli.py test/monitor/test_monitor_target_service.py test/tools/test_stock_monitor_cli.py
```

### Task 3: Implement Validated Candidate Lifecycle Synchronization

**Files:**
- Modify: `storage/storage_db.py:1552-1635,2416-2469`
- Modify: `monitor/forecast_ssf_monitor_sync.py`
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py`
- Modify: `test/monitor/test_forecast_ssf_monitor_sync.py`

**Interfaces:**
- Produces: `StorageDb.load_a_stock_listing_status(stock_codes: list[str]) -> pd.DataFrame`, returning `COL_STOCK_ID`, `COL_LIST_STATUS`, and `COL_DELISTING_DATE` for every database row matching the requested codes and raising provider/database errors.
- Produces: pause-aware `StorageDb.upsert_forecast_ssf_candidate_with_workflow_target(..., target_enabled: bool, reset_last_state: bool) -> Any` that will not enable a paused target.
- Consumes: `ForecastSSFMonitorSyncService.sync(as_of_date: date) -> dict[str, Any]`, blackroom preflight, `load_latest_top10_floatholders`, and the existing atomic storage primitive.
- Produces: lifecycle evidence with `{"as_of_date": ISO_date, "state": state, "reason": reason}` and `"previous_state"` only when the state changed.

- [ ] **Step 1: Write failing lifecycle service tests**

Add compact tests covering these exact contracts using the existing `MagicMock` storage fixture and a `_target(..., paused=False)` helper:

```python
def test_sync_paused_eligible_candidate_keeps_target_disabled_and_records_evaluated_outcome():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False, paused=True)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=_healthy_blackroom()).sync(date(2026, 1, 20))

    call = storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs
    assert (call["state"], call["target_enabled"]) == ("paused", False)
    assert call["evidence"]["evaluation"]["state"] == "eligible"


def test_sync_deferral_does_not_change_enabled_target():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True, paused=False)
    storage.load_latest_top10_floatholders.return_value = pd.DataFrame()

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=_healthy_blackroom()).sync(date(2026, 1, 20))

    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
```

Also add tests for blackroom recovery after expiry, non-SSF ineligibility, absent-universe retirement, reporting-period promotion that records `ineligible/reporting_period_superseded` and disables without evaluating the new period until the next run, listed-status absence that records `delisted_or_unlisted`, and forecast/blackroom/listing preflight failure with no writes. Include a rerun assertion that identical lifecycle state/evidence does not increment `disabled`, `updated`, or `created` counters.

- [ ] **Step 2: Run focused lifecycle tests to verify failure**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'paused or promotion or delisted or lifecycle or preflight' -v`

Expected: FAIL because the synchronizer has no listing preflight, pause state, lifecycle transition record, or reporting-period promotion gate.

- [ ] **Step 3: Add listing-status storage lookup and test it**

In `StorageDb`, implement a parameterized SQLAlchemy `text()` query against `a_stock_basic`, returning the code, `上市状态`, and `退市日期` for the requested codes. Return an empty DataFrame with those three columns only when `stock_codes` is empty; do not catch database errors. Use dialect-safe expanding bind parameters rather than interpolating stock codes:

```python
stmt = text(
    f'SELECT "{COL_STOCK_ID}", "{COL_LIST_STATUS}", "{COL_DELISTING_DATE}" '
    f"FROM {tb_name_a_stock_basic} WHERE \"{COL_STOCK_ID}\" IN :stock_codes"
).bindparams(bindparam("stock_codes", expanding=True))
return pd.read_sql(stmt, self.engine, params={"stock_codes": stock_codes})
```

Add a storage test for an active `L` row, a non-`L` row, and an absent code. The sync must interpret an absent/non-`L` record as a validated `delisted_or_unlisted` result only after the lookup returns successfully.

- [ ] **Step 4: Build lifecycle evidence without discarding prior evidence**

Add a small synchronizer helper with a single responsibility:

```python
def _with_lifecycle(
    self, previous_candidate: Any | None, evidence: dict[str, Any], as_of_date: date, state: str, reason: str
) -> dict[str, Any]:
    result = dict(getattr(previous_candidate, "evidence", None) or {})
    result.update(evidence)
    lifecycle = {"as_of_date": as_of_date.isoformat(), "state": state, "reason": reason}
    previous_state = getattr(previous_candidate, "state", None)
    if previous_state is not None and previous_state != state:
        lifecycle["previous_state"] = previous_state
    result["lifecycle"] = lifecycle
    return result
```

Call it for every `_persist` or `_persist_with_target` path, including existing missing/unlinked target retirements. For a paused target whose automatic evaluation is otherwise eligible, persist `state="paused"`, `state_reason="manual_pause"`, `target_enabled=False`, and `evidence["evaluation"] = {"state": "eligible", "reason": "ssf_holder_match"}`.

- [ ] **Step 5: Add complete preflight before any candidate writes**

After `load_active_forecast_candidates()` and `list_forecast_ssf_candidates()`, derive the union of current and persisted candidate stock codes. Before mutating candidates, perform both operations for every code in that union:

```python
all_stock_codes = current_stock_codes | set(previous_candidates)
listing = self.storage.load_a_stock_listing_status(sorted(all_stock_codes))
blackroom_results = self._load_blackroom_results(current_stock_codes)
```

Build a code-to-listing map and classify non-`L` or missing codes as `delisted_or_unlisted`; their target may be disabled only after preflight succeeds for every code. Apply this classification to both current rows and persisted candidates absent from the current forecast universe before ordinary qualified-universe retirement. Let lookup errors and blackroom failures propagate. Do not treat an empty successful forecast result as a listing failure; it should still validate and retire persisted workflow candidates.

- [ ] **Step 6: Implement transition ordering and promotion gate**

For each current forecast row, evaluate in this order: listing status, blackroom, shareholder deferral, SSF match, pause protection. Compute the automatic outcome first. If the matching target is paused, persist `state="paused"`, `state_reason="manual_pause"`, and `target_enabled=False` for every automatic outcome, including blackroom, listing, ineligibility, and promotion; retain that automatic outcome in `evidence["evaluation"]`. Use `previous_candidate.report_end_date` to detect a newer current report period. On promotion, persist `ineligible` with reason `reporting_period_superseded`, lifecycle evidence including both old/new report dates, disable its matching target through the atomic primitive, increment `disabled` only for an enabled target, and skip the current row's qualification. On the next successful run, `previous_candidate.report_end_date` matches and normal qualification proceeds.

In `_retire_absent_candidates()`, classify persisted absent candidates as `delisted_or_unlisted` before ordinary `forecast_no_longer_qualified` retirement when listing preflight shows they are absent/non-`L`. Preserve the current missing-universe behavior otherwise, but pass each candidate through the same target-link verification and lifecycle helper. Keep retirement scoped to `find_workflow_monitor_target(stock_code, "A", "daily", WORKFLOW_NAME)` and exact candidate target ID.

- [ ] **Step 7: Preserve idempotent counters and atomicity**

Update helper calls so target mutation uses the existing `upsert_forecast_ssf_candidate_with_workflow_target()` transaction. Count `disabled` only when `target.enabled is True` and the effective target state becomes disabled. For repeated candidate-only writes or an already disabled target, do not increment action counters. Retain the existing rollback test and add one that makes candidate persistence fail during a paused or supersession update, then asserts both candidate and target retain their prior stored values.

- [ ] **Step 8: Run focused lifecycle and storage regression coverage**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/dags/test_monitor_stock_daily.py -v`

Expected: PASS, including state transitions, deferral safety, manual/intraday isolation, listing classification, promotion timing, pause protection, atomic rollback, and unchanged DAG ordering.

- [ ] **Step 9: Commit lifecycle enforcement**

```bash
git add storage/storage_db.py monitor/forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py
```

### Task 4: Document The Operator Contract And Verify The Repository

**Files:**
- Modify: `docs/stock_monitor.md:7-26`
- Test: `test/tools/test_stock_monitor_cli.py`

**Interfaces:**
- Documents: `stock-monitor target pause --target-id ...` and `stock-monitor target resume --target-id ...`.
- Documents: workflow-only scope, resume-on-next-sync behavior, candidate states, non-destructive retirement, and manual-target isolation.

- [ ] **Step 1: Update target command and workflow lifecycle documentation**

Add both CLI commands below the existing target command list. Expand the forecast SSF section to explicitly state that a paused workflow target is immediately disabled, continues collecting evidence, and only becomes eligible for automatic enablement after a later successful sync following resume. State that missing/stale shareholder evidence causes `deferred` without disabling an active target; blackroom, qualified-universe removal, superseded reporting periods, and delisted/unlisted classification disable only the matching daily workflow target; manual and intraday targets remain unchanged.

- [ ] **Step 2: Run formatting, linting, typing, and focused tests**

Run: `uv run ruff format --check storage/model/stock_monitor_target.py storage/storage_db.py monitor/monitor_target_service.py monitor/forecast_ssf_monitor_sync.py tools/stock_monitor_cli.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/monitor/test_forecast_ssf_monitor_sync.py test/tools/test_stock_monitor_cli.py`

Expected: PASS.

Run: `uv run ruff check storage monitor tools test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/monitor/test_forecast_ssf_monitor_sync.py test/tools/test_stock_monitor_cli.py`

Expected: PASS.

Run: `uv run mypy storage monitor dags`

Expected: PASS.

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/monitor/test_forecast_ssf_monitor_sync.py test/tools/test_stock_monitor_cli.py test/dags/test_monitor_stock_daily.py -v`

Expected: PASS.

- [ ] **Step 3: Run final repository verification**

Run: `uv run pytest test`

Expected: PASS. Record existing third-party deprecation warnings separately from failures.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/stock_monitor.md
```

## Plan Self-Review

- Spec coverage: Task 1 creates durable pause state and atomic operator control; Task 2 exposes only explicit workflow pause/resume commands; Task 3 supplies lifecycle evidence, state transitions, complete preflight, reporting-period supersession, listing classification, idempotency, and atomicity; Task 4 documents and verifies the behavior.
- Placeholder scan: no incomplete tasks or deferred implementation references remain; every implementation step names the target APIs, expected state, and test command.
- Type consistency: `set_workflow_monitor_target_paused(target_id, paused)` is produced in Task 1 and consumed unchanged in Task 2; `load_a_stock_listing_status(stock_codes)` is produced and consumed in Task 3; synchronization retains the existing atomic `upsert_forecast_ssf_candidate_with_workflow_target()` interface.
