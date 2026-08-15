# Issue 61 Snapshot Candidate Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize qualified A-share candidates from the deterministically selected completed forecast snapshot into retained, workflow-owned daily `close_cross_ma` monitor targets.

**Architecture:** Add storage-owned reads for eligible snapshot selection, latest immutable revision selection, and as-of shareholder disclosures. Update the existing forecast SSF synchronizer to consume that immutable input, qualify after revision selection, persist provenance evidence, and use an atomic disable-and-retain target transition. The existing daily monitor DAG is not changed.

**Tech Stack:** Python 3.12, pandas, SQLAlchemy 2, SQLite unit tests, PostgreSQL contract tests, Airflow DAG callables, pytest, Ruff, mypy.

## Global Constraints

- Use `uv run` for Python commands in this repository.
- Preserve `forecast_ssf_ma20_sync` as an independent DAG; do not change `monitor_stock_daily` schedule, dependencies, retries, task boundaries, or SLA.
- Candidate input must come only from completed `ForecastSnapshotRun` and immutable `ForecastSnapshotRecord` rows.
- Business-date inputs use `date`; future snapshot ranges, forecast revisions, and shareholder disclosures are excluded.
- The workflow condition is exactly `{"type":"close_cross_ma","direction":"above","period":20,"workflow":"forecast_ssf_ma20"}`.
- Workflow-owned target identity is `(stock_code, market, frequency, workflow)`; manual, non-workflow, and non-daily targets must remain unmodified.
- Use `tools/run_tests.sh` for PostgreSQL-dependent coverage; mock external providers.
- Commit messages are English and name the completed diff.

---

## File Structure

- `storage/storage_db.py`: completed-snapshot selection, immutable latest-revision query, as-of top-10 holder read, and retained-target disable transition.
- `monitor/forecast_ssf_monitor_sync.py`: snapshot-first orchestration, qualification, evidence, workflow condition, and no-snapshot error.
- `monitor/shareholder_selling_punishment.py`: update the blackroom path to the renamed retained-target transition if it calls the legacy delete API.
- `test/storage/test_forecast_snapshot_storage.py`: SQLite contracts for snapshot choice and immutable record selection.
- `test/storage/test_forecast_ssf_candidate_storage.py`: retained-target and as-of-holder storage contracts.
- `test/monitor/test_forecast_ssf_monitor_sync.py`: service policy, provenance, no-mutation failure, and target behavior.
- `test/dags/test_forecast_ssf_ma20_sync.py`: visible propagation of a no-eligible-snapshot failure.

### Task 1: Add Immutable Snapshot Selection Storage Contracts

**Files:**
- Modify: `storage/storage_db.py:1682-1769,1932-1960`
- Modify: `test/storage/test_forecast_snapshot_storage.py`

**Interfaces:**
- Consumes: `ForecastSnapshotRun`, `ForecastSnapshotRecord`, `ForecastSnapshotStatus`, and `as_of_date: date`.
- Produces: `get_latest_completed_forecast_snapshot_run(as_of_date: date) -> ForecastSnapshotRun | None` and `load_selected_forecast_snapshot_records(run_id: int, as_of_date: date) -> pd.DataFrame`.
- Produces data-frame columns consumed by Task 3: `COL_STOCK_ID`, `COL_END_DATE`, `COL_ANN_DATE`, `COL_FORECAST_TYPE`, `COL_FORECAST_CHANGE_MIN`, `COL_FORECAST_CHANGE_MAX`, and `source_order`.

- [ ] **Step 1: Write failing storage tests for eligible-run ordering**

```python
def test_latest_completed_snapshot_excludes_future_running_and_failed_runs(db) -> None:
    future = _complete_run(db, end=date(2026, 7, 11), completed_at=datetime(2026, 7, 11, tzinfo=UTC))
    earlier = _complete_run(db, end=date(2026, 7, 9), completed_at=datetime(2026, 7, 10, tzinfo=UTC))
    later_completion = _complete_run(db, end=date(2026, 7, 9), completed_at=datetime(2026, 7, 11, tzinfo=UTC))
    same_time_higher_id = _complete_run(db, end=date(2026, 7, 9), completed_at=datetime(2026, 7, 11, tzinfo=UTC))
    _create_running_run(db, end=date(2026, 7, 10))
    _create_failed_run(db, end=date(2026, 7, 10))

    selected = db.get_latest_completed_forecast_snapshot_run(date(2026, 7, 10))

    assert selected.id == same_time_higher_id.id
    assert selected.id not in {future.id, earlier.id, later_completion.id}
```

