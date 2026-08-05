# Forecast SSF Monitor Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize qualified earnings-forecast securities with current social-security-fund ownership into one auditable, workflow-owned daily monitor target per stock.

**Architecture:** Add a small persisted candidate-state model that is the audit record and stable linkage to a monitor target. A `ForecastSSFMonitorSyncService` will consume the existing qualified forecast query, active blackroom records, and latest top-10 floatholder disclosure; it will reuse `is_social_security_holder` and mutate only monitor targets whose condition contains the stable `workflow: "forecast_ssf_ma20"` marker. The existing daily-monitor DAG receives a synchronous callable before monitor evaluation; it preserves the current schedule, task settings, and blackroom countdown dependencies.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy, PostgreSQL/SQLite test fixtures, Airflow, pytest, Ruff, mypy, uv.

## Global Constraints

- Use `uv run` for all Python and test commands.
- A candidate must be an existing #29 qualified forecast candidate, not a new forecast-filtering implementation.
- Reuse `top10_floatholder.ssf_detector.is_social_security_holder`; do not add a second ownership keyword list.
- An active A-share blackroom record is a hard exclusion before ownership evaluation.
- Persist selected forecast fields, latest shareholder disclosure and matched holder, blackroom result, state reason, and linked monitor target ID for every processed candidate.
- A workflow target uses `{"type": "price_vs_ma", "direction": "above", "period": 20, "workflow": "forecast_ssf_ma20"}` with `market="A"` and `frequency="daily"`.
- Each `(stock_code, market, workflow)` has at most one workflow-owned monitor target; manual targets with no matching workflow marker are never created, updated, disabled, or deleted by synchronization.
- A repeated successful run must make no duplicate candidate or workflow-target records.
- A systemic storage/forecast failure must raise before workflow-owned target state changes; an absent or stale shareholder disclosure is recorded as deferred and does not disable an existing workflow-owned target.
- Do not change DAG schedules, retries, task boundaries, SLA, or existing manual-monitor behavior.
- Add `forecast_ssf_candidates` to `tools/db_common.sh` when adding the new storage table.

---

## File Structure

- `storage/model/forecast_ssf_candidate.py`: SQLAlchemy model for per-stock candidate state and JSON evidence.
- `storage/model/__init__.py`, `storage/__init__.py`: public model/table exports.
- `storage/storage_db.py`: table initialization, latest-floatholder query, candidate upsert/list, and workflow-owned target lookup/upsert primitives.
- `monitor/forecast_ssf_monitor_sync.py`: orchestration service, immutable condition marker, state decisions, evidence construction, and structured run summary.
- `dags/monitor_stock_daily.py`: one callable/operator that invokes synchronization before the existing daily monitor operator.
- `test/storage/test_forecast_ssf_candidate_storage.py`: SQLite persistence, evidence, target linkage, and idempotent-upsert contracts.
- `test/monitor/test_forecast_ssf_monitor_sync.py`: service-level forecast-to-target behavior using pandas fixtures and mocked collaborators.
- `test/dags/test_monitor_stock_daily.py`: daily DAG callable and task-order assertions.
- `docs/stock_monitor.md`: concise operational description of workflow ownership and evidence persistence.
- `tools/db_common.sh`: include the new business table in export/import operations.

### Task 1: Persist Candidate Evidence and Workflow Target Identity

**Files:**
- Create: `storage/model/forecast_ssf_candidate.py`
- Modify: `storage/model/__init__.py`
- Modify: `storage/__init__.py`
- Modify: `storage/storage_db.py` near `ensure_forecasts_table`, `load_top10_floatholders_history`, and monitor-target methods
- Modify: `tools/db_common.sh`
- Test: `test/storage/test_forecast_ssf_candidate_storage.py`

**Interfaces:**
- Produces `ForecastSSFCandidate` table `forecast_ssf_candidates` with a unique `stock_code`, `market`, `report_end_date`, `state`, `state_reason`, `evidence`, `monitor_target_id`, `created_at`, and `updated_at`.
- Produces `StorageDb.ensure_forecast_ssf_candidates_table() -> None`.
- Produces `StorageDb.upsert_forecast_ssf_candidate(stock_code: str, market: str, report_end_date: date, state: str, state_reason: str, evidence: dict[str, Any], monitor_target_id: int | None) -> Any`.
- Produces `StorageDb.list_forecast_ssf_candidates() -> list[Any]`.
- Produces `StorageDb.load_latest_top10_floatholders(stock_id: str) -> pd.DataFrame` containing every holder for that stock's latest announcement date.
- Produces `StorageDb.find_workflow_monitor_target(stock_code: str, market: str, workflow: str) -> Any | None` and `StorageDb.upsert_workflow_monitor_target(stock_code: str, market: str, workflow: str, condition: dict[str, Any], note: str, enabled: bool, reset_last_state: bool) -> Any`.

