# Partial Paper Schema Key Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow enum governance to migrate and roll back reduced `paper_positions` and `daily_bar_diagnostics` schemas without attempting unavailable market-qualified key operations, while preserving complete-schema key enforcement and rollback safety.

**Architecture:** Keep market-qualified-key ownership in the existing Paper Trading enum adapter. Add a narrow catalog predicate that determines whether each table has all columns required by its market-qualified key, and apply that predicate uniformly to upgrade, verification, collision detection, and legacy-key restoration. Cover the behavior through both the direct Paper Trading migration wrapper and the unified `migrate_enums` orchestration seam.

**Tech Stack:** Python 3.11+, SQLAlchemy Core, PostgreSQL catalog queries, pytest, Ruff, uv.

## Global Constraints

- Use `uv run` for all Python commands in this repository.
- Use `tools/run_tests.sh` for PostgreSQL-dependent tests so `test_db` and `TEST_POSTGRESQL_URL` are available.
- Do not change Paper Trading API, CLI, repository, matching, valuation, or market-data behavior.
- Do not create missing business-key columns or synthesize market-qualified constraints for reduced schemas.
- Complete `paper_positions` schemas retain `(account_id, market, symbol)` identity.
- Complete `daily_bar_diagnostics` schemas retain `(business_date, market, stock_id, adjust)` identity.
- Preserve rollback rejection when complete schemas contain cross-market rows that collide under the legacy marketless key.
- Persisted `paper_market` labels remain exactly `a_share`, `hk_connect`, and `etf`.
- Do not commit unless the user explicitly requests it.

---

## File Structure

- `paper_trading/storage/enum_migration.py`: Owns `paper_market` conversion and the conditional market-qualified-key lifecycle. Add one small helper for required-column availability and reuse it at each lifecycle stage.
- `test/paper_trading/storage/test_enum_migration.py`: Direct adapter and compatibility-wrapper PostgreSQL regression coverage for reduced schemas, full-schema safety, and preconverted enum labels.
- `test/storage/test_enum_governance.py`: Unified `migrate_enums` PostgreSQL integration coverage for reduced schemas alongside Monitor and Storage adapters.

### Task 1: Guard Paper Adapter Key Operations By Cataloged Columns

**Files:**
- Modify: `paper_trading/storage/enum_migration.py:859-965`
- Test: `test/paper_trading/storage/test_enum_migration.py`

**Interfaces:**
- Consumes: PostgreSQL catalog access through `_column_facts(connection, PaperTradingEnumColumn(...))` and existing `_constraint_columns` helpers.
- Produces: An internal `bool` predicate used by `_upgrade_market_qualified_keys`, `_verify_market_qualified_keys`, `_reject_legacy_key_collisions`, and `_restore_legacy_market_qualified_keys`.

- [ ] **Step 1: Write failing direct migration tests for reduced schemas**

Add a helper that drops the business-key columns after the legacy fixture is created, while retaining enum-governed columns:

```python
def _drop_reduced_schema_key_columns(connection: Connection) -> None:
    connection.execute(text("ALTER TABLE paper_positions DROP CONSTRAINT uq_paper_positions_account_symbol"))
    connection.execute(text("ALTER TABLE paper_positions DROP COLUMN account_id"))
    connection.execute(text("ALTER TABLE paper_positions DROP COLUMN symbol"))
    connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP CONSTRAINT uq_daily_bar_diagnostics_business_key"))
    connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP COLUMN business_date"))
    connection.execute(text("ALTER TABLE daily_bar_diagnostics DROP COLUMN stock_id"))
```

Add a direct migration test that applies, verifies, and rolls back the adapter:

