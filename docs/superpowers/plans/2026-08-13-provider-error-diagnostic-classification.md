# Provider Error Diagnostic Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Govern `provider_error` as a daily-bar diagnostic classification so existing provider-failure diagnostics can migrate without semantic loss.

**Architecture:** Extend the Python `StrEnum` that is the single source of truth for the SQLAlchemy enum mapping and Storage migration label list. Add PostgreSQL migration coverage for a legacy row carrying the new label, then update the operator-facing enum verification inventory.

**Tech Stack:** Python 3.11+, `enum.StrEnum`, SQLAlchemy, PostgreSQL, pytest, Ruff, `uv`.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Add `provider_error` without remapping, deleting, or modifying existing diagnostic records.
- Keep all finite diagnostic classifications in `DailyBarDiagnosticClassification` and the named PostgreSQL enum.
- Preserve the existing migration rule that unknown legacy values fail preflight.
- Keep the PostgreSQL enum-label verification documentation aligned with the application enum.

---

### Task 1: Govern Provider-Error Classification

**Files:**
- Modify: `storage/domain_enums.py:23-27`
- Modify: `test/paper_trading/storage/test_repository.py:29-42`
- Modify: `test/storage/test_storage_enum_migration.py:164-207`
- Modify: `docs/paper_trading.md:731-738`

**Interfaces:**
- Consumes: `DailyBarDiagnosticClassification`, `STORAGE_ENUM_GROUPS`, and `STORAGE_ENUM_ADAPTER.apply(connection)`.
- Produces: `DailyBarDiagnosticClassification.PROVIDER_ERROR` with persisted value `"provider_error"`; a `daily_bar_diagnostic_classification` PostgreSQL enum containing that label.

- [ ] **Step 1: Write the failing Python enum contract test**

In `test/paper_trading/storage/test_repository.py`, extend the expected labels in
`test_daily_bar_diagnostic_scalar_columns_use_value_enums`:

```python
assert tuple(member.value for member in DailyBarDiagnosticClassification) == (
    "missing_market_data",
    "missing_exact_date",
    "provider_error",
    "downloaded",
    "resolved",
)
```

- [ ] **Step 2: Run the enum contract test and verify it fails**

Run: `uv run pytest test/paper_trading/storage/test_repository.py::test_daily_bar_diagnostic_scalar_columns_use_value_enums -v`

Expected: FAIL because `provider_error` is absent from the production enum.

- [ ] **Step 3: Write the failing PostgreSQL legacy-migration test**

At the start of `test_apply_converts_storage_values_and_enforces_json_contracts`
in `test/storage/test_storage_enum_migration.py`, insert a legacy row before
calling `STORAGE_ENUM_ADAPTER.apply(connection)`, then assert it survives as the
canonical label:

```python
connection.execute(
    text(
        "INSERT INTO daily_bar_diagnostics VALUES "
        "(1, 'bfq', 'provider_error', "
        "'[\"provider\": \"akshare\", \"status\": \"error\"]'::jsonb)"
    )
)

assert connection.execute(
    text("SELECT classification::text FROM daily_bar_diagnostics WHERE id = 1")
).scalar_one() == "provider_error"
```

Use the valid JSON object form in the actual SQL literal:

```python
'[{"provider": "akshare", "status": "error"}]'::jsonb
```

Also add a direct accepted insert after migration:

```python
connection.execute(
    text(
        "INSERT INTO daily_bar_diagnostics VALUES "
        "(2, 'bfq', 'provider_error', "
        "'[{\"provider\": \"akshare\", \"status\": \"error\"}]'::jsonb)"
    )
)
```

- [ ] **Step 4: Run the focused PostgreSQL migration test and verify it fails**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/storage/test_storage_enum_migration.py::test_apply_converts_storage_values_and_enforces_json_contracts -v`

Expected: FAIL during Storage migration preflight with `unknown legacy values ['provider_error']`.

- [ ] **Step 5: Add the canonical enum label**

In `storage/domain_enums.py`, add the member between `MISSING_EXACT_DATE` and
`DOWNLOADED`:

```python
class DailyBarDiagnosticClassification(StrEnum):
    MISSING_MARKET_DATA = "missing_market_data"
    MISSING_EXACT_DATE = "missing_exact_date"
    PROVIDER_ERROR = "provider_error"
    DOWNLOADED = "downloaded"
    RESOLVED = "resolved"
