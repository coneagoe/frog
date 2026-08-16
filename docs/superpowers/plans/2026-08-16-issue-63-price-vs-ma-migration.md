# Issue 63 Price-vs-MA Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely migrate every persisted `price_vs_ma` monitor target to `close_cross_ma`, then reject the retired condition everywhere.

**Architecture:** Add an idempotent storage migration that rewrites persisted condition JSON before application validation and PostgreSQL condition constraints remove `price_vs_ma`. Keep existing target rows and alert-state fields intact; disable migrated targets that cannot be legally evaluated by the A-share daily `close_cross_ma` runner. Remove runtime/user-input compatibility only after the migration path is covered by tests.

**Tech Stack:** Python 3.11+, SQLAlchemy, PostgreSQL JSONB constraints, SQLite-compatible storage bootstrap, pytest, repository commands via `uv run` / `tools/run_tests.sh`.

## Global Constraints

- Use `uv run` for Python commands in this repo; do not use bare `python` or `python3`.
- Use `tools/run_tests.sh` for PostgreSQL-dependent tests so `TEST_POSTGRESQL_URL` is supplied.
- Preserve target `id`, `stock_code`, `market`, `condition` metadata outside the changed type, `frequency`, `workflow`, `note`, `reset_mode`, `enabled` state for A-share daily targets, `last_state`, `triggered_at`, and candidate linkage.
- Preserve existing `last_state=True` and `last_state=False`; migration alone must not create catch-up alerts.
- Disable migrated non-A-share or non-daily targets explicitly and produce diagnostics that include target ID and market.
- PostgreSQL governance must accept `close_cross_ma` and reject `price_vs_ma` only after old records have been rewritten.
- SQLite migration/bootstrap must be repeatable.
- Remove `price_vs_ma` from user input validation, condition evaluation, documentation, and test fixtures after migration coverage exists.

---

## Files

- Modify: `monitor/storage/enum_migration.py` — PostgreSQL preflight/data rewrite/check sequencing and diagnostics.
- Modify: `storage/storage_db.py` — SQLite/bootstrap migration for existing local tables before target validation paths run.
- Modify: `monitor/condition_validation.py` — reject new `price_vs_ma` inputs.
- Modify: `monitor/condition.py` — remove `price_vs_ma` evaluator branch.
- Modify: `monitor/monitor_runner.py` — remove old daily final-close compatibility fetch path.
- Modify: `monitor/monitor_target_service.py` — remove label compatibility and keep `close_cross_ma` scope enforcement.
- Modify: `docs/stock_monitor.md` — document only supported MA monitor conditions.
- Modify: `test/monitor/storage/test_enum_migration.py` — PostgreSQL migration and constraint-sequencing coverage.
- Modify: `test/monitor/test_condition_validation.py`, `test/monitor/test_condition.py`, `test/monitor/test_monitor_target_service.py`, `test/monitor/test_monitor_runner.py` — compatibility removal and behavior fixture updates.
- Add or modify: focused `storage/storage_db.py` tests if an existing SQLite bootstrap test can cover repeatability cheaply.

## Verification Claim

**Claim:** After implementation, any persisted `price_vs_ma` target is converted before stricter validation/constraints reject it; all new application and direct-SQL inputs reject `price_vs_ma`; migrated valid A-share daily targets keep metadata and state; migrated unsupported targets are retained but disabled with diagnostics.

**Meaningful uncertainty:** Whether migration runs early enough in both PostgreSQL enum governance and SQLite table bootstrap; whether JSON rewrites preserve extra condition metadata such as `workflow`; whether existing true/false `last_state` is accidentally reset.

**Evidence path:** Write failing migration tests first, implement the smallest reusable conversion helper, then run focused unit tests plus PostgreSQL integration tests through `tools/run_tests.sh`. Final confidence requires a targeted grep proving no active code/docs/tests retain `price_vs_ma` compatibility except migration tests/fixtures explicitly asserting rejection/conversion.

---