- [ ] **Step 2: Run the new ordering test to verify it fails**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py::test_latest_completed_snapshot_excludes_future_running_and_failed_runs -v`

Expected: FAIL with `AttributeError` because the storage selection method does not exist.

- [ ] **Step 3: Implement deterministic completed-run selection**

```python
def get_latest_completed_forecast_snapshot_run(self, as_of_date: date) -> ForecastSnapshotRun | None:
    self.ensure_forecast_snapshot_tables()
    assert self.Session is not None
    with self.Session() as session:
        return cast(
            ForecastSnapshotRun | None,
            session.query(ForecastSnapshotRun)
            .filter(
                ForecastSnapshotRun.status == ForecastSnapshotStatus.COMPLETED.value,
                ForecastSnapshotRun.announcement_end_date <= as_of_date,
            )
            .order_by(
                ForecastSnapshotRun.announcement_end_date.desc(),
                ForecastSnapshotRun.completed_at.desc(),
                ForecastSnapshotRun.id.desc(),
            )
            .first(),
        )
```

- [ ] **Step 4: Run the ordering test to verify it passes**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py::test_latest_completed_snapshot_excludes_future_running_and_failed_runs -v`

Expected: PASS.

- [ ] **Step 5: Write failing latest-revision and future-input tests**

```python
def test_selected_snapshot_records_choose_latest_announcement_then_final_source_order(db) -> None:
    run = _complete_snapshot_with_records(
        db,
        [
            _record("600001.SH", date(2026, 7, 1), 0, growth_min=80),
            _record("600001.SH", date(2026, 7, 2), 0, growth_min=60),
            _record("600001.SH", date(2026, 7, 2), 1, growth_min=40),
            _record("600002.SH", date(2026, 7, 3), 0, growth_min=90),
        ],
    )

    records = db.load_selected_forecast_snapshot_records(run.id, date(2026, 7, 2))

    assert records[[COL_STOCK_ID, COL_ANN_DATE, "source_order", COL_FORECAST_CHANGE_MIN]].to_dict("records") == [
        {COL_STOCK_ID: "600001", COL_ANN_DATE: date(2026, 7, 2), "source_order": 1, COL_FORECAST_CHANGE_MIN: 40.0}
    ]
```

- [ ] **Step 6: Run the immutable-record test to verify it fails**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py::test_selected_snapshot_records_choose_latest_announcement_then_final_source_order -v`

Expected: FAIL with `AttributeError` because the record-selection method does not exist.

- [ ] **Step 7: Implement immutable latest-per-stock record retrieval**

Build a parameterized SQL CTE that filters `ForecastSnapshotRecord` by `run_id`, the selected run's `report_end_date`, and `announcement_date <= :as_of_date`; ranks by `announcement_date DESC, source_order DESC` within each `ts_code`; returns rank one ordered by `ts_code`. Convert `600001.SH`/`000001.SZ` to the repository’s six-digit `COL_STOCK_ID`, map snapshot fields to the forecast column constants, retain `source_order`, and convert date columns with `pd.to_datetime(..., errors="raise").dt.date`.

```python
WITH ranked AS (
    SELECT r.*, ROW_NUMBER() OVER (
        PARTITION BY r.ts_code
        ORDER BY r.announcement_date DESC, r.source_order DESC
    ) AS revision_rank
    FROM forecast_snapshot_records r
    JOIN forecast_snapshot_runs run ON run.id = r.run_id
    WHERE r.run_id = :run_id
      AND r.report_end_date = run.report_end_date
      AND r.announcement_date <= :as_of_date
)
SELECT * FROM ranked WHERE revision_rank = 1 ORDER BY ts_code
```

- [ ] **Step 8: Run the complete snapshot storage module**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py -v`

Expected: PASS, including existing snapshot lifecycle coverage.

- [ ] **Step 9: Commit the storage read contracts**

```bash
git add storage/storage_db.py test/storage/test_forecast_snapshot_storage.py
git commit -m "feat: select immutable forecast snapshot candidates"
```

### Task 2: Preserve Workflow Targets While Disabling And Bound Holder Reads

