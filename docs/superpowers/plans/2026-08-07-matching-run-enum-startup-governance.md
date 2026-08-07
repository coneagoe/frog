# Matching Run Enum Startup Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make matching-run PostgreSQL table and enum provisioning an explicit, idempotent operator bootstrap while ensuring application startup cannot create or alter the enum.

**Architecture:** Keep `PaperMatchingRun` mapped to `MatchingRunStatus`, but exclude its table from normal metadata bootstrap. Extend the focused migration module with preflight facts and a bootstrap operation that creates the missing table only under explicit operator control, then delegates legacy conversion and validation to the existing migration routine. Replace the conversion-only CLI with the bootstrap CLI and document the single maintenance procedure.

**Tech Stack:** Python 3.12, SQLAlchemy, PostgreSQL, pytest, Ruff, mypy, argparse.

## Global Constraints

- Use `uv run` for every Python command.
- Normal `StorageDb` initialization must not create, alter, or extend `paper_matching_run_status` or create `paper_matching_runs`.
- The supported operator entry point is `uv run tools/bootstrap_paper_matching_run_status.py`, with `--dry-run` and `--json`.
- The canonical status labels and order are `running`, `completed`, `completed_with_warnings`, and `failed`.
- Unknown legacy statuses, changed enum labels, and an invalid active-run partial unique index fail without mutation.
- The active-run index is unique on `(trade_date, scope_key)` with the `status = 'running'` predicate.
- Preserve matching logic, API schemas, CLI response rendering, DAG schedules, retries, task boundaries, and `completed_with_warnings` behavior.
- PostgreSQL integration tests requiring `TEST_POSTGRESQL_URL` are required for issue closure; skipped tests are not sufficient.

---

## File Structure

- `paper_trading/storage/matching_status_migration.py`: owns matching-run schema preflight, explicit table bootstrap, legacy varchar conversion, and enum/index validation.
- `tools/bootstrap_paper_matching_run_status.py`: parses operator flags, starts the transaction, calls bootstrap, and renders stable text/JSON output.
- `storage/storage_db.py`: creates normal metadata while explicitly excluding `paper_matching_runs` from startup DDL.
- `test/paper_trading/storage/test_matching_status_migration.py`: PostgreSQL integration coverage for preflight, fresh bootstrap, conversion, rejection, idempotency, and index behavior.
- `test/tools/test_bootstrap_paper_matching_run_status.py`: CLI transaction, output, direct-script entry point, and error behavior.
- `test/storage/test_storage_db.py`: regression coverage that startup metadata DDL excludes `PaperMatchingRun`.
- `docs/paper_trading.md`: documents the single explicit bootstrap procedure for fresh and legacy databases.
- Delete `tools/migrate_paper_matching_run_status_enum.py` and `test/tools/test_migrate_paper_matching_run_status_enum.py`: superseded conversion-only operator path.

### Task 1: Make Matching-Run DDL Explicit

**Files:**
- Modify: `storage/storage_db.py:421-428`
- Modify: `test/storage/test_storage_db.py:74-80`
- Test: `test/storage/test_storage_db.py`

**Interfaces:**
- Consumes: `Base.metadata.tables` and `tb_name_paper_matching_runs`.
- Produces: `_non_matching_run_tables() -> list[Any]`, the table collection passed to `Base.metadata.create_all` during normal startup.
- Produces: normal startup behavior that leaves `PaperMatchingRun.__table__` out of metadata DDL.

- [ ] **Step 1: Write the failing startup-DDL regression test**

Add a focused test that resets the storage singleton, substitutes a mock engine and `Base.metadata.create_all`, constructs `StorageDb` through `get_storage`, and inspects the call's `tables` keyword argument.

```python
def test_storage_startup_excludes_matching_runs_from_metadata_ddl(mock_config, monkeypatch):
    reset_storage()
    engine = Mock()
    create_all = Mock()
    monkeypatch.setattr("storage.storage_db.create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr("storage.storage_db.Base.metadata.create_all", create_all)

    get_storage(mock_config)

    tables = create_all.call_args.kwargs["tables"]
    assert all(table.name != "paper_matching_runs" for table in tables)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/storage/test_storage_db.py::test_storage_startup_excludes_matching_runs_from_metadata_ddl -v`

Expected: FAIL because current startup calls `Base.metadata.create_all(self.engine)` without a filtered `tables` collection.

- [ ] **Step 3: Implement the filtered metadata bootstrap**

Add a small module-level helper next to the metadata initialization globals and pass it to `create_all`:

```python
def _non_matching_run_tables() -> list[Any]:
    return [table for table in Base.metadata.sorted_tables if table.name != tb_name_paper_matching_runs]

# In StorageDb.__init__:
Base.metadata.create_all(self.engine, tables=_non_matching_run_tables())
```

