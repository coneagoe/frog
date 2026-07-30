# Paper Trading HK Connect Schema Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade legacy paper-trading databases with all HK Connect columns required by the current ORM, preventing account-list and HK Connect API failures.

**Architecture:** Extend the existing `StorageDb.ensure_paper_trading_schema()` bootstrap migration rather than adding a migration framework. The migration inspects each existing table before adding only absent HK Connect columns, using ORM-compatible PostgreSQL DDL defaults for legacy rows.

**Tech Stack:** Python 3.11+, SQLAlchemy, PostgreSQL/TimescaleDB, pytest, uv.

## Global Constraints

- Use `uv run` for every Python and pytest command.
- Preserve existing paper-trading data; only add missing schema elements.
- Keep the migration idempotent through SQLAlchemy schema inspection.
- Do not alter HK Connect business rules, frontend behavior, or unrelated table structures.
- Do not commit unless explicitly requested.

---

## File Structure

- Modify `storage/storage_db.py:2294-2422`: add the missing HK Connect schema upgrades to `StorageDb.ensure_paper_trading_schema()`.
- Modify `test/storage/test_storage_db.py`: add an integration-style regression test that initializes a legacy paper-trading schema, runs the upgrade, and verifies every new HK Connect column/table requirement.

### Task 1: Add a Legacy-Schema Regression Test

**Files:**
- Modify: `test/storage/test_storage_db.py`
- Reference: `storage/model/paper_trading.py:31-244`
- Reference: `storage/storage_db.py:2294-2422`

**Interfaces:**
- Consumes: `StorageDb.ensure_paper_trading_schema() -> None`.
- Produces: regression coverage that fails until legacy HK Connect columns are upgraded.

- [ ] **Step 1: Locate the existing StorageDb test fixture and import pattern**

Read `test/storage/test_storage_db.py` and use its existing temporary database/engine fixture. Import `inspect` from `sqlalchemy`, `PaperAccount`, and the paper-trading table-name constants that make assertions explicit.

- [ ] **Step 2: Write the failing regression test**

Add a test that starts from an existing legacy paper-trading schema: create the paper tables without the HK Connect fields, instantiate `StorageDb` with the test configuration, and call `ensure_paper_trading_schema()`.

```python
def test_ensure_paper_trading_schema_upgrades_hk_connect_columns(storage):
    storage.ensure_paper_trading_schema()

    inspector = inspect(storage.engine)
    account_columns = {column["name"] for column in inspector.get_columns("paper_accounts")}
    assert {
        "hk_commission_rate",
        "hk_min_commission",
        "hk_stamp_duty_rate",
        "hk_trading_fee_rate",
        "hk_sfc_levy_rate",
        "hk_afrc_levy_rate",
        "hk_settlement_fee_rate",
    } <= account_columns

    for table_name in (
        "paper_positions",
        "paper_orders",
        "paper_trades",
        "paper_trade_validity_checks",
    ):
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert "market" in columns

    snapshot_columns = {column["name"] for column in inspector.get_columns("paper_account_snapshots")}
    assert "pending_settlement" in snapshot_columns
```

Add an ORM query assertion after inserting a minimal legacy `paper_accounts` row, so the test exercises the same `PaperAccount` column selection that caused the production 500:

```python
with Session(storage.engine) as session:
    assert session.query(PaperAccount).order_by(PaperAccount.id).one().hk_commission_rate is None
```

- [ ] **Step 3: Run the focused test to verify RED**

Run:

```bash
uv run pytest test/storage/test_storage_db.py::test_ensure_paper_trading_schema_upgrades_hk_connect_columns -q
```

Expected: failure because `hk_commission_rate` and the other HK Connect fields are absent after the existing upgrade method returns.

### Task 2: Implement the Idempotent HK Connect Upgrade

**Files:**
- Modify: `storage/storage_db.py:2333-2422`
- Test: `test/storage/test_storage_db.py::test_ensure_paper_trading_schema_upgrades_hk_connect_columns`