- [ ] **Step 1: Write failing storage contract tests**

Create `test/storage/test_forecast_ssf_candidate_storage.py` with a SQLite `StorageDb.__new__` fixture following `test/storage/test_forecast_storage.py`. Create the complete `Base.metadata` schema, then assert:

```python
def test_candidate_upsert_preserves_one_auditable_record(tmp_path):
    db = _sqlite_storage(tmp_path)
    first = db.upsert_forecast_ssf_candidate(
        stock_code="600001", market="A", report_end_date=date(2025, 12, 31),
        state="eligible", state_reason="ssf_holder_match",
        evidence={"forecast": {"ann_date": "2026-01-15"}, "holder": {"name": "全国社保基金一一八组合"}},
        monitor_target_id=7,
    )
    second = db.upsert_forecast_ssf_candidate(
        stock_code="600001", market="A", report_end_date=date(2025, 12, 31),
        state="blackroom", state_reason="active_blackroom",
        evidence={"blackroom": {"banned": True}}, monitor_target_id=7,
    )

    rows = db.list_forecast_ssf_candidates()
    assert first.id == second.id
    assert [(row.stock_code, row.state, row.monitor_target_id) for row in rows] == [("600001", "blackroom", 7)]
    assert rows[0].evidence == {"blackroom": {"banned": True}}
```

Add a latest-disclosure fixture with two announcement dates and assert `load_latest_top10_floatholders("600001")` returns all holders from only the newer date. Add two manual targets plus one marker-bearing workflow target, then assert workflow lookup returns only the marked target and repeated workflow upsert returns its original ID.

- [ ] **Step 2: Run the new storage tests and verify failure**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -v`

Expected: FAIL because the candidate model and storage methods do not exist.

- [ ] **Step 3: Add the candidate model and exports**

Implement `ForecastSSFCandidate` with `stock_code` as the stable primary key, `market` defaulting to `"A"`, a required `Date` report period, short string state/reason fields, nullable JSON `evidence`, nullable integer `monitor_target_id`, and timezone-aware created/updated timestamps. Export the model and table constant from both storage package initializers. Keep state values as service-level strings; do not add an enum that callers would need to import.

- [ ] **Step 4: Add atomic storage primitives**

Use the existing SQLite/PostgreSQL conflict-upsert pattern from `save_forecasts` for candidate persistence. Implement `load_latest_top10_floatholders` using a parameterized query selecting one maximum `公告日期` per stock and normalize that date column with `pd.to_datetime`. For target ownership, inspect JSON condition at the application boundary after listing targets so the portable SQLite test path and PostgreSQL path have identical behavior. Reject duplicate marked targets with a clear `ValueError`; create only when absent, otherwise update only `condition`, `note`, `enabled`, and set `last_state=False` when `reset_last_state=True`.

- [ ] **Step 5: Register the table in database export/import support**

Append `forecast_ssf_candidates` next to `forecasts` in `BUSINESS_TABLES` in `tools/db_common.sh`.

- [ ] **Step 6: Run focused storage verification**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py test/storage/test_forecast_storage.py -v`

Expected: PASS, proving candidate upsert, evidence replacement, latest disclosure lookup, target-marker isolation, and repeated upsert behavior.

- [ ] **Step 7: Commit the persistence layer**

```bash
git add storage/model/forecast_ssf_candidate.py storage/model/__init__.py storage/__init__.py storage/storage_db.py tools/db_common.sh test/storage/test_forecast_ssf_candidate_storage.py
git commit -m "Add forecast SSF candidate storage"
```

### Task 2: Synchronize Qualified Forecasts Into Workflow Targets

**Files:**
- Create: `monitor/forecast_ssf_monitor_sync.py`
- Test: `test/monitor/test_forecast_ssf_monitor_sync.py`

**Interfaces:**
- Consumes `StorageDb.load_active_forecast_candidates(as_of_date: date) -> pd.DataFrame`, `StorageDb.load_latest_top10_floatholders(stock_id: str) -> pd.DataFrame`, candidate/target methods from Task 1, and `BlackroomService.is_banned(stock_code: str, market: str) -> dict[str, Any]`.
- Produces `WORKFLOW_NAME = "forecast_ssf_ma20"`.
- Produces `ForecastSSFMonitorSyncService(storage: Any = None, blackroom_service: Any = None)`.
- Produces `ForecastSSFMonitorSyncService.sync(as_of_date: date) -> dict[str, Any]` with keys `success`, `code`, `message`, and `data`.
- Produces a summary data mapping with `forecast_candidates`, `blackroom_excluded`, `ssf_matched`, `deferred`, `created`, `updated`, `disabled`, `unchanged`, and `errors`.