Do not change the existing `ensure_a_stock_basic_schema`, `ensure_blackroom_records_table`, or `ensure_paper_trading_schema` call order. Confirm none of those helpers creates `PaperMatchingRun.__table__`.

- [ ] **Step 4: Run focused storage regressions**

Run: `uv run pytest test/storage/test_storage_db.py -v`

Expected: PASS, including existing paper-trading schema upgrade coverage and the new metadata-DDL exclusion contract.

- [ ] **Step 5: Commit the explicit startup boundary**

```bash
git add storage/storage_db.py test/storage/test_storage_db.py
```

### Task 2: Add Preflight Facts and Explicit Matching-Run Bootstrap

**Files:**
- Modify: `paper_trading/storage/matching_status_migration.py:9-163`
- Modify: `test/paper_trading/storage/test_matching_status_migration.py:15-271`
- Test: `test/paper_trading/storage/test_matching_status_migration.py`

**Interfaces:**
- Consumes: a SQLAlchemy PostgreSQL `Connection`, `PaperMatchingRun.__table__`, `MATCHING_STATUS_LABELS`, and existing `migrate_paper_matching_status_enum(connection, dry_run=False)`.
- Produces: `MatchingStatusBootstrapResult` with `dry_run: bool`, `table_exists: bool`, `table_created: bool`, `converted: bool`, `labels: tuple[str, ...]`, `observed_legacy_values: tuple[str | None, ...]`, and `index_verified: bool`.
- Produces: `bootstrap_paper_matching_run_status(connection: Connection, *, dry_run: bool = False) -> MatchingStatusBootstrapResult`.

- [ ] **Step 1: Write failing PostgreSQL bootstrap tests**

Add tests using the existing `postgres_schema` fixture, plus an empty-schema fixture that creates only the schema and sets its search path. Cover these exact contracts:

```python
def test_postgresql_bootstrap_dry_run_reports_missing_table_without_ddl(empty_postgres_schema):
    engine, schema = empty_postgres_schema
    with _connection(engine, schema) as connection:
        result = bootstrap_paper_matching_run_status(connection, dry_run=True)
        assert result.table_exists is False
        assert result.table_created is False
        assert result.labels == LABELS
        assert result.observed_legacy_values == ()
        assert connection.execute(text("SELECT to_regclass('paper_matching_runs')")).scalar_one() is None

def test_postgresql_bootstrap_creates_fresh_enum_table_and_index(empty_postgres_schema):
    engine, schema = empty_postgres_schema
    with _connection(engine, schema) as connection:
        result = bootstrap_paper_matching_run_status(connection)
        assert result.table_created is True
        assert result.labels == LABELS
        assert result.index_verified is True
```

For the existing legacy-table fixture, assert dry-run exposes sorted distinct legacy values and writes neither type nor table changes; assert live bootstrap converts varchar status, retains the active index, and a second call has `table_created is False` and `converted is False`.

- [ ] **Step 2: Run the PostgreSQL tests to verify failure**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_matching_status_migration.py -v`

Expected: FAIL on missing `bootstrap_paper_matching_run_status` and `MatchingStatusBootstrapResult`. If `TEST_POSTGRESQL_URL` is empty, stop this task and configure an isolated PostgreSQL database before claiming this acceptance criterion.

- [ ] **Step 3: Implement preflight and bootstrap without startup coupling**

Refactor shared catalog queries into private helpers, keeping all SQL schema-scoped with `current_schema()`. Add an immutable result and bootstrap function:

```python
@dataclass(frozen=True)
class MatchingStatusBootstrapResult:
    dry_run: bool
    table_exists: bool
    table_created: bool
    converted: bool
    labels: tuple[str, ...]
    observed_legacy_values: tuple[str | None, ...]
    index_verified: bool

def bootstrap_paper_matching_run_status(
    connection: Connection, *, dry_run: bool = False
) -> MatchingStatusBootstrapResult:
    ...
```

For PostgreSQL, inspect `to_regclass` before writes. For a missing table, dry-run returns the expected labels, `table_exists=False`, `table_created=False`, empty observed values, and `index_verified=False`; live mode calls `PaperMatchingRun.__table__.create(connection, checkfirst=False)`, then validates the enum labels and partial index. For an existing table, select distinct status values ordered with `NULLS FIRST`, reject any non-canonical value before DDL, and delegate conversion/index validation to `migrate_paper_matching_status_enum`.

Keep the non-PostgreSQL behavior write-free and return canonical labels, with `table_created=False` and `index_verified=False`. Never call bootstrap from `StorageDb`.

- [ ] **Step 4: Run PostgreSQL migration and matching regressions**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_matching_status_migration.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py -v`

