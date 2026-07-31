# Paper Matching Run Status Enum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist paper matching-run states with a PostgreSQL native enum via an explicit migration command, without changing matching success semantics.

**Architecture:** A connection-level migration module validates, converts, and verifies the PostgreSQL schema. A dedicated administrative CLI owns configuration, transactions, output, and exit codes. The ORM maps the existing domain enum's lowercase values, while the matching API rolls back unexpected persistence failures at its route boundary.

**Tech Stack:** Python 3.11+, SQLAlchemy 2, PostgreSQL, SQLite, FastAPI, pytest, argparse.

## Global Constraints

- Use `uv run` for Python commands.
- Canonical states are exactly `running`, `completed`, `completed_with_warnings`, and `failed`.
- Persist `MatchingRunStatus.value`, never uppercase member names.
- PostgreSQL enum DDL belongs only to the explicit migration command, never process startup bootstrap.
- Unknown legacy values fail preflight without coercion, truncation, or deletion.
- Preserve lowercase API/CLI success responses and existing matching/DAG behavior.
- PostgreSQL integration tests use `TEST_POSTGRESQL_URL`; skip only when unavailable.
- Do not include existing unrelated Docker runtime-artifact deletions in edits or commits.

---

## File Structure

- Create `paper_trading/storage/matching_status_migration.py`: migration/result/error contract.
- Create `tools/migrate_paper_matching_run_status_enum.py`: explicit operator command.
- Modify `storage/model/paper_trading.py`: lowercase enum persistence mapping.
- Modify `paper_trading/storage/repository.py`: canonical state use at repository boundaries.
- Modify `paper_trading/api/routers/matching.py`: rollback and safe persistence-error boundary.
- Create `test/paper_trading/storage/test_matching_status_migration.py`: migration unit and portable model tests.
- Modify `test/storage/test_storage_db.py`: real PostgreSQL temporary-schema coverage.
- Create `test/tools/test_migrate_paper_matching_run_status_enum.py`: CLI coverage.
- Modify API/replay tests and `docs/paper_trading.md`: behavioral and operating coverage.

### Task 1: Map Matching Runs to Canonical Enum Values

**Files:**
- Modify: `storage/model/paper_trading.py:246-273`
- Modify: `paper_trading/storage/repository.py:656-728`
- Test: `test/paper_trading/storage/test_models.py`
- Test: `test/paper_trading/services/test_order_delete_service.py:889-1023`

**Interfaces:**
- Consumes: `MatchingRunStatus`.
- Produces: a validating SQLAlchemy enum column named `paper_matching_run_status` that persists lowercase `.value` strings and remains SQLite-compatible.

- [ ] **Step 1: Write failing status-contract tests**

```python
def test_matching_run_status_round_trips_lowercase_value(session):
    run = PaperMatchingRun(
        trade_date=date(2026, 7, 31),
        scope_key="all",
        status=MatchingRunStatus.COMPLETED_WITH_WARNINGS,
    )
    session.add(run)
    session.commit()
    assert session.get(PaperMatchingRun, run.id).status == MatchingRunStatus.COMPLETED_WITH_WARNINGS

def test_matching_run_status_rejects_unknown_value(session):
    session.add(PaperMatchingRun(trade_date=date(2026, 7, 31), scope_key="all", status="unknown"))
    with pytest.raises((LookupError, StatementError)):
        session.flush()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest test/paper_trading/storage/test_models.py -k matching_run_status -v`

Expected: FAIL because status is a free-form string.

- [ ] **Step 3: Implement the portable enum mapping**

```python
MatchingRunStatusType = Enum(
    MatchingRunStatus,
    name="paper_matching_run_status",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    native_enum=True,
    validate_strings=True,
)
```

Use the type for matching-run status. Replace repository/replay raw `"running"` uses with `MatchingRunStatus.RUNNING.value`; retain the lowercase partial-index predicate.

- [ ] **Step 4: Verify model and replay behavior**

Run: `uv run pytest test/paper_trading/storage/test_models.py -k matching_run_status -v && uv run pytest test/paper_trading/services/test_order_delete_service.py -k matching_run -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add storage/model/paper_trading.py paper_trading/storage/repository.py test/paper_trading/storage/test_models.py test/paper_trading/services/test_order_delete_service.py && git commit -m "feat: model paper matching statuses as enums"`

### Task 2: Build and Prove the PostgreSQL Migration

**Files:**
- Create: `paper_trading/storage/matching_status_migration.py`
- Create: `test/paper_trading/storage/test_matching_status_migration.py`
- Modify: `test/storage/test_storage_db.py:3510-3587`

**Interfaces:**
- Produces: `migrate_paper_matching_status_enum(connection: Connection, *, dry_run: bool = False) -> MatchingStatusEnumMigrationResult`.
- Produces: `MatchingStatusEnumMigrationError` for invalid history, unsupported live dialect, or failed verification.

- [ ] **Step 1: Write failing migration tests**