**Files:**
- Modify: `storage/storage_db.py:2390-2408,2705-2781`
- Modify: `monitor/shareholder_selling_punishment.py`
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py:170-377`

**Interfaces:**
- Consumes: workflow target ID, candidate lifecycle state/reason/evidence, and `as_of_date: date`.
- Produces: `disable_forecast_ssf_target_with_candidate_transition(target_id: int, state: str, state_reason: str, evidence: dict[str, Any]) -> bool`.
- Produces: `load_latest_top10_floatholders(stock_id: str, as_of_date: date) -> pd.DataFrame`.
- Task 3 uses both methods; blackroom protection must use the disable method rather than a delete method.

- [ ] **Step 1: Write failing retained-target transition tests**

```python
def test_disable_transition_retains_owned_target_and_candidate_link(tmp_path) -> None:
    db = _sqlite_storage(tmp_path)
    target, candidate = _linked_workflow_target_and_candidate(db)

    assert db.disable_forecast_ssf_target_with_candidate_transition(
        target.id, "ineligible", "ssf_holder_not_found", {"reason": "no_ssf"}
    ) is True

    persisted_target = db.find_workflow_monitor_target("600001", "A", "daily", "forecast_ssf_ma20")
    persisted_candidate = db.list_forecast_ssf_candidates()[0]
    assert (persisted_target.id, persisted_target.enabled) == (target.id, False)
    assert persisted_candidate.monitor_target_id == target.id
    assert persisted_candidate.state == "ineligible"
```

- [ ] **Step 2: Run the retained-target test to verify it fails**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py::test_disable_transition_retains_owned_target_and_candidate_link -v`

Expected: FAIL with `AttributeError` because the disable transition does not exist.

- [ ] **Step 3: Replace delete semantics with one atomic disable transition**

Rename the public and private delete-transition methods to `disable_forecast_ssf_target_with_candidate_transition` and `_disable_forecast_ssf_target_with_candidate_transition`. Within the existing transaction, retain `candidate.monitor_target_id`, update candidate state/reason/evidence, set `target.enabled = False`, and flush. Keep ownership validation: target must be a daily `forecast_ssf_ma20` target with exactly one linked candidate; otherwise return `False` without mutation. Rename blackroom wrappers to call this transition and update every in-repository caller.

```python
candidate.state = state
candidate.state_reason = state_reason
candidate.evidence = evidence_builder(candidate)
target.enabled = False
session.flush()
```

- [ ] **Step 4: Run retained-target storage tests to verify they pass**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -v`

Expected: PASS after updating existing deletion-oriented assertions to retained target ID, disabled state, and stable candidate link.

- [ ] **Step 5: Write failing as-of shareholder disclosure test**

```python
def test_load_latest_top10_floatholders_excludes_future_disclosure(tmp_path) -> None:
    db = _sqlite_storage(tmp_path)
    _save_holders(db, "600001", date(2026, 1, 10), ["全国社保基金一一八组合"])
    _save_holders(db, "600001", date(2026, 1, 25), ["普通股东"])

    result = db.load_latest_top10_floatholders("600001", date(2026, 1, 20))

    assert set(result[COL_ANN_DATE].dt.date) == {date(2026, 1, 10)}
```

- [ ] **Step 6: Run the as-of holder test to verify it fails**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py::test_load_latest_top10_floatholders_excludes_future_disclosure -v`

Expected: FAIL with `TypeError` because the current method lacks `as_of_date`.

- [ ] **Step 7: Require business date in the holder query**

Add `as_of_date: date` to `load_latest_top10_floatholders`; add `AND "公告日期" <= :as_of_date` both to the outer query and the `MAX` subquery; pass both parameters to `pd.read_sql`. Update all direct callers and tests to provide the business date.

```sql
AND "公告日期" = (
    SELECT MAX("公告日期")
    FROM top10_floatholders
    WHERE "股票代码" = :stock_id
      AND "公告日期" <= :as_of_date
)
```