Expected: PASS. The PostgreSQL suite proves fresh creation, dry-run non-mutation, legacy conversion, unknown-value rejection, idempotency, canonical labels, and active-index enforcement.

- [ ] **Step 5: Commit bootstrap storage behavior**

```bash
git add paper_trading/storage/matching_status_migration.py test/paper_trading/storage/test_matching_status_migration.py
```

### Task 3: Replace the Conversion-Only Operator Command

**Files:**
- Create: `tools/bootstrap_paper_matching_run_status.py`
- Delete: `tools/migrate_paper_matching_run_status_enum.py`
- Create: `test/tools/test_bootstrap_paper_matching_run_status.py`
- Delete: `test/tools/test_migrate_paper_matching_run_status_enum.py`

**Interfaces:**
- Consumes: `bootstrap_paper_matching_run_status(connection, dry_run: bool) -> MatchingStatusBootstrapResult`, `parse_config()`, and `get_storage().engine.begin()`.
- Produces: `main(argv: list[str] | None = None) -> int` and text/JSON output including table existence/creation, conversion, labels, observed legacy values, and index readiness.

- [ ] **Step 1: Write failing CLI tests**

Copy the existing fake transaction/engine/storage fixtures into the new test file and update imports to the bootstrap command. Assert direct script help works without `PYTHONPATH`, `--dry-run --json` forwards `dry_run=True`, and live output has every bootstrap result field:

```python
assert json.loads(capsys.readouterr().out) == {
    "converted": True,
    "dry_run": False,
    "index_verified": True,
    "labels": ["running", "completed", "completed_with_warnings", "failed"],
    "observed_legacy_values": ["completed", "running"],
    "table_created": False,
    "table_exists": True,
}
```

Retain tests proving exceptions roll back the transaction, log the error, write a concise stderr message, and return nonzero.

- [ ] **Step 2: Run the CLI tests to verify failure**

Run: `uv run pytest test/tools/test_bootstrap_paper_matching_run_status.py -v`

Expected: FAIL because the new command and bootstrap callable do not exist.

- [ ] **Step 3: Implement the replacement command and remove the old path**

Create the command by retaining the current parser/config/transaction structure, replacing its import and result serializer:

```python
from paper_trading.storage.matching_status_migration import (
    MatchingStatusBootstrapResult,
    bootstrap_paper_matching_run_status,
)

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        parse_config()
        with get_storage().engine.begin() as connection:
            result = bootstrap_paper_matching_run_status(connection, dry_run=args.dry_run)
        _print_result(result, json_output=args.json_output)
        return 0
    except Exception as exc:
        logger.exception("Paper matching run bootstrap failed: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
```

Delete the old conversion-only script and its tests; do not leave a second supported command or compatibility wrapper.

- [ ] **Step 4: Run CLI and script regressions**

Run: `uv run pytest test/tools/test_bootstrap_paper_matching_run_status.py test/tools/test_db_scripts.py -v`

Expected: PASS, including direct executable startup, stable output, dry-run forwarding, transaction rollback, and enum-aware export/import tests.

- [ ] **Step 5: Commit the supported operator interface**

```bash
git add tools/bootstrap_paper_matching_run_status.py test/tools/test_bootstrap_paper_matching_run_status.py
```

### Task 4: Prove Startup Non-Mutation and Preserve Matching Outcomes

**Files:**
- Modify: `test/paper_trading/storage/test_matching_status_migration.py`
- Modify: `test/paper_trading/api/test_matching_api.py:15-72` only if an existing assertion needs an explicit persistence check
- Test: `test/paper_trading/storage/test_matching_status_migration.py`
- Test: `test/paper_trading/api/test_matching_api.py`
- Test: `test/paper_trading/services/test_order_delete_service.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes: `StorageDb` startup, PostgreSQL catalog query for `paper_matching_run_status`, and the bootstrap function from Task 2.
- Produces: regression evidence that startup is enum-DDL free and that warning-completed matching runs continue to persist and surface their canonical value.

- [ ] **Step 1: Write the failing PostgreSQL startup non-mutation test**

In the PostgreSQL test module, use an isolated schema with a legacy varchar `paper_matching_runs` table and no enum. Configure a `StorageDb` instance to use that engine, bypass unrelated compatibility helpers, and clear `_metadata_initialized_pids`. Record the matching enum catalog result before and after initialization:

```python
before = connection.execute(text("SELECT count(*) FROM pg_type ...")).scalar_one()
StorageDb(config_that_uses_the_test_engine)
after = connection.execute(text("SELECT count(*) FROM pg_type ...")).scalar_one()
assert before == after == 0
assert connection.execute(text("SELECT atttypid::regtype::text FROM pg_attribute ...")).scalar_one() == "character varying"
```

Use `SET search_path` on connections created by the injected engine so catalog and metadata operations target the isolated test schema.

- [ ] **Step 2: Run the test to verify failure against current startup**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_matching_status_migration.py -k startup -v`