```python
def test_sqlite_dry_run_performs_no_postgresql_ddl(sqlite_connection):
    result = migrate_paper_matching_status_enum(sqlite_connection, dry_run=True)
    assert result.dialect == "sqlite"
    assert result.column_converted is False

def test_migration_rejects_unknown_legacy_status(postgresql_legacy_connection):
    postgresql_legacy_connection.execute(text("INSERT INTO paper_matching_runs (trade_date, scope_key, status) VALUES ('2026-07-31', 'all', 'unknown')"))
    with pytest.raises(MatchingStatusEnumMigrationError, match="unknown"):
        migrate_paper_matching_status_enum(postgresql_legacy_connection)
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest test/paper_trading/storage/test_matching_status_migration.py -v`

Expected: FAIL because the migration interface does not exist.

- [ ] **Step 3: Implement validation, conversion, and verification**

Implement this sequence: return a non-mutating no-op for SQLite dry-run and reject other non-PostgreSQL live runs; report no-op if the table is absent; validate all existing values before DDL; create and verify `public.paper_matching_run_status`; convert text/varchar with `USING status::text::public.paper_matching_run_status`; verify column type and active-run partial unique index; return immutable conversion facts. Never call this module from startup bootstrap.

- [ ] **Step 4: Add real PostgreSQL temporary-schema tests**

Reuse existing `TEST_POSTGRESQL_URL`, unique schema, `search_path`, and cleanup patterns. Test valid legacy conversion, idempotent rerun, invalid history, labels, invalid insert rejection, one-running-run uniqueness, and terminal-run retry.

- [ ] **Step 5: Verify migration behavior**

Run: `uv run pytest test/paper_trading/storage/test_matching_status_migration.py test/storage/test_storage_db.py -k "matching_status or postgresql" -v`

Expected: PASS; live cases skip only if PostgreSQL is unavailable.

- [ ] **Step 6: Commit**

Run: `git add paper_trading/storage/matching_status_migration.py test/paper_trading/storage/test_matching_status_migration.py test/storage/test_storage_db.py && git commit -m "feat: add matching status enum migration"`

### Task 3: Add the Explicit Migration Command

**Files:**
- Create: `tools/migrate_paper_matching_run_status_enum.py`
- Create: `test/tools/test_migrate_paper_matching_run_status_enum.py`

