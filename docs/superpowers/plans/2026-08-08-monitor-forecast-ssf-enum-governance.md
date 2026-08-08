# Monitor and Forecast SSF Enum Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the existing Monitor and Forecast SSF enum migration into one explicit enum-governance command without changing valid monitor or candidate lifecycle behavior.

**Architecture:** Split each existing domain migration into composable preflight, apply, verify, and rollback phases, preserving its domain-owned catalog and PostgreSQL rules. A new governance coordinator performs every domain preflight before any DDL and exposes the only supported command; the former Monitor and Paper Trading commands are removed after their behavior is covered through the coordinator.

**Tech Stack:** Python 3.11+, SQLAlchemy, PostgreSQL native enums and JSONB checks, SQLite, pytest, Ruff, uv.

## Global Constraints

- Run all repository Python commands with `uv run`.
- Preserve canonical readable enum labels in `monitor/domain_enums.py` and existing API/CLI values.
- Do not change Monitor scheduling, DAG dependencies, retries, task boundaries, SLA, or Forecast SSF candidate lifecycle semantics.
- Run live enum DDL only under the operator-managed maintenance window with all business writers stopped.
- PostgreSQL integration tests must skip with `TEST_POSTGRESQL_URL` unset; SQLite tests do not substitute for PostgreSQL enum DDL coverage.
- Every migration failure must roll back the shared transaction before any partial schema change commits.
- Do not leave `tools/migrate_monitor_enums.py` or `tools/migrate_paper_trading_enums.py` as separate production migration interfaces.

---

## File Structure

- Create: `storage/enum_governance.py` — common adapter protocol, result types, and coordinator that establishes the all-domain-preflight-before-DDL transaction contract.
- Create: `tools/migrate_enums.py` — sole operator command, argument parsing, configuration bootstrap, transaction boundary, and stable human/JSON reporting.
- Modify: `monitor/storage/enum_migration.py` — expose Monitor/Forecast SSF migration phases through the common adapter without changing its enum definitions, validation, condition check, or rollback rules.
- Modify: `paper_trading/storage/enum_migration.py` — expose Paper Trading migration phases through the common adapter without changing its enum catalog or index semantics.
- Modify: `tools/db_common.sh`, `tools/db_export.sh`, `tools/db_import.sh` — add the Monitor enum catalog and table/type mapping to backup and clean-restore ordering.
- Delete: `tools/migrate_monitor_enums.py`, `tools/migrate_paper_trading_enums.py` — remove superseded migration interfaces.
- Create: `test/storage/test_enum_governance.py` — unit tests for phase ordering, aggregate results, and shared transaction failure behavior.
- Create: `test/tools/test_migrate_enums.py` — command interface and output tests.
- Modify: `test/monitor/storage/test_enum_migration.py` and `test/paper_trading/storage/test_enum_migration.py` — retain domain integration coverage against adapter entry points and add coordinated atomicity coverage.
- Delete: `test/tools/test_migrate_monitor_enums.py`, `test/tools/test_migrate_paper_trading_enums.py` — remove superseded command tests.
- Modify: `test/tools/test_db_scripts.py` — prove Monitor types are emitted before dependent selected-table dumps and removed only after dependent clean drops.
- Modify: `docs/paper_trading.md` or the existing enum operations guide selected by the repository — document the unified command, governed Monitor types, maintenance-window requirement, dry-run, verification, rollback, and restore ordering.

### Task 1: Define the Coordinator Contract

**Files:**
- Create: `storage/enum_governance.py`
- Test: `test/storage/test_enum_governance.py`

**Interfaces:**
- Consumes: an SQLAlchemy `Connection`; adapter callbacks supplied by domain modules.
- Produces: `EnumGovernanceAdapter`, `EnumGovernanceDomainResult`, `EnumGovernanceResult`, and `migrate_enums(connection, *, dry_run: bool = False, rollback: bool = False)`.
- `EnumGovernanceAdapter` must expose `name`, `preflight(connection, *, rollback)`, `apply(connection)`, `verify(connection, *, rollback)`, `rollback(connection)`, and `result(*, dry_run, rollback, converted, rolled_back)`.

- [ ] **Step 1: Write failing coordinator ordering tests**

Create fake adapters that append phase names to an events list. Assert normal apply preflights all adapters before the first apply, dry-run invokes only preflight, and a failing second preflight prevents the first adapter from applying:

```python
def test_normal_migration_preflights_every_adapter_before_ddl() -> None:
    events: list[str] = []
    result = migrate_enums(FakeConnection(), adapters=(_adapter("paper", events), _adapter("monitor", events)))

    assert events == ["paper.preflight", "monitor.preflight", "paper.apply", "monitor.apply", "paper.verify", "monitor.verify"]
    assert result.converted is True


def test_preflight_failure_prevents_every_apply() -> None:
    events: list[str] = []

    with pytest.raises(EnumGovernanceError, match="monitor preflight failed"):
        migrate_enums(FakeConnection(), adapters=(_adapter("paper", events), _adapter("monitor", events, fail_preflight=True)))

    assert events == ["paper.preflight", "monitor.preflight"]
```

- [ ] **Step 2: Run the coordinator tests to verify they fail**

Run: `uv run pytest test/storage/test_enum_governance.py -v`

Expected: FAIL because `storage.enum_governance` does not exist.

- [ ] **Step 3: Implement the minimal coordinator**

Define frozen result dataclasses with `dry_run`, `rollback`, `converted`, `rolled_back`, and ordered domain results. For PostgreSQL, invoke all adapter `preflight` methods first. On normal apply, run `apply` for each adapter and then verify each adapter. On rollback, run each adapter rollback and then verify its legacy form. Return a no-change result for non-PostgreSQL connections, preserving each adapter’s own portable behavior.

```python
def migrate_enums(connection: Connection, *, dry_run: bool = False, rollback: bool = False) -> EnumGovernanceResult:
    adapters = ENUM_GOVERNANCE_ADAPTERS
    for adapter in adapters:
        adapter.preflight(connection, rollback=rollback)
    if dry_run:
        return _result(adapters, dry_run=True, rollback=rollback)
    if rollback:
        changed = [adapter.rollback(connection) for adapter in adapters]
        for adapter in adapters:
            adapter.verify(connection, rollback=True)
        return _result(adapters, rollback=True, rolled_back=any(changed))
    changed = [adapter.apply(connection) for adapter in adapters]
    for adapter in adapters:
        adapter.verify(connection, rollback=False)
    return _result(adapters, converted=any(changed))
```

Translate a domain migration exception into `EnumGovernanceError` only when adding the adapter name makes the failure more actionable; retain the original error as the exception cause.

- [ ] **Step 4: Run the coordinator tests to verify they pass**

Run: `uv run pytest test/storage/test_enum_governance.py -v`

Expected: PASS, including normal, dry-run, rollback, and preflight-failure ordering cases.

- [ ] **Step 5: Commit the coordinator contract**

```bash
git add storage/enum_governance.py test/storage/test_enum_governance.py
```

### Task 2: Adapt Monitor and Forecast SSF Migration Phases

**Files:**
- Modify: `monitor/storage/enum_migration.py:141-343`
- Modify: `test/monitor/storage/test_enum_migration.py:149-381`

**Interfaces:**
- Consumes: `EnumGovernanceAdapter` from `storage.enum_governance` and existing `MONITOR_ENUM_GROUPS`.
- Produces: `MONITOR_ENUM_ADAPTER`, with `preflight`, `apply`, `verify`, `rollback`, and result reporting compatible with Task 1.
- Preserves: `migrate_monitor_enums(connection, *, dry_run=False, rollback=False)` as a non-public compatibility wrapper only until the old CLI has been deleted; it delegates to the adapter phases and is no longer documented as an operator interface.

- [ ] **Step 1: Write failing phase-level Monitor tests**

Add tests proving that preflight does not create enum types or the condition check, apply creates all four types and the `ck_stock_monitor_targets_condition_type` check only after a successful preflight, and adapter rollback restores `VARCHAR` columns and removes the check:

```python
def test_adapter_preflight_validates_legacy_condition_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        MONITOR_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert _enum_types(connection) == set()
        assert not _check_exists(connection)
```

- [ ] **Step 2: Run the new Monitor phase tests to verify they fail**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/monitor/storage/test_enum_migration.py -k adapter -v`

Expected: FAIL because `MONITOR_ENUM_ADAPTER` is undefined. When the variable is unset, pytest must explicitly skip these PostgreSQL tests.

- [ ] **Step 3: Extract Monitor phase methods without weakening validation**

Split `migrate_monitor_enums` into adapter methods that reuse the existing `_preflight`, `_alter_group`, `_add_condition_check`, `_ensure_indexes`, `_verify`, and `_rollback` helpers. Preserve all current rejection behavior for invalid legacy values, invalid condition documents, unexpected enum labels, indexes, defaults, partial table presence, and unmanaged dependencies. Ensure the apply phase creates missing tables only after the unified preflight passes.

- [ ] **Step 4: Run Monitor migration coverage**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/monitor/storage/test_enum_migration.py -v`

