# Monitor and Forecast SSF Enum Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Constrain Monitor and Forecast SSF finite persisted values with canonical Python enums and PostgreSQL enums, and require valid typed monitor conditions at every write boundary.

**Architecture:** Add Monitor domain enums and a central condition validator, then map model columns through SQLAlchemy native enums and call the validator from service and direct storage writers. A dedicated operator migration converts the two existing tables in PostgreSQL, validates legacy conditions, installs the minimum stable JSON check, and supports dry-run, verification, idempotent reruns, and rollback without changing the Paper Trading migration.

**Tech Stack:** Python 3.11+, `StrEnum`, SQLAlchemy 2, PostgreSQL enums and JSONB checks, SQLite, pytest, Ruff, mypy.

## Global Constraints

- Run repository Python commands with `uv run`; do not use bare `python` or `python3`.
- Preserve canonical string labels in API, CLI, workflow, storage, and database results.
- Do not alter PostgreSQL enum labels at application startup; only the operator migration performs DDL.
- Reject legacy untyped monitor condition documents; do not translate or coerce them.
- Keep type-dependent condition direction and field validation in Python; PostgreSQL enforces only the minimum stable JSON object/discriminator contract.
- Preserve every existing Forecast SSF state, including `delisted_or_unlisted`.
- PostgreSQL integration tests must use an isolated temporary schema and skip explicitly when `TEST_POSTGRESQL_URL` is unavailable.
- Do not change DAG schedules, retries, task boundaries, or SLA.

---

## File Structure

- Create: `monitor/domain_enums.py` — canonical `StrEnum` values for Monitor market, frequency, reset mode, and Forecast SSF candidate state.
- Create: `monitor/condition_validation.py` — reusable validation of the discriminated monitor condition JSON contract.
- Modify: `monitor/monitor_target_service.py` — delegate its condition rules to the central validator while retaining service response semantics.
- Modify: `storage/model/stock_monitor_target.py` — map Monitor finite columns to named SQLAlchemy native enum types.
- Modify: `storage/model/forecast_ssf_candidate.py` — map candidate market and lifecycle state to named SQLAlchemy native enum types.
- Modify: `storage/storage_db.py` — validate direct Monitor writes and Forecast SSF finite values before transactions.
- Create: `monitor/storage/enum_migration.py` — dedicated Monitor/Forecast SSF PostgreSQL enum migration.
- Create: `tools/migrate_monitor_enums.py` — operator command for migration dry-run, apply, and rollback.
- Create: `test/monitor/test_condition_validation.py` — isolated validator tests.
- Modify: `test/monitor/test_monitor_target_service.py` — service-level central-validation regression coverage.
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py` — SQLite direct-storage and enum mapping coverage using typed conditions.
- Create: `test/monitor/storage/test_enum_migration.py` — PostgreSQL temporary-schema migration and direct-SQL enforcement coverage.
- Create: `test/tools/test_migrate_monitor_enums.py` — operator command behavior coverage.

### Task 1: Define Canonical Values And Validate Conditions

**Files:**
- Create: `monitor/domain_enums.py`
- Create: `monitor/condition_validation.py`
- Create: `test/monitor/test_condition_validation.py`

**Interfaces:**
- Produces: `MonitorMarket`, `MonitorFrequency`, `MonitorResetMode`, and `ForecastSSFCandidateState`, all `StrEnum` subclasses whose `.value` labels match persisted strings.
- Produces: `validate_condition(condition: Mapping[str, Any]) -> dict[str, Any]`, returning a shallow normalized copy or raising `ValueError` with a field-specific message.
- Consumes: no storage or service code; this module remains portable and is the single condition-schema authority.

- [ ] **Step 1: Write failing enum and validator tests**

```python
from monitor.condition_validation import validate_condition
from monitor.domain_enums import ForecastSSFCandidateState, MonitorFrequency, MonitorMarket, MonitorResetMode


def test_enum_values_match_persisted_contract():
    assert [value.value for value in MonitorMarket] == ["A", "HK", "ETF"]
    assert [value.value for value in MonitorFrequency] == ["daily", "intraday"]
    assert [value.value for value in MonitorResetMode] == ["auto", "manual"]
    assert "delisted_or_unlisted" in {value.value for value in ForecastSSFCandidateState}