- [ ] **Step 8: Run focused storage tests**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -v`

Expected: PASS, including holder lookup and transition ownership/rollback tests.

- [ ] **Step 9: Commit retained transitions and as-of holder reads**

```bash
git add storage/storage_db.py monitor/shareholder_selling_punishment.py test/storage/test_forecast_ssf_candidate_storage.py
git commit -m "feat: retain disabled forecast workflow targets"
```

### Task 3: Synchronize From Immutable Snapshot Evidence

**Files:**
- Modify: `monitor/forecast_ssf_monitor_sync.py:1-489`
- Modify: `test/monitor/test_forecast_ssf_monitor_sync.py`

**Interfaces:**
- Consumes: `storage.get_latest_completed_forecast_snapshot_run(as_of_date)`, `storage.load_selected_forecast_snapshot_records(run_id, as_of_date)`, `storage.load_latest_top10_floatholders(stock_code, as_of_date)`, and Task 2's disable transition.
- Produces: `NoEligibleForecastSnapshotError(RuntimeError)` and `ForecastSSFMonitorSyncService.sync(as_of_date: date) -> dict[str, Any]` with immutable snapshot provenance in candidate evidence.
- The DAG in Task 4 allows `NoEligibleForecastSnapshotError` to propagate as a visible task failure.

- [ ] **Step 1: Write a failing no-snapshot mutation-guard test**

```python
def test_sync_without_eligible_snapshot_raises_before_any_mutation() -> None:
    storage = MagicMock()
    storage.get_latest_completed_forecast_snapshot_run.return_value = None

    with pytest.raises(NoEligibleForecastSnapshotError, match="no completed forecast snapshot"):
        ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    storage.load_selected_forecast_snapshot_records.assert_not_called()
    storage.list_forecast_ssf_candidates.assert_not_called()
    storage.load_a_stock_listing_status.assert_not_called()
    storage.upsert_forecast_ssf_candidate.assert_not_called()
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
```

- [ ] **Step 2: Run the no-snapshot test to verify it fails**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py::test_sync_without_eligible_snapshot_raises_before_any_mutation -v`

Expected: FAIL because `NoEligibleForecastSnapshotError` and the snapshot-first read path do not exist.

- [ ] **Step 3: Implement snapshot-first input and no-snapshot failure**

Define `NoEligibleForecastSnapshotError(RuntimeError)` near the workflow constants. At the first line of `sync`, load one eligible completed run and raise the new error when absent. Load immutable selected records before loading candidates, listing data, blackroom state, shareholders, or targets. Remove use of `load_active_forecast_candidates`.

```python
snapshot = self.storage.get_latest_completed_forecast_snapshot_run(as_of_date)
if snapshot is None:
    raise NoEligibleForecastSnapshotError(
        f"no completed forecast snapshot eligible as of {as_of_date.isoformat()}"
    )
records = self.storage.load_selected_forecast_snapshot_records(snapshot.id, as_of_date)
```

- [ ] **Step 4: Write failing revision-qualification and provenance tests**

```python
def test_sync_qualifies_after_latest_revision_and_persists_snapshot_provenance() -> None:
    storage = _snapshot_storage(
        snapshot=_snapshot(id=42, report_end=date(2025, 12, 31), start=date(2026, 1, 1), end=date(2026, 1, 15)),
        records=_records("600001", ann_date=date(2026, 1, 15), source_order=3, growth_min=50.0, forecast_type="预增"),
    )
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")
    storage.upsert_forecast_ssf_candidate_with_workflow_target.return_value = _target(17)

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=_not_banned()).sync(date(2026, 1, 20))

    call = storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs
    assert call["condition"]["type"] == "close_cross_ma"
    assert call["evidence"]["snapshot"] == {
        "id": 42,
        "report_end_date": "2025-12-31",
        "announcement_start_date": "2026-01-01",
        "announcement_end_date": "2026-01-15",
        "completed_at": "2026-01-16T00:00:00+00:00",
    }
    assert call["evidence"]["forecast"]["source_order"] == 3
```

Add separate parameterized cases proving unsupported code, unlisted status, ST name, non-`预增`, nonnumeric growth, and growth below `50` cannot create/re-enable targets. Add a later nonqualifying record case proving an older qualifying record does not survive.