```

No migration-code change is needed: `STORAGE_ENUM_GROUPS` already obtains labels
from this `StrEnum` and converts legacy varchar values through an explicit cast.

- [ ] **Step 6: Update the operator verification inventory**

In `docs/paper_trading.md`, change the expected
`daily_bar_diagnostic_classification` labels to:

```sql
('daily_bar_diagnostic_classification', ARRAY['missing_market_data','missing_exact_date','provider_error','downloaded','resolved']),
```

- [ ] **Step 7: Run focused tests and verify they pass**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/paper_trading/storage/test_repository.py::test_daily_bar_diagnostic_scalar_columns_use_value_enums test/storage/test_storage_enum_migration.py::test_apply_converts_storage_values_and_enforces_json_contracts -v`

Expected: PASS. The PostgreSQL test proves pre-existing and new `provider_error`
values are accepted, while its existing unknown-label assertion remains present.

- [ ] **Step 8: Run affected regression checks**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/storage/test_storage_enum_migration.py test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_enum_migration.py -v && uv run ruff format --check storage/domain_enums.py test/paper_trading/storage/test_repository.py test/storage/test_storage_enum_migration.py && uv run ruff check storage/domain_enums.py test/paper_trading/storage/test_repository.py test/storage/test_storage_enum_migration.py`

Expected: all selected tests and Ruff checks exit `0`.

- [ ] **Step 9: Commit the contract change**

```bash
git add storage/domain_enums.py test/paper_trading/storage/test_repository.py test/storage/test_storage_enum_migration.py docs/paper_trading.md
```

### Task 2: Run the Paused Production Migration and Matching Repair

**Files:**
- No repository files changed.

**Interfaces:**
- Consumes: `uv run tools/migrate_enums.py --dry-run --json`, `uv run tools/migrate_enums.py --json`, the stopped business writers, and the verified backup at `backups/quant_business_20260813_171152.sql.gz`.
- Produces: a migrated `daily_bar_diagnostics` table with `market`, a complete Paper Trading enum schema, and a recorded matching run for `2026-08-07`.

- [ ] **Step 1: Confirm backup and maintenance state**

Run:

```bash
gzip -t backups/quant_business_20260813_171152.sql.gz
```

Expected: gzip exits `0`; only the `db` service is running before live migration.

- [ ] **Step 2: Run and inspect the unified dry-run**

Run: `uv run tools/migrate_enums.py --dry-run --json`

Expected: exit `0` and JSON reports all domains ready. Do not run the live command
if the dry-run fails.

- [ ] **Step 3: Apply the unified migration**

Run: `uv run tools/migrate_enums.py --json`

Expected: exit `0` and JSON reports the Paper Trading and Storage domains applied
or already ready.

- [ ] **Step 4: Independently verify required live schema facts**

Run:

```bash
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U quant -d quant -c "SELECT enum_range(NULL::daily_bar_diagnostic_classification);"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U quant -d quant -c "SELECT column_name, udt_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'daily_bar_diagnostics' AND column_name IN ('market', 'classification') ORDER BY column_name;"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U quant -d quant -c "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname IN ('ix_paper_orders_validity_status', 'ix_paper_orders_market', 'ix_daily_bar_diagnostics_market') ORDER BY indexname;"
```

Expected: classification labels include `provider_error`; diagnostics has
`market` with `paper_market` and `classification` with
`daily_bar_diagnostic_classification`; all three indexes are returned.

- [ ] **Step 5: Restart only the Paper Trading API**

Run: `docker compose up -d paper-trading`

Expected: the `paper-trading` service is running before a matching request.

- [ ] **Step 6: Rerun matching for the affected account and date**

Run:

```bash
set -a
source .env
set +a
export PAPER_TRADING_API_BASE_URL="${PAPER_TRADING_API_BASE_URL:-http://localhost:8000}"
uv run tools/paper_trading_cli.py matching run --trade-date 2026-08-07 --account-id 6
```

Expected: the API returns a matching-run record instead of HTTP `500`.

- [ ] **Step 7: Verify matching and diagnostic outcomes**

Run:

```bash
set -a
source .env
set +a
export PAPER_TRADING_API_BASE_URL="${PAPER_TRADING_API_BASE_URL:-http://localhost:8000}"
uv run tools/paper_trading_cli.py --json matching list
uv run tools/paper_trading_cli.py --json order get --order-id 41
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U quant -d quant -c "SELECT business_date, market, stock_id, classification, resolved FROM daily_bar_diagnostics WHERE business_date = '2026-08-07' AND stock_id = '518880';"
```

Expected: a new `2026-08-07`, account `6` run has a completed status or
`completed_with_warnings`, order `41` remains consistently represented, and a
missing-bar diagnostic is persisted rather than triggering a schema error.

- [ ] **Step 8: Restore other writers after matching verification**

Run: `docker compose up -d`

Expected: services return to their configured runtime state after migration and
matching verification are complete.