Expected: PASS or explicit skips when PostgreSQL is unavailable. Existing assertions for shared `monitor_market`, conditions, defaults, indexes, idempotency, and rollback remain green.

- [ ] **Step 5: Commit the Monitor adapter**

```bash
git add monitor/storage/enum_migration.py test/monitor/storage/test_enum_migration.py
```

### Task 3: Adapt Paper Trading Migration Phases

**Files:**
- Modify: `paper_trading/storage/enum_migration.py:275-448`
- Modify: `test/paper_trading/storage/test_enum_migration.py:128-322`

**Interfaces:**
- Consumes: `EnumGovernanceAdapter` from `storage.enum_governance` and `PAPER_TRADING_ENUM_GROUPS`.
- Produces: `PAPER_TRADING_ENUM_ADAPTER`, exposing the same phase interface as `MONITOR_ENUM_ADAPTER`.
- Preserves: matching-run partial-index validation, pre-existing matching enum handling, complete Paper Trading type catalog, and reversible string conversions.

- [ ] **Step 1: Write failing Paper Trading phase tests**

Add an adapter preflight test that verifies all legacy values and the active matching-run partial index without DDL, plus an apply/rollback phase test:

```python
def test_adapter_preflight_does_not_convert_matching_status(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        PAPER_TRADING_ENUM_ADAPTER.preflight(connection, rollback=False)

        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _enum_types(connection) == set()
```

- [ ] **Step 2: Run the new Paper Trading phase tests to verify they fail**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_enum_migration.py -k adapter -v`

Expected: FAIL because `PAPER_TRADING_ENUM_ADAPTER` is undefined, or explicit skips without PostgreSQL.

- [ ] **Step 3: Extract Paper Trading phase methods**

Expose an adapter around the current `_preflight`, `_create_missing_tables`, `_create_type`, `_alter_group`, `_verify`, and `_rollback` helpers. Preserve the existing behavior for missing-table bootstrap, preconverted groups, enum labels, defaults, normal and partial indexes, and dependency rejection. Do not move Monitor rules into this module.

- [ ] **Step 4: Run all Paper Trading enum integration tests**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_enum_migration.py -v`

Expected: PASS or explicit skips. The matching-run `completed_with_warnings` enum label and active-run partial unique index remain verified.

- [ ] **Step 5: Commit the Paper Trading adapter**

```bash
git add paper_trading/storage/enum_migration.py test/paper_trading/storage/test_enum_migration.py
```

### Task 4: Add the Unified Operator Command

**Files:**
- Create: `tools/migrate_enums.py`
- Create: `test/tools/test_migrate_enums.py`
- Delete: `tools/migrate_monitor_enums.py`
- Delete: `tools/migrate_paper_trading_enums.py`
- Delete: `test/tools/test_migrate_monitor_enums.py`
- Delete: `test/tools/test_migrate_paper_trading_enums.py`

**Interfaces:**
- Consumes: `conf.parse_config()`, `storage.get_storage()`, and `storage.enum_governance.migrate_enums`.
- Produces: `uv run tools/migrate_enums.py [--dry-run] [--rollback] [--json]` as the only supported migration command.
- Output: includes `dry_run`, `rollback`, `converted`, `rolled_back`, and ordered per-domain groups in stable human-readable and sorted JSON formats.

- [ ] **Step 1: Write failing unified command tests**

Build lightweight fake storage and result objects. Assert the command calls configuration parsing, holds result formatting inside `with engine.begin()` so output errors roll back the transaction, forwards flags, emits both Paper Trading and Monitor groups, rejects abbreviated options, and works from `/tmp`:

```python
def test_main_emits_stable_json_for_all_domains(monkeypatch, capsys) -> None:
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(FakeTransaction()))
    monkeypatch.setattr(command, "migrate_enums", lambda connection, **kwargs: _result_with_paper_and_monitor_groups())

    assert command.main(["--dry-run", "--json"]) == 0
    assert [domain["name"] for domain in json.loads(capsys.readouterr().out)["domains"]] == ["paper_trading", "monitor"]
```

- [ ] **Step 2: Run unified command tests to verify they fail**

Run: `uv run pytest test/tools/test_migrate_enums.py -v`

Expected: FAIL because the unified command does not exist.

- [ ] **Step 3: Implement the single command and remove superseded commands**