```python
def test_reduced_schemas_skip_market_qualified_keys_during_apply_verify_and_rollback(postgres_schema):
    engine, schema = postgres_schema
    with _connection(engine, schema) as connection:
        _drop_reduced_schema_key_columns(connection)

        assert migrate_paper_trading_enums(connection).converted is True
        assert _column_type(connection, "paper_positions", "market") == "paper_market"
        assert _column_type(connection, "daily_bar_diagnostics", "market") == "paper_market"

        assert migrate_paper_trading_enums(connection, rollback=True).rolled_back is True
        assert _column_type(connection, "paper_positions", "market") == "character varying(20)"
        assert _column_type(connection, "daily_bar_diagnostics", "market") is None
```

Assert neither market-qualified constraint exists after apply, and ensure the diagnostic `market` column is removed after rollback as normal.

- [ ] **Step 2: Run the new direct migration test to verify it fails**

Run:

```bash
tools/run_tests.sh test/paper_trading/storage/test_enum_migration.py::test_reduced_schemas_skip_market_qualified_keys_during_apply_verify_and_rollback -v
```

Expected: FAIL during apply, verification, collision preflight, or rollback because the adapter executes key SQL against an absent business-key column.

- [ ] **Step 3: Define key requirements and the complete-key predicate**

Near the key lifecycle helpers, add immutable requirements for each key and a helper that checks each named column through the existing catalog query:

```python
_MARKET_QUALIFIED_KEY_COLUMNS = {
    "paper_positions": ("account_id", "market", "symbol"),
    "daily_bar_diagnostics": ("business_date", "market", "stock_id", "adjust"),
}


def _has_market_qualified_key_columns(connection: Connection, table_name: str) -> bool:
    return _table_exists(connection, table_name) and all(
        _column_facts(connection, PaperTradingEnumColumn(table_name, column_name, "", None, False)) is not None
        for column_name in _MARKET_QUALIFIED_KEY_COLUMNS[table_name]
    )
```

Keep the helper private. It must not treat a present table as sufficient; every required business-key and `market` column must be cataloged.

- [ ] **Step 4: Apply the predicate symmetrically to all key lifecycle operations**

Replace table-existence conditions in every market-qualified key path with the new predicate:

```python
if _has_market_qualified_key_columns(connection, "paper_positions"):
    # existing upgrade, verify, collision, or restoration logic

if _has_market_qualified_key_columns(connection, "daily_bar_diagnostics"):
    # existing upgrade, verify, collision, or restoration logic
```

Preserve all existing SQL and constraint names inside guarded blocks:

```python
"UNIQUE (account_id, market, symbol)"
"UNIQUE (business_date, market, stock_id, adjust)"
"GROUP BY account_id, symbol"
"GROUP BY business_date, stock_id, adjust"
```

Do not change `_add_market_columns`: an existing reduced table must still receive/backfill `market` when its governed market column is absent.

- [ ] **Step 5: Run focused direct migration coverage**

Run:

```bash
tools/run_tests.sh test/paper_trading/storage/test_enum_migration.py -v
```

Expected: PASS. This retains the existing complete-schema tests that require upgraded keys and reject legacy-key collisions during rollback.

### Task 2: Cover Unified Governance And Enum Fixture Labels

**Files:**
- Modify: `test/storage/test_enum_governance.py:495-516`
- Modify: `test/paper_trading/storage/test_enum_migration.py:306-326`
- Test: `test/storage/test_enum_governance.py`
- Test: `test/paper_trading/storage/test_enum_migration.py`

**Interfaces:**
- Consumes: `migrate_enums(connection)` with the default `(paper_trading, monitor, storage)` adapters and the reduced-schema fixture helper defined in this test module.
- Produces: Regression evidence that global enum governance applies and rolls back reduced paper schemas without weakening complete-schema validation.

- [ ] **Step 1: Write a failing unified migration test with reduced paper schemas**

In `test/storage/test_enum_governance.py`, use the existing `postgres_schema` fixture. Its paper fixture already models the reduced schemas relevant to this issue: `paper_positions` retains the declared enum-governed `source` and `market` columns but has no `account_id` or `symbol`; Storage's `daily_bar_diagnostics` fixture retains `adjust`, `classification`, and `provider_outcomes` but has no diagnostic business-key columns. Add this integration test:

