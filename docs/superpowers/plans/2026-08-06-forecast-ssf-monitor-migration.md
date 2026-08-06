# Forecast SSF Monitor Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely upgrade existing monitor-target tables and retire forecast SSF workflow targets when stocks leave the qualified forecast universe.

**Architecture:** Make `ensure_monitor_targets_table()` the migration gate that adds/backfills the durable workflow owner, reports legacy duplicate owners before creating the unique index, and is safe to call before any ORM target access. Extend the synchronizer with a post-processing retirement pass that atomically disables only daily `forecast_ssf_ma20` targets for persisted candidates absent from the current qualified result.

**Tech Stack:** Python 3.11+, SQLAlchemy, SQLite/PostgreSQL-compatible DDL and upserts, pandas, pytest, Ruff, mypy.

## Global Constraints

- Use `uv run` for every Python command.
- Preserve manual targets and targets whose frequency is not `daily`.
- Every non-NULL durable `workflow` value, including an empty string, is workflow ownership.
- Do not automatically delete or merge legacy duplicate workflow targets.
- Fail legacy duplicate migration with a `ValueError` that names the owner key and target IDs before creating the unique index.
- A missing qualified forecast candidate must produce `state="ineligible"` and `state_reason="forecast_no_longer_qualified"` and atomically disable only its daily `forecast_ssf_ma20` target.
- A forecast-loading failure must raise before any retirement or target mutation.
- Do not change DAG schedules, retries, task boundaries, or SLA.

---

## File Structure

- `storage/storage_db.py`: startup migration gate, legacy workflow backfill/duplicate diagnostic, and candidate-retirement storage primitive where needed.
- `monitor/forecast_ssf_monitor_sync.py`: post-qualification retirement pass and lifecycle evidence.
- `test/storage/test_forecast_ssf_candidate_storage.py`: pre-migration SQLite schema, backfill, duplicate diagnostic, and index contracts.
- `test/monitor/test_forecast_ssf_monitor_sync.py`: qualified-universe removal, empty universe, and target-isolation behavior.
- `docs/stock_monitor.md`: document that targets are disabled when no longer qualified.

### Task 1: Make Workflow Schema Migration Safe

**Files:**
- Modify: `storage/storage_db.py`
- Test: `test/storage/test_forecast_ssf_candidate_storage.py`

**Interfaces:**
- Produces: `StorageDb.ensure_monitor_targets_table() -> None` that creates then migrates old schemas before target ORM access.
- Produces: `_ensure_workflow_monitor_target_identity() -> None` that backfills durable owners and validates duplicates before index creation.

- [ ] **Step 1: Write failing legacy-schema tests**

Create a SQLite `stock_monitor_targets` table manually without `workflow`, insert a JSON-marker row and a manual row, then call `ensure_monitor_targets_table()`. Assert `list_monitor_targets()` succeeds, the marker row receives its durable workflow (including `""`), and a later manual `create_monitor_target()` succeeds.

Create a separate old-schema fixture with two rows sharing `("600001", "A", "daily", "forecast_ssf_ma20")` through JSON markers. Assert `ensure_monitor_targets_table()` raises `ValueError` matching the owner key and both IDs; assert the unique index was not created.

- [ ] **Step 2: Run migration tests to verify failure**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -k 'legacy or migration' -v`

Expected: FAIL because startup initialization does not add/backfill `workflow` or diagnose duplicates before index creation.

- [ ] **Step 3: Implement ordered migration gate**

Update `ensure_monitor_targets_table()` to call `_ensure_workflow_monitor_target_identity()` immediately after `create(checkfirst=True)`. In the helper, treat `condition.get("workflow") is not None` as a backfillable marker, query duplicate non-NULL durable owners before DDL, and raise:

```python
raise ValueError(
    f"发现重复的 workflow 监控目标: {stock_code}/{market}/{frequency}/{workflow!r} "
    f"(ids: {target_ids})"
)
```

Only create `uq_stock_monitor_targets_workflow_owner` after the validation query returns no duplicates. Do not modify conflicting targets.

- [ ] **Step 4: Run storage migration regression coverage**

Run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py -v`