Copy only the shared argument handling and error-reporting behavior from the old commands. Invoke `parse_config()`, obtain storage, begin one transaction, call `migrate_enums`, and render the aggregate result before leaving the transaction. Use `argparse.ArgumentParser(..., allow_abbrev=False)`. Delete both dedicated command modules and their tests after their scenarios are represented in the new suite.

- [ ] **Step 4: Run command tests to verify they pass**

Run: `uv run pytest test/tools/test_migrate_enums.py -v`

Expected: PASS. `uv run tools/migrate_enums.py --help` lists exactly `--dry-run`, `--rollback`, and `--json` as operation flags.

- [ ] **Step 5: Commit the unified command**

```bash
git add tools/migrate_enums.py test/tools/test_migrate_enums.py
```

### Task 5: Preserve Monitor Enum Backup and Restore Ordering

**Files:**
- Modify: `tools/db_common.sh:54-101`
- Modify: `tools/db_export.sh:102-231`
- Modify: `tools/db_import.sh:99-120`
- Modify: `test/tools/test_db_scripts.py`

**Interfaces:**
- Consumes: the `monitor_market`, `monitor_frequency`, `monitor_reset_mode`, and `forecast_ssf_candidate_state` definitions and their table mapping.
- Produces: dumps that create any needed Monitor type before `stock_monitor_targets` or `forecast_ssf_candidates`; clean full restores that drop those tables before types; selected-table clean restores that retain shared `monitor_market` when its other dependent table is unselected.

- [ ] **Step 1: Write failing backup/restore ordering tests**

Add script tests covering all Monitor types and the shared market type:

```python
def test_selected_monitor_target_dump_creates_required_monitor_types_before_table(tmp_path: Path):
    result, dump = _run_export(tmp_path, table="stock_monitor_targets")

    assert result.returncode == 0
    assert dump.index('CREATE TYPE "public"."monitor_market"') < dump.index('CREATE TABLE public.stock_monitor_targets')
    assert 'CREATE TYPE "public"."forecast_ssf_candidate_state"' not in dump


def test_selected_monitor_target_clean_does_not_drop_shared_monitor_market(tmp_path: Path):
    result, commands = _run_clean_import(tmp_path, table="stock_monitor_targets")

    assert result.returncode == 0
    assert 'DROP TYPE IF EXISTS "public"."monitor_market"' not in commands
```

- [ ] **Step 2: Run the backup/restore tests to verify they fail**

Run: `uv run pytest test/tools/test_db_scripts.py -k "monitor or enum" -v`

Expected: FAIL because the shell catalog only recognizes Paper Trading types.

- [ ] **Step 3: Add a single shared enum catalog and mapping**

Replace Paper-Trading-specific naming in `db_common.sh` with generic business enum arrays and helper functions. Add the four Monitor types and their exact table relationships. Retain existing Paper Trading mappings unchanged. For `monitor_market`, mark it non-droppable on selected-table clean restores because `stock_monitor_targets` and `forecast_ssf_candidates` share it. Preserve the full clean reverse-table-then-type ordering.

- [ ] **Step 4: Run script coverage to verify it passes**

Run: `uv run pytest test/tools/test_db_scripts.py -v`

Expected: PASS, including all existing Paper Trading ordering and clean safety cases plus new Monitor cases.

- [ ] **Step 5: Commit backup/restore support**

```bash
git add tools/db_common.sh tools/db_export.sh tools/db_import.sh test/tools/test_db_scripts.py
```

### Task 6: Add Coordinated PostgreSQL Atomicity Coverage

**Files:**
- Modify: `test/monitor/storage/test_enum_migration.py`
- Modify: `test/paper_trading/storage/test_enum_migration.py`
- Modify: `test/storage/test_enum_governance.py`

**Interfaces:**
- Consumes: `migrate_enums` and the two domain adapters from Tasks 1-3.
- Produces: proof that an invalid Monitor condition prevents conversion of Paper Trading values and that invalid Paper Trading legacy values prevent conversion of Monitor values when both domains are governed in one transaction.

- [ ] **Step 1: Write a failing shared-transaction PostgreSQL test**

Use one disposable schema containing the legacy subsets needed by both adapters. Insert an invalid Monitor condition after creating valid Paper Trading rows, then run the coordinator inside `engine.begin()`:

```python
with pytest.raises(EnumGovernanceError, match="monitor"):
    migrate_enums(connection)

assert _paper_column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
assert _monitor_column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
assert _all_managed_enum_types(connection) == set()
```