```python
def test_global_migration_and_rollback_support_reduced_paper_key_schemas(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))

        assert migrate_enums(connection).converted is True
        assert _column_type(connection, "paper_positions", "market") == "paper_market"
        assert _column_type(connection, "daily_bar_diagnostics", "market") == "paper_market"

        assert migrate_enums(connection, rollback=True).rolled_back is True
        assert _all_managed_enum_types(connection) == set()
```

The fixture tables must continue to satisfy each adapter's declared enum columns. `paper_positions.source` is needed by Paper Trading's `paper_position_source` group; Storage requires the diagnostic `adjust`, `classification`, and `provider_outcomes` columns. The missing fields must be only the market-qualified-key business columns.

After apply, assert that no market-qualified constraints are required on the reduced tables. After rollback, assert `daily_bar_diagnostics.market` is removed and Storage-owned enum columns have their original varchar types.

- [ ] **Step 2: Run the unified test to verify it fails before the guard**

Run:

```bash
tools/run_tests.sh test/storage/test_enum_governance.py::test_global_migration_and_rollback_support_reduced_paper_key_schemas -v
```

Expected: FAIL with an `EnumGovernanceError` caused by Paper Trading key DDL, verification, collision, or restoration against an absent column.

- [ ] **Step 3: Correct the stale preconverted market fixture**

In `test_apply_leaves_preconverted_group_columns_defaults_and_indexes_untouched`, replace the manually-created type definition:

```python
connection.execute(text("CREATE TYPE paper_market AS ENUM ('a_share', 'hk_connect', 'etf')"))
```

Do not weaken production label validation. The test fixture must represent the exact persisted enum contract accepted by `_preflight`.

- [ ] **Step 4: Run the focused unified and preconverted-fixture tests**

Run:

```bash
tools/run_tests.sh test/storage/test_enum_governance.py::test_global_migration_and_rollback_support_reduced_paper_key_schemas test/paper_trading/storage/test_enum_migration.py::test_apply_leaves_preconverted_group_columns_defaults_and_indexes_untouched -v
```

Expected: PASS. The global path applies all three adapters and rolls them back; the preconverted fixture remains unchanged because it has all three valid labels.

### Task 3: Format, Run Regression Coverage, And Inspect The Diff

**Files:**
- Modify: `paper_trading/storage/enum_migration.py`
- Modify: `test/paper_trading/storage/test_enum_migration.py`
- Modify: `test/storage/test_enum_governance.py`

**Interfaces:**
- Consumes: Completed conditional-key implementation and direct/unified PostgreSQL integration tests.
- Produces: A formatted, lint-clean, verified issue `#58` change set.

- [ ] **Step 1: Format the changed files**

Run:

```bash
uv run ruff format paper_trading/storage/enum_migration.py test/paper_trading/storage/test_enum_migration.py test/storage/test_enum_governance.py
```

Expected: Ruff exits zero and makes only mechanical formatting changes.

- [ ] **Step 2: Run lint on the changed files**

Run:

```bash
uv run ruff check paper_trading/storage/enum_migration.py test/paper_trading/storage/test_enum_migration.py test/storage/test_enum_governance.py
```

Expected: PASS with no lint findings.

- [ ] **Step 3: Run PostgreSQL regression coverage through the repository runner**

Run:

```bash
tools/run_tests.sh test/paper_trading/storage/test_enum_migration.py test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py -v
```

Expected: PASS. This covers direct adapter behavior, the unified orchestration seam, Storage ownership of diagnostic enum columns, complete-schema market-qualified constraints, and rollback collision rejection.

- [ ] **Step 4: Inspect only the intended diff**

Run:

```bash
git diff --check
git diff -- paper_trading/storage/enum_migration.py test/paper_trading/storage/test_enum_migration.py test/storage/test_enum_governance.py
```

Expected: no whitespace errors; the diff contains only conditional market-qualified-key behavior, fixture correction, and focused tests. Leave unrelated untracked files unchanged.