### Task 1: PostgreSQL Data Migration Before Constraint Tightening

**Files:**
- Modify: `test/monitor/storage/test_enum_migration.py`
- Modify: `monitor/storage/enum_migration.py`

**Interfaces:**
- Produces: `_migrate_price_vs_ma_conditions(connection: Connection) -> tuple[PriceVsMaMigrationDiagnostic, ...]`
- Produces: `PriceVsMaMigrationDiagnostic(target_id: int, market: str | None, frequency: str | None, disabled: bool, reason: str)`
- Consumes: existing `migrate_monitor_enums(connection)` and named check `ck_stock_monitor_targets_condition_type`.

- [ ] **Step 1: Write failing PostgreSQL migration tests**

Add tests with legacy rows that include all relevant columns in the fixture schema (`workflow`, `note`, `enabled`, `last_state`, `triggered_at`) and conditions such as:

```python
def test_apply_migrates_price_vs_ma_targets_before_tightening_condition_check(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN note text"))
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN workflow varchar(64)"))
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN enabled boolean NOT NULL DEFAULT true"))
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN last_state boolean NOT NULL DEFAULT false"))
        connection.execute(text("ALTER TABLE stock_monitor_targets ADD COLUMN triggered_at timestamptz"))
        connection.execute(text(
            "INSERT INTO stock_monitor_targets "
            "(id, stock_code, market, condition, frequency, reset_mode, note, workflow, enabled, last_state, triggered_at) "
            "VALUES "
            "(1, '600001', 'A', '{\"type\":\"price_vs_ma\",\"direction\":\"above\",\"period\":20,\"workflow\":\"forecast_ssf_ma20\"}'::jsonb, "
            "'daily', 'manual', 'keep note', 'forecast_ssf_ma20', true, true, '2026-06-03 15:30:00+08'), "
            "(2, '00700', 'HK', '{\"type\":\"price_vs_ma\",\"direction\":\"above\",\"period\":20}'::jsonb, "
            "'daily', 'auto', 'hk note', NULL, true, false, NULL)"
        ))

        result = migrate_monitor_enums(connection)

        rows = connection.execute(text(
            "SELECT id, market, condition::jsonb, frequency, reset_mode, note, workflow, enabled, last_state, triggered_at "
            "FROM stock_monitor_targets ORDER BY id"
        )).all()
        assert result.converted is True
        assert rows[0].condition["type"] == "close_cross_ma"
        assert rows[0].enabled is True
        assert rows[0].last_state is True
        assert rows[0].note == "keep note"
        assert rows[0].workflow == "forecast_ssf_ma20"
        assert rows[1].condition["type"] == "close_cross_ma"
        assert rows[1].enabled is False
        assert rows[1].last_state is False
```

Add a rerun test asserting a second `migrate_monitor_enums(connection)` returns `converted is False` and leaves row values unchanged.

- [ ] **Step 2: Run tests to verify failure**

Run: `tools/run_tests.sh test/monitor/storage/test_enum_migration.py -v`

Expected: FAIL because `price_vs_ma` remains accepted in constraints and rows are not rewritten/disabled.

- [ ] **Step 3: Implement PostgreSQL migration helper**

In `monitor/storage/enum_migration.py`, add a dataclass and helper that:

```python
@dataclass(frozen=True)
class PriceVsMaMigrationDiagnostic:
    target_id: int
    market: str | None
    frequency: str | None
    disabled: bool
    reason: str
```

Implementation rules:
- Select rows where `condition::jsonb->>'type' = 'price_vs_ma'`.
- Rewrite `condition` with `jsonb_set(condition::jsonb, '{type}', '"close_cross_ma"'::jsonb, false)` so all extra keys are retained.
- For rows where `market = 'A' AND frequency = 'daily'`, preserve `enabled` exactly.
- For all other migrated rows, set `enabled = false` when the column exists and return diagnostics with reason `close_cross_ma unsupported outside A daily scope`.
- Never update `last_state` or `triggered_at`.
- Safely no-op if `stock_monitor_targets` is absent or lacks optional legacy columns.