**Interfaces:**
- Produces: `main(argv: list[str] | None = None) -> int`.
- Supports: `--dry-run` and `--json`.
- Uses: `parse_config()`, `get_storage()`, and `migrate_paper_matching_status_enum(connection, dry_run=...)`.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_main_dry_run_prints_json_result(monkeypatch, capsys):
    monkeypatch.setattr(module, "migrate_paper_matching_status_enum", lambda connection, dry_run: result)
    assert module.main(["--dry-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True

def test_main_reports_migration_failure(monkeypatch, caplog):
    monkeypatch.setattr(module, "migrate_paper_matching_status_enum", raise_migration_error)
    assert module.main([]) == 1
    assert "migration failed" in caplog.text.lower()
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest test/tools/test_migrate_paper_matching_run_status_enum.py -v`

Expected: FAIL because the command module does not exist.

- [ ] **Step 3: Implement transaction-owned CLI behavior**

```python
def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    parse_config()
    storage = get_storage()
    assert storage.engine is not None
    try:
        with storage.engine.begin() as connection:
            result = migrate_paper_matching_status_enum(connection, dry_run=args.dry_run)
    except MatchingStatusEnumMigrationError:
        logger.exception("Paper matching status enum migration failed")
        return 1
    print(_render_result(result, json_output=args.json))
    return 0
```

Ensure dry-run emits no mutating DDL and all connection/verification failures return nonzero with logs.

- [ ] **Step 4: Verify CLI behavior**

Run: `uv run pytest test/tools/test_migrate_paper_matching_run_status_enum.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add tools/migrate_paper_matching_run_status_enum.py test/tools/test_migrate_paper_matching_run_status_enum.py && git commit -m "feat: add matching status migration command"`

### Task 4: Handle Matching Persistence Errors Safely

**Files:**
- Modify: `paper_trading/api/routers/matching.py:1-29`
- Modify: `test/paper_trading/api/test_matching_api.py:14-71`

**Interfaces:**
- Produces: unchanged successful `MatchingRunResponse`.
- Produces: safe HTTP 500 after rollback for unexpected `SQLAlchemyError` during matching persistence.

- [ ] **Step 1: Write failing API boundary tests**

```python
def test_matching_commit_failure_rolls_back_and_hides_database_details(client, monkeypatch, caplog):
    monkeypatch.setattr(Session, "commit", raise_sqlalchemy_error)
    response = client.post("/paper/matching/runs", json={"trade_date": "2026-07-31"}, headers=auth_headers)
    assert response.status_code == 500
    assert "SELECT" not in response.text
    assert "psycopg" not in response.text.lower()
    assert "matching persistence failed" in caplog.text.lower()
```

Retain/add the existing warning case asserting a matching request returns HTTP 200 and lowercase `completed_with_warnings`.

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest test/paper_trading/api/test_matching_api.py -v`

Expected: commit failure currently escapes without explicit rollback or a safe response.

- [ ] **Step 3: Add a narrow route boundary**

Catch only `SQLAlchemyError` around matching service execution/commit, call `session.rollback()`, use `logger.exception` with safe trade-date/account context, and raise `HTTPException(status_code=500, detail={"code": "MATCHING_PERSISTENCE_FAILED", "message": "Matching persistence failed", "details": {}})`. Do not alter domain behavior.

- [ ] **Step 4: Verify API behavior**

Run: `uv run pytest test/paper_trading/api/test_matching_api.py -v`

Expected: PASS; warning-completed matching remains successful and persistence failure rolls back safely.

- [ ] **Step 5: Commit**

Run: `git add paper_trading/api/routers/matching.py test/paper_trading/api/test_matching_api.py && git commit -m "fix: handle matching persistence failures safely"`

### Task 5: Document Rollout and Restore

**Files:**
- Modify: `docs/paper_trading.md:336-355`
- Modify: `tools/db_common.sh:1-49` only if verification shows an enum restore-order defect.
- Test: `test/tools/test_migrate_paper_matching_run_status_enum.py`

**Interfaces:**
- Consumes: `uv run tools/migrate_paper_matching_run_status_enum.py [--dry-run] [--json]`.
- Produces: controlled migration, deployment, retry, backup, and restore procedure.

- [ ] **Step 1: Add executable result verification**

```python
def test_migration_result_reports_enum_and_active_index_verification(connection):
    result = migrate_paper_matching_status_enum(connection)
    assert result.active_index_verified is True
    assert result.enum_labels == tuple(member.value for member in MatchingRunStatus)
```

- [ ] **Step 2: Verify result contract**

Run: `uv run pytest test/tools/test_migrate_paper_matching_run_status_enum.py -k verification -v`

Expected: PASS.

- [ ] **Step 3: Update operational documentation**

Document: isolate API/Celery/Airflow matching writes; back up database; run dry-run and resolve invalid values; run migration and check labels/index; deploy enum-aware services; resume matching and retry Airflow; verify `completed_with_warnings`. State future labels require migration/review. Verify type-before-row restoration and change `tools/db_common.sh` only for an observed defect.

- [ ] **Step 4: Verify command without mutation**

Run: `uv run tools/migrate_paper_matching_run_status_enum.py --dry-run --json`

Expected: non-mutating JSON result, or a recorded local configuration limitation plus integration-test evidence.

- [ ] **Step 5: Commit**

Run: `git add docs/paper_trading.md tools/db_common.sh test/tools/test_migrate_paper_matching_run_status_enum.py && git commit -m "docs: document matching status enum rollout"`

### Task 6: Verify the Complete Change

**Files:**
- Verify all Task 1–5 files plus the design and plan documents.

- [ ] **Step 1: Check formatting and lint**

Run: `uv run ruff format --check paper_trading/storage/matching_status_migration.py tools/migrate_paper_matching_run_status_enum.py storage/model/paper_trading.py paper_trading/storage/repository.py paper_trading/api/routers/matching.py test/paper_trading/storage/test_matching_status_migration.py test/tools/test_migrate_paper_matching_run_status_enum.py test/paper_trading/api/test_matching_api.py && uv run ruff check paper_trading/storage/matching_status_migration.py tools/migrate_paper_matching_run_status_enum.py storage/model/paper_trading.py paper_trading/storage/repository.py paper_trading/api/routers/matching.py test/paper_trading/storage/test_matching_status_migration.py test/tools/test_migrate_paper_matching_run_status_enum.py test/paper_trading/api/test_matching_api.py`

Expected: PASS.

- [ ] **Step 2: Run focused regression suite**

Run: `uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_matching_status_migration.py test/tools/test_migrate_paper_matching_run_status_enum.py test/paper_trading/api/test_matching_api.py test/paper_trading/services/test_order_delete_service.py -v`

Expected: PASS; PostgreSQL-only tests skip only when unavailable.

- [ ] **Step 3: Inspect intended changes only**

Run: `git --no-pager diff -- paper_trading storage tools test docs/paper_trading.md docs/superpowers/specs/2026-07-31-paper-matching-run-status-enum-design.md docs/superpowers/plans/2026-07-31-paper-matching-run-status-enum.md`

Expected: matching status migration/API/test/docs changes only; no Docker runtime artifacts.

## Plan Self-Review

- Task 1 covers lowercase enum persistence and replay compatibility.
- Task 2 covers explicit validation, conversion, idempotence, native type, and partial-index behavior.
- Task 3 creates the single operator migration command.
- Task 4 covers rollback, logs, and safe API failure output.
- Task 5 covers rollout, future-label contract, and restore verification.
- Task 6 provides formatting, lint, regression, and diff evidence.