- [ ] **Step 2: Run the atomicity test to verify it fails**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/storage/test_enum_governance.py -k atomic -v`

Expected: FAIL before the coordinator has both adapters wired into its default registry, or explicit skip without PostgreSQL.

- [ ] **Step 3: Wire the default adapter registry and preserve transaction scope**

Set `ENUM_GOVERNANCE_ADAPTERS` in deterministic order: Paper Trading first, Monitor second. Do not open a nested transaction in the coordinator or adapters. The command’s `engine.begin()` remains the only transaction owner, so exceptions roll back every prior DDL operation.

- [ ] **Step 4: Run all focused enum migration tests**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/storage/test_enum_governance.py test/paper_trading/storage/test_enum_migration.py test/monitor/storage/test_enum_migration.py -v`

Expected: PASS or explicit PostgreSQL skips. The atomicity assertion must pass when a test database is available.

- [ ] **Step 5: Commit coordinated integration coverage**

```bash
git add storage/enum_governance.py test/storage/test_enum_governance.py test/paper_trading/storage/test_enum_migration.py test/monitor/storage/test_enum_migration.py
```

### Task 7: Document Operations and Run Final Verification

**Files:**
- Modify: the existing enum migration operations guide identified by `rg -n "migrate_paper_trading_enums|migrate_monitor_enums|enum migration" docs README.md`
- Verify: all files from Tasks 1-6

**Interfaces:**
- Consumes: final unified command and backup/restore behavior.
- Produces: one authoritative operator procedure for enum governance.

- [ ] **Step 1: Replace old command references**

Remove references to `tools/migrate_monitor_enums.py` and `tools/migrate_paper_trading_enums.py`. Document the single command and exact phases:

```markdown
1. Stop every business writer while leaving PostgreSQL running and retain a verified backup.
2. Run `uv run tools/migrate_enums.py --dry-run --json` and resolve every reported preflight error.
3. Run `uv run tools/migrate_enums.py --json` during the maintenance window.
4. Run focused Monitor and Paper Trading write-path smoke tests before restarting workers.
5. Use `uv run tools/migrate_enums.py --rollback --json` only as the tested schema rollback procedure.
```

State that Monitor condition JSON receives application validation for conditional rules and a minimal PostgreSQL object/type check for direct SQL. List all four Monitor types and their restore ordering constraints.

- [ ] **Step 2: Verify docs no longer expose obsolete commands**

Run: `rg -n "migrate_monitor_enums|migrate_paper_trading_enums" README.md docs tools test`

Expected: no production documentation or command references. Test fixtures may mention old modules only if they are being deleted in the same change; final output should be empty.

- [ ] **Step 3: Run portable contract and command tests**

Run: `uv run pytest test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/storage/test_forecast_ssf_candidate_storage.py test/storage/test_enum_governance.py test/tools/test_migrate_enums.py test/tools/test_db_scripts.py -v`

Expected: PASS. This proves condition validation, storage write boundaries, candidate lifecycle behavior, coordinator behavior, unified CLI behavior, and backup/restore ordering.

- [ ] **Step 4: Run PostgreSQL migration tests**

Run: `TEST_POSTGRESQL_URL="$TEST_POSTGRESQL_URL" uv run pytest test/paper_trading/storage/test_enum_migration.py test/monitor/storage/test_enum_migration.py test/storage/test_enum_governance.py -v`

Expected: PASS against a configured PostgreSQL database or explicit skips when it is unavailable. Do not claim PostgreSQL coverage ran if the tests skipped.

- [ ] **Step 5: Run static checks and inspect scope**

Run: `uv run ruff format --check storage/enum_governance.py monitor/storage/enum_migration.py paper_trading/storage/enum_migration.py tools/migrate_enums.py test/storage/test_enum_governance.py test/tools/test_migrate_enums.py && uv run ruff check storage/enum_governance.py monitor/storage/enum_migration.py paper_trading/storage/enum_migration.py tools/migrate_enums.py test/storage/test_enum_governance.py test/tools/test_migrate_enums.py && uv run mypy storage/enum_governance.py monitor/storage/enum_migration.py paper_trading/storage/enum_migration.py && git diff --check && git status --short`

Expected: no formatter, lint, type, or whitespace errors; only intentional changes are present. Do not stage unrelated `data/` or pre-existing untracked planning artifacts.

- [ ] **Step 6: Commit operations documentation and verification-ready changes**

```bash
git add docs
git commit -m "Document unified enum governance operations"
```