- [ ] **Step 1: Write failing qualification and evidence tests**

Create a DataFrame fixture using existing Chinese constants for two forecast candidates. Configure the first candidate's latest holders to include `全国社保基金一一八组合`, the second to include only a non-SSF holder, and configure blackroom responses as unbanned. Assert that one marked target is created and the candidate rows contain the forecast report period/announcement date, matching holder name/latest disclosure date, `{ "banned": False }`, and linked target ID.

```python
result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

assert result["success"] is True
assert result["data"]["ssf_matched"] == 1
storage.upsert_workflow_monitor_target.assert_called_once_with(
    stock_code="600001", market="A", workflow="forecast_ssf_ma20",
    condition={"type": "price_vs_ma", "direction": "above", "period": 20, "workflow": "forecast_ssf_ma20"},
    note="业绩预增+社保基金+MA20", enabled=True, reset_last_state=True,
)
```

Write separate tests for an active blackroom result disabling a pre-existing marked target and recording `state="blackroom"`; an empty/latest disclosure older than two calendar months recording `state="deferred"` without disabling a previous target; a no-SSF fresh disclosure disabling the prior marked target and recording `state="ineligible"`; and a manual target that never reaches an update or disable call.

- [ ] **Step 2: Run the new service tests and verify failure**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -v`

Expected: FAIL because `ForecastSSFMonitorSyncService` is not defined.

- [ ] **Step 3: Implement candidate decisions with the shared SSF detector**

Implement `sync` as one public orchestration method. It must call `storage.load_active_forecast_candidates(as_of_date)` before processing any target. For every forecast row, call `blackroom_service.is_banned(stock_code, "A")`; if the returned result is unsuccessful, raise `RuntimeError` before target mutation. For allowed rows, load the latest disclosure, parse its announcement date, defer absent or data older than two calendar months, and otherwise use `is_social_security_holder` on `COL_FLOAT_HOLDER_NAME` to choose the first matching holder deterministically.

Build evidence with only JSON-safe primitive values:

```python
{
    "forecast": {"report_end_date": "2025-12-31", "ann_date": "2026-01-15", "type": "预增", "p_change_min": 50.0},
    "shareholder": {"ann_date": "2026-01-10", "matched_holder": "全国社保基金一一八组合"},
    "blackroom": {"banned": False},
}
```

Do not reimplement forecast qualification, normalize unrelated provider data, or introduce SSF keywords in this module.

- [ ] **Step 4: Implement idempotent target transitions**

For eligible candidates, invoke `upsert_workflow_monitor_target` with the exact marker-bearing MA20 condition. Determine `reset_last_state` from the prior candidate state/linked target: `True` only for a newly created or requalified target, otherwise `False`. For a blackroom or fresh ineligible candidate, find only its marked target and disable it if currently enabled. For deferred candidates, persist evidence and state but leave target enabled state unchanged. Persist candidate state after each successful target decision and retain the target ID returned by the storage primitive.

- [ ] **Step 5: Add idempotency and systemic-failure tests**

Add a repeated eligible synchronization test with an existing marked target/candidate and assert it retains its ID, does not reset `last_state`, and increments `unchanged` rather than `created`. Add a test where `load_active_forecast_candidates` raises and assert no target/candidate write collaborator was called. Add a test where one candidate's holder query raises and assert that candidate becomes `deferred` while an independent eligible candidate is still enabled.

- [ ] **Step 6: Run service regression coverage**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py test/monitor/test_monitor_target_service.py test/storage/test_forecast_ssf_candidate_storage.py -v`

Expected: PASS, including blackroom exclusion, shared SSF matching, stale-data deferral, manual-target isolation, idempotency, and mixed per-stock failures.

- [ ] **Step 7: Commit synchronization behavior**

```bash
git add monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
git commit -m "Sync forecast SSF monitor targets"
```

### Task 3: Invoke Synchronization Before the Daily Monitor

**Files:**
- Modify: `dags/monitor_stock_daily.py`
- Modify: `test/dags/test_monitor_stock_daily.py`

**Interfaces:**
- Consumes `ForecastSSFMonitorSyncService.sync(as_of_date: date) -> dict[str, Any]` from Task 2.
- Produces `sync_forecast_ssf_monitor_targets(**context) -> str`.
- Produces `sync_forecast_ssf_targets_task` upstream of `daily_monitor_task`.

- [ ] **Step 1: Write failing DAG callable and ordering tests**

Extend the fake-Airflow fixture in `test/dags/test_monitor_stock_daily.py`. Patch `monitor.forecast_ssf_monitor_sync.ForecastSSFMonitorSyncService` and call:

```python
result = monitor_stock_daily_module.sync_forecast_ssf_monitor_targets(
    logical_date=datetime(2026, 1, 20, 15, 30)
)

service.return_value.sync.assert_called_once_with(date(2026, 1, 20))
assert "业绩预增社保基金监控目标同步完成" in result
```

Add a failed-result test asserting `success=False, code="STORAGE_ERROR"` raises through `_raise_if_failed`. Assert source text or fake operator downstream state proves `sync_forecast_ssf_targets_task >> daily_monitor_task`, while existing tasks still flow independently into `countdown_blackroom_task`.

- [ ] **Step 2: Run the DAG tests and verify failure**

Run: `uv run pytest test/dags/test_monitor_stock_daily.py -v`

Expected: FAIL because the new callable and upstream operator are absent.

- [ ] **Step 3: Implement the daily sync callable and operator dependency**

Use `_format_logical_date(context)` and parse it with `datetime.strptime(run_date, "%Y%m%d").date()`. Instantiate the sync service lazily inside the callable, call `.sync(as_of_date=...)`, validate with `_raise_if_failed`, and return one compact summary string from result data. Create `sync_forecast_ssf_targets_task` using `PythonOperator` without changing the DAG's schedule, default args, retries, or existing operator configuration. Add only `sync_forecast_ssf_targets_task >> daily_monitor_task`; do not make it part of the countdown fan-in.

- [ ] **Step 4: Run DAG and workflow-focused tests**

Run: `uv run pytest test/dags/test_monitor_stock_daily.py test/monitor/test_forecast_ssf_monitor_sync.py -v`

Expected: PASS, proving the logical date is propagated and target sync completes before monitor evaluation.

- [ ] **Step 5: Commit DAG orchestration**

```bash
git add dags/monitor_stock_daily.py test/dags/test_monitor_stock_daily.py
git commit -m "Run forecast SSF sync before daily monitor"
```

### Task 4: Document and Verify Issue #31

**Files:**
- Modify: `docs/stock_monitor.md`
- Modify: GitHub Issue #31 through `gh` only after verification succeeds

- [ ] **Step 1: Document the workflow-owned target contract**

Add a short `### 业绩预增社保基金监控同步` section after the forecast-data section. State that the daily workflow uses existing qualified forecasts, active blackroom filtering, and the existing SSF detector; it stores audit evidence in `forecast_ssf_candidates`; and it owns only targets marked `workflow: "forecast_ssf_ma20"`, leaving manual targets unchanged. Do not document pause/resume or alert-time behavior not implemented by this issue.

- [ ] **Step 2: Run all issue-focused tests**

Run: `uv run pytest test/storage/test_forecast_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/monitor/test_monitor_target_service.py test/dags/test_monitor_stock_daily.py`

Expected: exit code 0 with zero failures.

- [ ] **Step 3: Run repository checks affected by the change**

Run: `uv run ruff format --check storage/model/forecast_ssf_candidate.py storage/model/__init__.py storage/__init__.py storage/storage_db.py monitor/forecast_ssf_monitor_sync.py dags/monitor_stock_daily.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_monitor_stock_daily.py`, `uv run ruff check storage monitor dags test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_monitor_stock_daily.py`, and `uv run mypy storage monitor dags`.

Expected: all commands exit 0. Correct only findings introduced by this implementation.

- [ ] **Step 4: Inspect final scope and workspace state**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors; the user-owned changes to `pyproject.toml`, `test/download/test_download_manager.py`, and untracked `data/` remain untouched.

- [ ] **Step 5: Commit documentation**

```bash
git add docs/stock_monitor.md
git commit -m "Document forecast SSF monitor synchronization"
```

- [ ] **Step 6: Update and close Issue #31 with verification evidence**

Comment on Issue #31 with the issue-focused test command, Ruff/mypy results, the workflow marker, and the evidence-table name. Check the five acceptance criteria only when each is covered by the passing tests. Then close the issue with a concise confirmation that the qualified-forecast, blackroom, SSF, idempotent ownership, evidence, and mocked end-to-end path are implemented and verified.

## Plan Self-Review

- Spec coverage: Tasks 1-2 cover active blackroom filtering, reuse of the shared SSF detector, one workflow-owned target, auditable forecast/shareholder/blackroom/target evidence, and repeated-run idempotency. Task 2 uses mocked storage/pandas fixtures for the complete forecast-to-target path. Task 3 makes the new service operational without changing existing DAG settings.
- Scope: MA20 condition evaluation, manual pause/resume, alert-time blackroom rechecks, forecast ingestion validation, and shareholder download orchestration remain out of this issue's implementation boundary.
- Completeness check: every task declares concrete files, methods, test commands, and commit commands.
- Type consistency: candidate persistence and workflow-target storage names are defined in Task 1 and consumed with the same signatures in Tasks 2-3.