Expected: PASS, including fresh-schema targets, old-schema migration, manual-target access, marker backfill, and duplicate diagnostics.

- [ ] **Step 5: Commit the migration gate**

```bash
git add storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py
git commit -m "Migrate workflow monitor target ownership"
```

### Task 2: Retire Targets Outside Qualified Universe

**Files:**
- Modify: `monitor/forecast_ssf_monitor_sync.py`
- Modify: `storage/storage_db.py` only if an existing atomic primitive lacks required candidate-only behavior
- Test: `test/monitor/test_forecast_ssf_monitor_sync.py`

**Interfaces:**
- Consumes: current `load_active_forecast_candidates`, persisted `list_forecast_ssf_candidates`, daily workflow lookup, and atomic candidate/target upsert.
- Produces: a sync pass that retires absent daily `forecast_ssf_ma20` candidates with `forecast_no_longer_qualified`.

- [ ] **Step 1: Write failing retirement tests**

Configure an existing eligible candidate with a linked daily workflow target and a current forecast DataFrame containing another stock. Assert sync disables the absent stock’s workflow target and calls atomic persistence with `state="ineligible"`, `state_reason="forecast_no_longer_qualified"`, lifecycle evidence containing `as_of_date`, and `target_enabled=False`.

Add tests that an empty current forecast result retires every persisted daily workflow candidate, while a manual target and an intraday marker-bearing target remain untouched. Add a forecast-loading exception case asserting no lookup, candidate write, or target mutation occurs.

- [ ] **Step 2: Run service tests to verify failure**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'retire or no_longer_qualified or empty_universe' -v`

Expected: FAIL because current sync processes only stocks present in the qualified DataFrame.

- [ ] **Step 3: Implement post-processing retirement**

After blackroom preflight and current candidate processing, build the set of current stock codes. Iterate persisted candidates whose linked workflow target is daily `forecast_ssf_ma20` and whose stock is absent. Reuse the atomic workflow target/candidate primitive for existing workflow targets; persist candidate-only ineligible state if no target is linked. Preserve prior evidence and add:

```python
"lifecycle": {"as_of_date": as_of_date.isoformat(), "reason": "forecast_no_longer_qualified"}
```

Increment `disabled` only when an enabled workflow target is actually disabled. Do not inspect or mutate manual/intraday targets.

- [ ] **Step 4: Run focused workflow regression coverage**

Run: `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/dags/test_monitor_stock_daily.py -v`

Expected: PASS, including blackroom, stale-holder deferral, atomic failure rollback, legacy migration, retirement, and DAG ordering.

- [ ] **Step 5: Commit retirement behavior**

```bash
git add monitor/forecast_ssf_monitor_sync.py storage/storage_db.py test/monitor/test_forecast_ssf_monitor_sync.py
git commit -m "Retire unqualified forecast SSF targets"
```

### Task 3: Document and Verify Migration Behavior

**Files:**
- Modify: `docs/stock_monitor.md`

- [ ] **Step 1: Update workflow documentation**

Extend `### 业绩预增社保基金监控同步` to state that a workflow-owned daily target is disabled when its stock leaves the current qualified forecast universe. State that only workflow-owned daily targets are affected; manual and intraday targets remain unchanged.

- [ ] **Step 2: Run final project checks**

Run: `uv run pytest test`, `uv run ruff format --check storage/storage_db.py monitor/forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py`, `uv run ruff check storage monitor dags test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py`, `uv run mypy storage monitor dags`, and `git diff --check`.

Expected: all checks pass. Record existing third-party deprecation warnings separately from failures.

- [ ] **Step 3: Commit documentation**

```bash
git add docs/stock_monitor.md
git commit -m "Document forecast SSF target retirement"
```

## Plan Self-Review

- Spec coverage: Task 1 implements pre-ORM upgrade safety, empty-string backfill, duplicate diagnostics, and uniqueness enforcement. Task 2 implements approved qualified-universe retirement with atomic target/candidate state. Task 3 documents and verifies behavior.
- Placeholder scan: no incomplete requirements or deferred implementation terms are present.
- Type consistency: Task 2 uses existing storage interfaces and does not change DAG contracts; Task 1 establishes the migration gate invoked by current monitor startup.