def test_validate_condition_accepts_typed_workflow_price_vs_ma_condition():
    condition = {"type": "price_vs_ma", "direction": "above", "period": 20, "workflow": "forecast_ssf_ma20"}

    assert validate_condition(condition) == condition


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ({"type": "unknown"}, "condition.type"),
        ({"type": "ma_cross", "direction": "above", "fast": 5, "slow": 20}, "condition.direction"),
        ({"type": "price_threshold", "direction": "above"}, "condition.value"),
        ({"type": "price_vs_ma", "direction": "above", "period": 0}, "condition.period"),
        ({"workflow": "forecast_ssf_ma20"}, "condition.type"),
    ],
)
def test_validate_condition_rejects_invalid_contract(condition, message):
    with pytest.raises(ValueError, match=message):
        validate_condition(condition)
```

- [ ] **Step 2: Run the validator tests to verify RED**

Run: `uv run pytest test/monitor/test_condition_validation.py -v`

Expected: FAIL during collection because `monitor.condition_validation` and `monitor.domain_enums` do not exist.

- [ ] **Step 3: Add the canonical `StrEnum` definitions**

```python
from enum import StrEnum


class MonitorMarket(StrEnum):
    A = "A"
    HK = "HK"
    ETF = "ETF"


class ForecastSSFCandidateState(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    DEFERRED = "deferred"
    PAUSED = "paused"
    BLACKROOM = "blackroom"
    DELISTED_OR_UNLISTED = "delisted_or_unlisted"
```

Define `MonitorFrequency` and `MonitorResetMode` in the same module using their specification labels.

- [ ] **Step 4: Implement the minimal condition validator**

```python
def validate_condition(condition: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(condition, Mapping):
        raise ValueError("condition must be a JSON object")
    normalized = dict(condition)
    condition_type = normalized.get("type")
    if condition_type == "price_threshold":
        _validate_direction(normalized, {"above", "below"})
        _required_number(normalized, "value")
    elif condition_type == "ma_cross":
        _validate_direction(normalized, {"golden", "death"})
        fast = _required_positive_int(normalized, "fast")
        slow = _required_positive_int(normalized, "slow")
        if fast >= slow:
            raise ValueError("condition.fast must be less than condition.slow")
    elif condition_type == "change_pct":
        _validate_direction(normalized, {"above", "below"})
        _required_number(normalized, "value")
    elif condition_type in {"price_cross_ma", "price_vs_ma"}:
        _validate_direction(normalized, {"above", "below"})
        _required_positive_int(normalized, "period")
    elif condition_type == "rsi":
        _validate_direction(normalized, {"above", "below"})
        normalized.setdefault("period", 14)
        _required_positive_int(normalized, "period")
        value = _required_number(normalized, "value")
        if not 0 <= value <= 100:
            raise ValueError("condition.value must be between 0 and 100")
    else:
        raise ValueError(f"condition.type unsupported: {condition_type!r}")
    return normalized
```

The six explicit branches are `price_threshold`, `change_pct`, `price_cross_ma`, `price_vs_ma`, `ma_cross`, and `rsi`. Reject booleans as numbers and reject non-positive integer periods.

- [ ] **Step 5: Run the validator tests to verify GREEN**

Run: `uv run pytest test/monitor/test_condition_validation.py -v`

Expected: PASS, including untyped workflow JSON rejection.

- [ ] **Step 6: Commit the portable contract**

```bash
git add monitor/domain_enums.py monitor/condition_validation.py test/monitor/test_condition_validation.py
git commit -m "Define monitor value contracts"
```

### Task 2: Route Service And SQLite Storage Writes Through The Contract

**Files:**
- Modify: `monitor/monitor_target_service.py:74-377`
- Modify: `storage/model/stock_monitor_target.py:1-71`
- Modify: `storage/model/forecast_ssf_candidate.py:1-28`
- Modify: `storage/storage_db.py:1500-1583,2248-2329,2486-2637`
- Modify: `test/monitor/test_monitor_target_service.py:277-314`
- Modify: `test/storage/test_forecast_ssf_candidate_storage.py:52-70,388-688`

**Interfaces:**
- Consumes: `validate_condition()` and the four enums from Task 1.
- Produces: storage write methods that raise `ValueError` before database transactions for invalid Monitor conditions, markets, frequency/reset mode, candidate market, or candidate state.
- Produces: SQLAlchemy `Enum(..., native_enum=True, validate_strings=True, _create_events=False)` model columns named `monitor_market`, `monitor_frequency`, `monitor_reset_mode`, and `forecast_ssf_candidate_state`; candidate and monitor market share `monitor_market`.

- [ ] **Step 1: Write failing service and direct-storage tests**

```python
def test_add_target_rejects_untyped_workflow_condition():
    result = MonitorTargetService(storage=MagicMock()).add_target(
        stock_code="600519", market="A", condition={"workflow": "forecast_ssf_ma20"}
    )

    assert result["code"] == "VALIDATION_ERROR"
    assert "condition.type" in result["message"]


def test_direct_storage_create_rejects_invalid_condition_before_commit(tmp_path):
    db = _sqlite_storage(tmp_path)

    with pytest.raises(ValueError, match="condition.type"):
        db.create_monitor_target("600001", "A", {"workflow": "forecast_ssf_ma20"})


@pytest.mark.parametrize("field,value", [("market", "US"), ("frequency", "weekly"), ("reset_mode", "never")])
def test_direct_monitor_storage_rejects_unknown_finite_values(tmp_path, field, value):
    db = _sqlite_storage(tmp_path)
    kwargs = {field: value}

    with pytest.raises(ValueError):
        db.create_monitor_target("600001", "A", _typed_condition(), **kwargs)


def test_forecast_candidate_storage_rejects_unknown_state(tmp_path):
    db = _sqlite_storage(tmp_path)

    with pytest.raises(ValueError, match="state"):
        db.upsert_forecast_ssf_candidate("600001", "A", date(2025, 12, 31), "unknown", "reason", {}, None)
```

Use `_typed_condition()` in the storage test module to return `{"type": "price_threshold", "direction": "above", "value": 10}` and update all existing direct-storage fixtures from legacy `{ "price": ... }` shapes to valid typed shapes.

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `uv run pytest test/monitor/test_monitor_target_service.py test/storage/test_forecast_ssf_candidate_storage.py -k 'untyped_workflow or unknown_finite or unknown_state' -v`

Expected: FAIL because direct storage accepts untyped conditions and unknown finite values.

- [ ] **Step 3: Replace duplicate service condition rules with the central validator**

In `_parse_and_validate_condition()`, preserve JSON parsing and object checks, call `validate_condition(parsed)`, and wrap its `ValueError` as `TargetValidationError`. Remove `_expect_numeric`, `_expect_int`, `_validate_condition_rules`, and `_validate_direction` only after all service tests pass. Keep `_validate_market`, `_validate_frequency`, and `_validate_reset_mode`, but derive their allowed labels from the Task 1 enums rather than separate literal sets.

- [ ] **Step 4: Map finite model fields through named SQLAlchemy enums**

Add a local helper equivalent to the Paper Trading `_value_enum()` helper, using values from a `StrEnum` and `validate_strings=True`. Replace `String` mappings for Monitor `market`, `frequency`, and `reset_mode`, and Forecast SSF candidate `market` and `state`. Keep annotation and external values as `str` so responses remain unchanged.

- [ ] **Step 5: Validate all direct storage writers before opening a transaction**

At the start of `create_monitor_target()`, validate `market`, `frequency`, `reset_mode`, and `condition`. In `update_monitor_target()`, validate each changed finite field and condition before creating the session. In `upsert_workflow_monitor_target()` and `upsert_forecast_ssf_candidate_with_workflow_target()`, validate market/frequency/condition before starting their transactions. In `upsert_forecast_ssf_candidate()`, validate candidate market and state before `engine.begin()`.

Use a small private helper in `StorageDb` only if it prevents repeated enum-membership code; it must raise `ValueError` such as `market must be one of ['A', 'ETF', 'HK']` rather than exposing an SQLAlchemy error.

- [ ] **Step 6: Update all SQLite fixtures and workflow-storage calls to typed conditions**

Replace each direct test fixture like `{"price": {"above": 10}}` with the applicable canonical typed shape. Preserve workflow markers where an existing test asserts ownership. Ensure test cases intentionally exercising ownership use valid typed conditions plus the marker, so failures continue to test ownership rather than the new schema validation.

- [ ] **Step 7: Run focused service and storage tests to verify GREEN**

Run: `uv run pytest test/monitor/test_monitor_target_service.py test/storage/test_forecast_ssf_candidate_storage.py -v`

Expected: PASS. Valid workflow upserts preserve candidate transitions, including `delisted_or_unlisted`; invalid direct writes fail before persistence.

- [ ] **Step 8: Commit write-boundary enforcement**

```bash
git add monitor/monitor_target_service.py storage/model/stock_monitor_target.py storage/model/forecast_ssf_candidate.py storage/storage_db.py test/monitor/test_monitor_target_service.py test/storage/test_forecast_ssf_candidate_storage.py
git commit -m "Validate monitor persistence values"
```

### Task 3: Implement The Dedicated PostgreSQL Enum Migration

**Files:**
- Create: `monitor/storage/__init__.py`
- Create: `monitor/storage/enum_migration.py`
- Create: `test/monitor/storage/test_enum_migration.py`

**Interfaces:**
- Consumes: Task 1 enums and model table metadata from `StockMonitorTarget` and `ForecastSSFCandidate`.
- Produces: `MonitorEnumMigrationError`, `MonitorEnumColumn`, `MonitorEnumGroup`, `MonitorEnumMigrationResult`, and `migrate_monitor_enums(connection: Connection, *, dry_run: bool = False, rollback: bool = False) -> MonitorEnumMigrationResult`.
- Produces enum groups: `monitor_market` for both tables’ market columns, `monitor_frequency`, `monitor_reset_mode`, and `forecast_ssf_candidate_state`.

- [ ] **Step 1: Write failing PostgreSQL migration tests**

Model the fixture after `test/paper_trading/storage/test_enum_migration.py`: create a UUID schema, set `search_path`, create legacy `VARCHAR` Monitor and Forecast SSF tables with their defaults, and clean up using `DROP SCHEMA ... CASCADE`.

```python
def test_apply_converts_columns_and_rejects_direct_invalid_values(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        result = migrate_monitor_enums(connection)

        assert result.converted is True
        assert _column_type(connection, "stock_monitor_targets", "market") == "monitor_market"
        assert _column_type(connection, "forecast_ssf_candidates", "state") == "forecast_ssf_candidate_state"
        with pytest.raises(Exception):
            connection.execute(
                text(
                    "INSERT INTO stock_monitor_targets "
                    "(stock_code, market, condition, frequency, reset_mode) "
                    "VALUES ('600001', 'US', '{\"type\": \"price_threshold\", \"direction\": \"above\", \"value\": 10}'::jsonb, 'daily', 'auto')"
                )
            )
        with pytest.raises(Exception):
            connection.execute(
                text(
                    "INSERT INTO stock_monitor_targets "
                    "(stock_code, market, condition, frequency, reset_mode) "
                    "VALUES ('600001', 'A', '{\"type\": \"unknown\"}'::jsonb, 'daily', 'auto')"
                )
            )


def test_invalid_legacy_condition_aborts_without_ddl(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        connection.execute(
            text(
                "INSERT INTO stock_monitor_targets "
                "(stock_code, market, condition, frequency, reset_mode) "
                "VALUES ('600001', 'A', '{\"workflow\": \"forecast_ssf_ma20\"}'::jsonb, 'daily', 'auto')"
            )
        )

        with pytest.raises(MonitorEnumMigrationError, match="condition"):
            migrate_monitor_enums(connection)

        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _enum_types(connection) == set()
```

Add tests for unknown legacy enum labels, `dry_run=True` no-write behavior, idempotent second apply, and rollback restoring original `VARCHAR` types/defaults and removing the named types and check constraint.

- [ ] **Step 2: Run integration tests to verify RED**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/monitor/storage/test_enum_migration.py -v`

Expected: FAIL during collection because `monitor.storage.enum_migration` does not exist. If the PostgreSQL URL is unavailable, record the explicit skip and run the full portable suite after Task 4.

- [ ] **Step 3: Implement strict preflight and enum conversion**

Adapt the minimal reusable parts of `paper_trading.storage.enum_migration` into the new module; do not import private implementation functions from it. Preflight must:

```python
MONITOR_ENUM_GROUPS = (
    MonitorEnumGroup("monitor_market", _labels(MonitorMarket), (
        _column("stock_monitor_targets", "market", "VARCHAR(5)", "'A'"),
        _column("forecast_ssf_candidates", "market", "VARCHAR(5)", "'A'"),
    )),
    MonitorEnumGroup("monitor_frequency", _labels(MonitorFrequency), (
        _column("stock_monitor_targets", "frequency", "VARCHAR(10)", "'daily'"),
    )),
    MonitorEnumGroup("monitor_reset_mode", _labels(MonitorResetMode), (
        _column("stock_monitor_targets", "reset_mode", "VARCHAR(10)", "'auto'"),
    )),
    MonitorEnumGroup("forecast_ssf_candidate_state", _labels(ForecastSSFCandidateState), (
        _column("forecast_ssf_candidates", "state", "VARCHAR(32)"),
    )),
)
```

Before any `CREATE TYPE` or `ALTER TABLE`, inspect distinct values and reject unknown/null values inconsistent with column nullability. Validate every `stock_monitor_targets.condition` using `validate_condition()`, converting its `ValueError` to `MonitorEnumMigrationError`. Verify expected labels, converted types, and defaults after apply. Rollback must convert types to their exact original `VARCHAR` declarations, restore defaults, drop the JSON constraint, verify no dependencies, then drop each enum type.

- [ ] **Step 4: Add the minimal stable PostgreSQL JSON check**

Define a stable named check, for example `ck_stock_monitor_targets_condition_type`, that requires `jsonb_typeof(condition) = 'object'` and `condition->>'type' IN ('price_threshold', 'price_cross_ma', 'price_vs_ma', 'ma_cross', 'change_pct', 'rsi')`. Add it after successful legacy-condition preflight. On rerun, inspect the named constraint and reject a conflicting definition; on rollback, remove only this named constraint.

- [ ] **Step 5: Run PostgreSQL migration tests to verify GREEN**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/monitor/storage/test_enum_migration.py -v`

Expected: PASS against the available database. The test proves unknown labels and unsupported JSON types fail at the database boundary, while type-dependent invalid conditions are rejected by Python preflight/write validation.

- [ ] **Step 6: Commit PostgreSQL migration coverage**

```bash
git add monitor/storage/__init__.py monitor/storage/enum_migration.py test/monitor/storage/test_enum_migration.py
git commit -m "Migrate monitor values to enums"
```

### Task 4: Provide The Operator Command And Run Focused Verification

**Files:**
- Create: `tools/migrate_monitor_enums.py`
- Create: `test/tools/test_migrate_monitor_enums.py`
- Verify: files changed in Tasks 1-3

**Interfaces:**
- Consumes: `parse_config()`, `get_storage().engine.begin()`, and `migrate_monitor_enums()`.
- Produces: `main(argv: list[str] | None = None) -> int` supporting `--dry-run`, `--rollback`, and `--json`, with stable summary output and nonzero failure behavior.

- [ ] **Step 1: Write failing command tests**

Copy the fake transaction and storage pattern from `test/tools/test_migrate_paper_trading_enums.py` with Monitor result types.

```python
def test_main_forwards_dry_run_and_emits_stable_json(monkeypatch, capsys):
    transaction = FakeTransaction()
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(transaction))
    monkeypatch.setattr(command, "migrate_monitor_enums", fake_migration)

    assert command.main(["--dry-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_main_returns_one_and_rolls_back_transaction_on_migration_error(monkeypatch, capsys):
    monkeypatch.setattr(command, "migrate_monitor_enums", raising_migration)

    assert command.main(["--rollback"]) == 1
    assert "error: migration failure" in capsys.readouterr().err
```

Also test `--help` from `/tmp` and rejection of abbreviated flags by `allow_abbrev=False`.

- [ ] **Step 2: Run command tests to verify RED**

Run: `uv run pytest test/tools/test_migrate_monitor_enums.py -v`

Expected: FAIL during collection because `tools.migrate_monitor_enums` does not exist.

- [ ] **Step 3: Implement the explicit operator command**

Follow the existing Paper Trading command structure exactly: add project root to `sys.path`, call `parse_config()`, open `get_storage().engine.begin()`, invoke `migrate_monitor_enums(connection, dry_run=args.dry_run, rollback=args.rollback)`, print either `asdict(result)` JSON or the stable group summary, and return `1` after writing `error: ...` to stderr on failure.

- [ ] **Step 4: Run command tests to verify GREEN**

Run: `uv run pytest test/tools/test_migrate_monitor_enums.py -v`

Expected: PASS.

- [ ] **Step 5: Run the full focused evidence path**

Run: `uv run pytest test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/tools/test_migrate_monitor_enums.py -v`

Expected: PASS with typed Forecast SSF conditions and unchanged lifecycle behavior.

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/monitor/storage/test_enum_migration.py -v`

Expected: PASS when the local PostgreSQL service is reachable; otherwise an explicit availability skip is the documented coverage gap.

Run: `uv run ruff format --check monitor/domain_enums.py monitor/condition_validation.py monitor/storage/enum_migration.py monitor/monitor_target_service.py storage/model/stock_monitor_target.py storage/model/forecast_ssf_candidate.py storage/storage_db.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/storage/test_enum_migration.py test/storage/test_forecast_ssf_candidate_storage.py test/tools/test_migrate_monitor_enums.py && uv run ruff check monitor storage test/monitor test/storage/test_forecast_ssf_candidate_storage.py test/tools/test_migrate_monitor_enums.py && uv run mypy monitor storage`

Expected: PASS with no formatting, lint, or type errors in the affected checked modules.

- [ ] **Step 6: Inspect final changes**

Run: `git diff --check && git status --short && git diff --stat`

Expected: no whitespace errors and only issue #37 implementation, tests, and documentation changes in this worktree.

- [ ] **Step 7: Commit command and final verification**

```bash
git add tools/migrate_monitor_enums.py test/tools/test_migrate_monitor_enums.py
git commit -m "Add monitor enum migration command"
```