- [ ] **Step 5: Run the new synchronization tests to verify they fail**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -v`

Expected: FAIL because the service still reads mutable forecasts, emits `price_vs_ma`, and lacks snapshot provenance.

- [ ] **Step 6: Implement qualification and evidence with existing lifecycle order**

Replace `_CONDITION` with `close_cross_ma`. Filter immutable rows after latest-revision selection: require a six-digit supported A-share code, current listing status `L`, stock name without `ST`, exact `预增`, and finite numeric lower growth `>= 50`. Load listing data for the selected input codes plus previous candidates, construct `current_stock_codes` only from qualified rows, and retain the existing blackroom-before-supersession precedence. Pass `as_of_date` to holder lookup. Add snapshot metadata and `source_order` to each forecast evidence block before every eligible, deferred, or ineligible persistence path. Replace every legacy delete transition call with Task 2's disable transition and count it as `disabled` rather than `deleted` in the summary/tests.

```python
evidence["snapshot"] = {
    "id": snapshot.id,
    "report_end_date": snapshot.report_end_date.isoformat(),
    "announcement_start_date": snapshot.announcement_start_date.isoformat(),
    "announcement_end_date": snapshot.announcement_end_date.isoformat(),
    "completed_at": snapshot.completed_at.isoformat(),
}
evidence["forecast"]["source_order"] = int(row["source_order"])
```

- [ ] **Step 7: Run service tests to verify the synchronization policy passes**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -v`

Expected: PASS, including existing pause, blackroom, stale-holder, target-ownership, and per-stock error behavior updated for retained disabled targets.

- [ ] **Step 8: Commit snapshot-driven synchronization**

```bash
git add monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
git commit -m "feat: synchronize candidates from forecast snapshots"
```

### Task 4: Verify DAG Failure And End-To-End Contracts

**Files:**
- Modify: `test/dags/test_forecast_ssf_ma20_sync.py`
- Modify: `test/storage/test_forecast_snapshot_enum_migration.py` only if PostgreSQL snapshot selection needs an explicit new contract fixture

**Interfaces:**
- Consumes: `ForecastSSFMonitorSyncService.sync(as_of_date)` and `NoEligibleForecastSnapshotError` from Task 3.
- Produces: evidence that the existing DAG callable visibly fails on no eligible snapshot while retaining its one-task topology and schedule.

- [ ] **Step 1: Write a failing DAG propagation test**

```python
def test_sync_task_propagates_no_eligible_snapshot_failure(monkeypatch, sync_module):
    monkeypatch.setattr(sync_module, "is_a_share_trade_date", lambda _: True)
    service = MagicMock()
    service.return_value.sync.side_effect = NoEligibleForecastSnapshotError("no completed forecast snapshot eligible")
    monkeypatch.setattr("monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService", service)

    with pytest.raises(NoEligibleForecastSnapshotError, match="no completed forecast snapshot eligible"):
        sync_module.sync_forecast_ssf_targets(**monday_sync_context())
```

- [ ] **Step 2: Run the DAG test to verify it fails before Task 3 is complete**

Run: `uv run pytest test/dags/test_forecast_ssf_ma20_sync.py::test_sync_task_propagates_no_eligible_snapshot_failure -v`

Expected: FAIL with an import error until Task 3 defines the exception; after Task 3, PASS without altering DAG production code.

- [ ] **Step 3: Add PostgreSQL selection coverage when the existing enum-migration fixture can create completed snapshots**

Write a test that inserts completed, failed, running, and future-ending snapshot runs into PostgreSQL, invokes `get_latest_completed_forecast_snapshot_run`, and asserts the same deterministic range-end/completion/ID order as Task 1. Keep the test in `test/storage/test_forecast_snapshot_enum_migration.py` only when it requires the PostgreSQL enum/table migration fixture; otherwise retain the tested SQLite contract from Task 1.

- [ ] **Step 4: Run focused unit and DAG verification**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_forecast_ssf_ma20_sync.py -v`

Expected: PASS.

- [ ] **Step 5: Run PostgreSQL and static checks**

Run: `tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v`

Expected: PASS.

Run: `uv run ruff format --check storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/shareholder_selling_punishment.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_forecast_ssf_ma20_sync.py`

Expected: PASS.

Run: `uv run ruff check storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/shareholder_selling_punishment.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_forecast_ssf_ma20_sync.py`

Expected: PASS.

Run: `uv run mypy storage monitor`

Expected: PASS.

- [ ] **Step 6: Commit final tests and validation fixes**

```bash
git add test/dags/test_forecast_ssf_ma20_sync.py test/storage/test_forecast_snapshot_enum_migration.py storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/shareholder_selling_punishment.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py
```