Call this helper inside `_adapter_apply` before `_add_condition_check(connection)`, after preflight has verified known legacy data but before the constraint is tightened.

- [ ] **Step 4: Tighten condition governance after migration**

Change `_CONDITION_CHECK_SQL`, `_NORMALIZED_CONDITION_CHECK`, and legacy detection so final governance includes `close_cross_ma` and excludes `price_vs_ma`; keep legacy-check recognition for the previous constraint so it can be replaced on apply.

- [ ] **Step 5: Run PostgreSQL migration tests**

Run: `tools/run_tests.sh test/monitor/storage/test_enum_migration.py -v`

Expected: PASS.

---

### Task 2: SQLite Bootstrap Migration and Repeatability

**Files:**
- Modify: `storage/storage_db.py`
- Modify or add: storage tests covering local SQLite monitor target bootstrap.

**Interfaces:**
- Produces: `StorageDb.ensure_monitor_targets_table()` rewrites legacy `price_vs_ma` rows before service validation can reject them.
- Consumes: SQLAlchemy engine/session already owned by `StorageDb`.

- [ ] **Step 1: Write failing SQLite repeatability test**

Create or extend a focused storage test that builds a SQLite `stock_monitor_targets` table with rows for A daily and HK daily `price_vs_ma`, calls `ensure_monitor_targets_table()` twice, then asserts:
- A daily row has condition type `close_cross_ma` and original enabled/last_state values.
- HK row has condition type `close_cross_ma`, `enabled = false`, and preserved `last_state`.
- Second call changes nothing and raises no error.

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest <chosen-test-file>::test_sqlite_price_vs_ma_migration_is_repeatable -v`

Expected: FAIL because SQLite bootstrap does not rewrite legacy condition JSON.

- [ ] **Step 3: Implement SQLite-safe migration**

In `ensure_monitor_targets_table()` after creating/adding required columns but before loading targets for validation, execute a dialect-aware migration:
- If dialect is SQLite, read matching rows into Python, update condition dicts, and write JSON back with SQLAlchemy parameters.
- If unsupported target scope, set `enabled=False` and log a warning containing target ID and market.
- Keep this helper idempotent by selecting only `price_vs_ma` rows.

- [ ] **Step 4: Run SQLite test**

Run: `uv run pytest <chosen-test-file>::test_sqlite_price_vs_ma_migration_is_repeatable -v`

Expected: PASS.

---

### Task 3: Remove Application Compatibility

**Files:**
- Modify: `monitor/condition_validation.py`
- Modify: `monitor/condition.py`
- Modify: `monitor/monitor_runner.py`
- Modify: `monitor/monitor_target_service.py`
- Modify: `test/monitor/test_condition_validation.py`
- Modify: `test/monitor/test_condition.py`
- Modify: `test/monitor/test_monitor_target_service.py`
- Modify: `test/monitor/test_monitor_runner.py`

**Interfaces:**
- Consumes: Task 1/2 migration guarantee that persisted rows no longer need runtime `price_vs_ma` support.
- Produces: application-level validation rejects new `price_vs_ma`; runtime has no evaluation branch or special fetch path.

- [ ] **Step 1: Update tests first**

Replace acceptance tests with explicit rejection tests:

```python
def test_validate_condition_rejects_price_vs_ma():
    with pytest.raises(ValueError, match="condition.type"):
        validate_condition({"type": "price_vs_ma", "direction": "above", "period": 20})