Expected: FAIL before Task 1 because `Base.metadata.create_all` creates the native enum/table. After Task 1, PASS without calling the explicit bootstrap function.

- [ ] **Step 3: Add the warning-status persistence assertion only if absent**

The API warning test already asserts the returned status. Add the direct matching-run persistence assertion there only when repository access already exposes the created run:

```python
runs = repo.list_matching_runs()
assert runs[-1].status == "completed_with_warnings"
```

Do not change matching service behavior or response schemas. Keep the existing CLI test that preserves warning fields and the replay test that records a warning run.

- [ ] **Step 4: Run end-to-end focused behavior coverage**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_matching_status_migration.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_matching_api.py test/tools/test_paper_trading_cli.py -v`

Expected: PASS. The output demonstrates explicit schema governance plus persistence and API/CLI exposure of `completed_with_warnings` without an HTTP 500.

- [ ] **Step 5: Commit governance evidence**

```bash
git add test/paper_trading/storage/test_matching_status_migration.py test/paper_trading/api/test_matching_api.py
```

### Task 5: Document the Single Bootstrap Procedure and Run Final Gates

**Files:**
- Modify: `docs/paper_trading.md:457-542`

**Interfaces:**
- Consumes: `tools/bootstrap_paper_matching_run_status.py` and its stable `--dry-run --json` output.
- Produces: an operator procedure covering fresh database setup, legacy conversion, preflight, live bootstrap, independent verification, deployment sequencing, and warning-status validation.

- [ ] **Step 1: Update the matching-run status documentation**

Replace references to `migrate_paper_matching_run_status_enum.py` with the sole supported command:

```bash
uv run tools/bootstrap_paper_matching_run_status.py --dry-run --json
uv run tools/bootstrap_paper_matching_run_status.py --json
```

State explicitly that normal API, Celery, Airflow, and `StorageDb` startup do not create or alter `paper_matching_runs` or `paper_matching_run_status`. Add the fresh-install case: run the same bootstrap command before starting matching writers; it creates the table, enum, and verified active-run index. Retain the isolation, backup, invalid-status resolution, independent PostgreSQL verification, deployment order, and `completed_with_warnings` validation steps.

- [ ] **Step 2: Run final targeted quality gates**

Run: `uv run ruff format --check storage/storage_db.py paper_trading/storage/matching_status_migration.py tools/bootstrap_paper_matching_run_status.py test/storage/test_storage_db.py test/paper_trading/storage/test_matching_status_migration.py test/tools/test_bootstrap_paper_matching_run_status.py`

Expected: PASS.

Run: `uv run ruff check storage/storage_db.py paper_trading/storage/matching_status_migration.py tools/bootstrap_paper_matching_run_status.py test/storage/test_storage_db.py test/paper_trading/storage/test_matching_status_migration.py test/tools/test_bootstrap_paper_matching_run_status.py`

Expected: PASS.

Run: `uv run mypy storage paper_trading`

Expected: PASS.

- [ ] **Step 3: Run the complete required behavior suite**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_matching_status_migration.py test/storage/test_storage_db.py test/tools/test_bootstrap_paper_matching_run_status.py test/tools/test_db_scripts.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_matching_api.py test/tools/test_paper_trading_cli.py -v`

Expected: PASS with no skipped PostgreSQL migration tests.

- [ ] **Step 4: Inspect the final change set**

Run: `git diff --check && git status --short && git log --oneline -10`

Expected: no whitespace errors; only the intended issue #35 changes are present in this isolated worktree.

- [ ] **Step 5: Commit the operator documentation**

```bash
git add docs/paper_trading.md
```

## Plan Self-Review

- Spec coverage: Task 1 isolates startup DDL; Task 2 supplies explicit dry-run/live bootstrap for fresh and legacy schemas; Task 3 establishes one supported command; Task 4 proves PostgreSQL startup non-mutation and preserves warning behavior; Task 5 documents and verifies the operator workflow.
- Placeholder scan: all functions, fields, files, commands, and expected test outcomes are specified. The PostgreSQL URL is intentionally an external required test fixture, not a deferred implementation item.
- Type consistency: `bootstrap_paper_matching_run_status` returns `MatchingStatusBootstrapResult` consistently in Tasks 2 and 3; `StorageDb` continues to own normal metadata setup but receives no bootstrap call.