**Interfaces:**
- Consumes: table names and SQLAlchemy `inspect(self.engine).get_columns(table_name)`.
- Produces: `ensure_paper_trading_schema()` adds every missing HK Connect column while leaving existing columns and rows untouched.

- [ ] **Step 1: Add missing account fee columns**

Inside the existing `paper_accounts` inspection block, add these DDL entries to the schema-upgrade column map:

```python
hk_account_fee_columns = {
    "hk_commission_rate": "NUMERIC(20, 8)",
    "hk_min_commission": "NUMERIC(20, 4)",
    "hk_stamp_duty_rate": "NUMERIC(20, 8)",
    "hk_trading_fee_rate": "NUMERIC(20, 8)",
    "hk_sfc_levy_rate": "NUMERIC(20, 8)",
    "hk_afrc_levy_rate": "NUMERIC(20, 8)",
    "hk_settlement_fee_rate": "NUMERIC(20, 8)",
}
```

For each missing column, execute:

```python
conn.execute(text(f"ALTER TABLE {tb_name_paper_accounts} ADD COLUMN {column_name} {ddl}"))
```

- [ ] **Step 2: Add market columns to all market-aware legacy tables**

After the relevant table existence checks, iterate over the four table names and add a missing market marker with a backward-compatible default:

```python
market_ddl = "VARCHAR(20) NOT NULL DEFAULT 'a_share'"
for tb_name in (
    tb_name_paper_positions,
    tb_name_paper_orders,
    tb_name_paper_trades,
    tb_name_paper_trade_validity_checks,
):
    if inspect(self.engine).has_table(tb_name):
        columns = {column["name"] for column in inspect(self.engine).get_columns(tb_name)}
        if "market" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tb_name} ADD COLUMN market {market_ddl}"))
```

- [ ] **Step 3: Add snapshot pending-settlement column**

Extend the existing snapshot upgrade map with:

```python
"pending_settlement": "NUMERIC(20, 4) NOT NULL DEFAULT 0",
```

This retains legacy snapshot accounting values while establishing the required non-null ORM field.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run:

```bash
uv run pytest test/storage/test_storage_db.py::test_ensure_paper_trading_schema_upgrades_hk_connect_columns -q
```

Expected: PASS. The ORM account query succeeds and every required HK Connect column is present.

- [ ] **Step 5: Run focused paper-trading regression tests**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/api/test_accounts_api.py -q
```

Expected: PASS, confirming repository and account API compatibility with the expanded schema.

### Task 3: Apply and Verify the Running Service Upgrade

**Files:**
- Runtime: Docker Compose `paper-trading` service and configured PostgreSQL database.

**Interfaces:**
- Consumes: startup invocation of `get_storage()` and `ensure_paper_trading_schema()`.
- Produces: upgraded live database and a non-500 authenticated account-list endpoint.

- [ ] **Step 1: Inspect current live columns before restart**

Run:

```bash
docker compose exec -T db psql -U quant -d quant -c "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'paper_accounts' ORDER BY ordinal_position;"
```

Expected: live schema lacks `hk_commission_rate` before service restart.

- [ ] **Step 2: Restart the paper-trading service**

Run:

```bash
docker compose restart paper-trading
```

Expected: service starts successfully and its storage bootstrap upgrades the live legacy schema.

- [ ] **Step 3: Verify schema and API recovery**

Load the repository `.env`, then run the supported CLI:

```bash
set -a; source .env; set +a; export PAPER_TRADING_API_BASE_URL="${PAPER_TRADING_API_BASE_URL:-http://localhost:8000}"; uv run tools/paper_trading_cli.py account list
```

Expected: account list is returned successfully or is empty; it must not return `Internal Server Error`.

Confirm the live table now has all HK account fee columns:

```bash
docker compose exec -T db psql -U quant -d quant -c "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'paper_accounts' AND column_name LIKE 'hk_%' ORDER BY column_name;"
```

Expected: seven rows, one for each `hk_*` fee field.

- [ ] **Step 4: Inspect service logs for missing-column regressions**

Run:

```bash
docker compose logs --tail=100 paper-trading
```

Expected: no `UndefinedColumn` or `Internal Server Error` after the verification request.