```

Remove `test_price_vs_ma_uses_latest_close_and_requires_strictly_above`, `test_price_vs_ma_requires_complete_daily_history`, `test_run_daily_monitor_uses_final_close_for_price_vs_ma`, and `test_add_target_accepts_price_vs_ma_condition`; add service rejection coverage if no validation test exercises the service path.

- [ ] **Step 2: Run focused tests to verify failure**

Run: `uv run pytest test/monitor/test_condition_validation.py test/monitor/test_condition.py test/monitor/test_monitor_target_service.py test/monitor/test_monitor_runner.py -v`

Expected: FAIL where code still accepts/evaluates `price_vs_ma`.

- [ ] **Step 3: Remove compatibility code**

Make these minimal code changes:
- `monitor/condition_validation.py`: change `elif condition_type in {"price_cross_ma", "price_vs_ma"}` to only `"price_cross_ma"`.
- `monitor/condition.py`: delete the `elif ctype == "price_vs_ma"` branch.
- `monitor/monitor_runner.py`: remove `_build_history_for_condition` handling for `price_vs_ma`; remove it from `_resolve_current_price` daily special cases.
- `monitor/monitor_target_service.py`: remove `_format_condition_summary` branch for `price_vs_ma`.

- [ ] **Step 4: Run focused monitor tests**

Run: `uv run pytest test/monitor/test_condition_validation.py test/monitor/test_condition.py test/monitor/test_monitor_target_service.py test/monitor/test_monitor_runner.py -v`

Expected: PASS.

---

### Task 4: Documentation and Fixture Cleanup

**Files:**
- Modify: `docs/stock_monitor.md`
- Modify: any remaining active tests/fixtures found by grep.

**Interfaces:**
- Consumes: Task 3 removal decisions.
- Produces: no active user-facing documentation advertises `price_vs_ma`.

- [ ] **Step 1: Update documentation**

Delete the two `price_vs_ma` condition bullets from `docs/stock_monitor.md`. Keep the `close_cross_ma` bullet and, if helpful, add one sentence that legacy `price_vs_ma` targets are migrated to `close_cross_ma` and unsupported markets are disabled.

- [ ] **Step 2: Grep for active compatibility leftovers**

Run: `grep` tool or shell equivalent for `price_vs_ma|close_cross_ma` and inspect matches.

Expected: `price_vs_ma` remains only in issue-63 migration tests, migration helper names/comments, and historical docs under `docs/superpowers/` that are not product docs.

- [ ] **Step 3: Update remaining fixtures**

Replace any active non-migration test fixture using `price_vs_ma` with `close_cross_ma` if it asserts current supported behavior, or with rejection expectations if it asserts input validation.

---

### Task 5: Final Verification

**Files:**
- No source changes expected unless verification finds a gap.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: evidence for issue #63 acceptance criteria.

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
uv run pytest \
  test/monitor/test_condition_validation.py \
  test/monitor/test_condition.py \
  test/monitor/test_monitor_target_service.py \
  test/monitor/test_monitor_runner.py \
  test/tools/test_stock_monitor_cli.py -v
```

Expected: PASS.

- [ ] **Step 2: Run PostgreSQL migration tests**

Run: `tools/run_tests.sh test/monitor/storage/test_enum_migration.py -v`

Expected: PASS.

- [ ] **Step 3: Run active leftover scan**

Run: `rg "price_vs_ma" monitor storage tools test docs/stock_monitor.md`

Expected: only migration/rejection references remain; no active evaluator, validator acceptance, runner compatibility, or product-doc support remains.

- [ ] **Step 4: Run broader monitor suite if focused checks pass**

Run: `uv run pytest test/monitor test/tools/test_stock_monitor_cli.py -v`

Expected: PASS, except PostgreSQL-marked tests that require `tools/run_tests.sh` should be rerun through the runner if they fail only due to missing `TEST_POSTGRESQL_URL`.

---

## Self-Review

- Spec coverage: migration order, metadata preservation, last-state preservation, unsupported-target disablement, PostgreSQL/SQLite repeatability, compatibility removal, docs, and tests are each covered by a task.
- Placeholder scan: no `TBD`/`TODO`/generic test directives remain; each task has concrete target files, commands, and expected results.
- Type consistency: shared diagnostic names are defined in Task 1 before use; Task 2 is storage-local and does not require the PostgreSQL helper.
