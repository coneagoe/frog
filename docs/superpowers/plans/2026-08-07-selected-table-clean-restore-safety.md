# Selected-Table Clean Restore Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent selected-table clean backup and restore operations from removing foreign keys owned by unselected tables.

**Architecture:** Add one shared PostgreSQL catalog query and guard function in `tools/db_common.sh`. Both shell entrypoints invoke it before emitting or executing selected-table clean drops. Keep full-database clean behavior unchanged, and replace the stale matching-only operations documentation with the unified behavior.

**Tech Stack:** Bash, PostgreSQL system catalogs, Docker Compose, pytest, SQLAlchemy PostgreSQL integration tests.

## Global Constraints

- Run repository Python commands with `uv run`.
- Do not change full business-database clean ordering, dependencies, or enum cleanup rules.
- Do not use `DROP TABLE ... CASCADE` for a selected-table clean operation when unselected inbound foreign keys exist.
- Gated PostgreSQL tests must skip when `TEST_POSTGRESQL_URL` is unset.
- Preserve shared enum types and duplicate-safe enum creation in selected-table dumps.

---

### Task 1: Specify and Verify the Script Guard

**Files:**
- Modify: `test/tools/test_db_scripts.py:23-170`
- Modify: `tools/db_common.sh:70-101`
- Modify: `tools/db_export.sh:128-137`
- Modify: `tools/db_import.sh:99-120`

**Interfaces:**
- Consumes: `TABLE_NAME`, `CLEAN`, `SCHEMA`, `SERVICE`, `DB_NAME`, `DB_USER` from each entrypoint.
- Produces: `reject_selected_table_clean_with_inbound_foreign_keys`, a shell function that exits nonzero before selected-table clean SQL is emitted or run when PostgreSQL reports inbound foreign keys from another table.

- [ ] **Step 1: Write the failing script tests**

Extend the fake Docker wrapper so a `psql -c` call with the new inbound-foreign-key catalog query returns a row for `paper_orders`. Add one export test and one import test:

```python
def test_clean_paper_orders_export_rejects_unselected_inbound_foreign_key(tmp_path: Path):
    result = _run_script_result(
        "db_export.sh",
        ["--no-gzip", "--clean", "--table", "paper_orders", "--out", str(tmp_path / "orders.sql")],
        tmp_path,
        inbound_foreign_key="paper_trades.paper_trades_order_id_fkey",
    )

    assert result.returncode != 0
    assert "unselected inbound foreign key" in result.stderr
    assert "DROP TABLE" not in (tmp_path / "orders.sql").read_text(encoding="utf-8")


def test_clean_paper_orders_import_rejects_unselected_inbound_foreign_key(tmp_path: Path):
    input_file = tmp_path / "orders.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    result = _run_script_result(
        "db_import.sh",
        ["--clean", "--table", "paper_orders", "--in", str(input_file)],
        tmp_path,
        inbound_foreign_key="paper_trades.paper_trades_order_id_fkey",
    )

    assert result.returncode != 0
    assert "unselected inbound foreign key" in result.stderr
    assert "DROP TABLE" not in (tmp_path / "commands.log").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest test/tools/test_db_scripts.py -k inbound_foreign_key -v`

Expected: FAIL because neither script queries or rejects unselected inbound foreign keys.

- [ ] **Step 3: Add the shared catalog guard**

In `tools/db_common.sh`, add a function accepting the selected table name, schema, and a caller-provided query executor. Query `pg_constraint`, `pg_class`, and `pg_namespace` for `contype = 'f'` constraints where `confrelid` is the selected table and `conrelid` is not it. When any row exists, print the selected table and foreign-key owner/name to stderr, explain that the command cannot safely clean it, and return nonzero.

The query must use psql variables for the schema and selected table, rather than interpolating them into SQL.

- [ ] **Step 4: Invoke the guard before selected-table clean work**

In both `db_export.sh` and `db_import.sh`, invoke the guard only when `CLEAN=1` and `TABLE_NAME` is nonempty. Invoke it before `db_export.sh` writes manual drop SQL and before `db_import.sh` calls `run_drop_docker`. Preserve all current full-clean branches exactly.

- [ ] **Step 5: Run the script tests to verify they pass**

Run: `uv run pytest test/tools/test_db_scripts.py -v`

Expected: PASS, including the two new rejection tests and all existing enum/full-clean tests.

- [ ] **Step 6: Commit the script guard**

```bash
git add tools/db_common.sh tools/db_export.sh tools/db_import.sh test/tools/test_db_scripts.py
git commit -m "Prevent unsafe selected table clean restores"
```

### Task 2: Prove PostgreSQL Foreign Keys Remain Intact

**Files:**
- Create: `test/tools/test_db_scripts_postgresql.py`

**Interfaces:**
- Consumes: `TEST_POSTGRESQL_URL` and the `db_export.sh`/`db_import.sh` command interfaces from Task 1.
- Produces: integration tests that establish a disposable schema, construct the Paper Order inbound-FK scenario, and verify both selected-table clean paths reject it before mutation.

- [ ] **Step 1: Write the failing PostgreSQL integration tests**

Create schema-scoped tests modeled after `test/paper_trading/storage/test_enum_migration.py`. Build `paper_orders`, `paper_trades`, and `paper_trade_validity_checks`, with both dependents owning an `order_id REFERENCES paper_orders(id)` constraint. Execute the scripts against a Docker database only when the test URL is available.

Each test must assert:

```python
assert result.returncode != 0
assert "unselected inbound foreign key" in result.stderr
assert foreign_key_exists(connection, schema, "paper_trades", "paper_trades_order_id_fkey")
assert foreign_key_exists(connection, schema, "paper_trade_validity_checks", "paper_trade_validity_checks_order_id_fkey")
assert table_exists(connection, schema, "paper_orders")
```

- [ ] **Step 2: Run the integration tests to verify current behavior fails**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/tools/test_db_scripts_postgresql.py -v`

Expected before Task 1 implementation: FAIL because `DROP TABLE ... CASCADE` removes the dependent foreign keys. If the configured URL is unavailable, record the skip/failure and do not treat it as coverage.

- [ ] **Step 3: Make the Docker execution schema-aware**

Pass `--schema <temporary-schema>` to each script and ensure the subprocess uses the local Compose `db` service. Use a unique schema fixture with `CREATE SCHEMA`, set `search_path` only inside test database queries, and finish with `DROP SCHEMA ... CASCADE` in fixture cleanup.

- [ ] **Step 4: Run the integration tests after the script guard**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/tools/test_db_scripts_postgresql.py -v`

Expected: PASS with both foreign-key constraints and `paper_orders` still present. If no PostgreSQL URL is available, tests must report skipped with the explicit availability reason.

- [ ] **Step 5: Commit PostgreSQL coverage**

```bash
git add test/tools/test_db_scripts_postgresql.py
git commit -m "Test selected table restore foreign keys"
```

### Task 3: Consolidate Backup and Restore Documentation

**Files:**
- Modify: `docs/paper_trading.md:548-628`

**Interfaces:**
- Consumes: final script semantics from Task 1.
- Produces: one authoritative Paper Trading backup/restore description aligned with the enum catalog and clean guard.

- [ ] **Step 1: Replace the obsolete matching-only section**

Remove the `Backup restore ordering` paragraph that says only
`paper_matching_runs` is enum-aware. Retain the existing limitations around
non-atomic clean import and enum-label forward compatibility.

- [ ] **Step 2: Add the implemented selected-table clean limitation**

Place the canonical behavior beside the governed enum list:

```markdown
Selected-table clean export and import refuse to run when an unselected table
has a foreign key referencing the selected table. This prevents a restore from
silently dropping a constraint that the selected-table dump cannot recreate.
Use a full business-database clean restore when the required tables are managed
together, or use a separately reviewed recovery procedure.
```

- [ ] **Step 3: Verify the final documentation has one model**

Run: `rg -n "enum-aware for `paper_matching_runs`|only.*paper_matching_runs|Backup restore ordering" docs/paper_trading.md`

Expected: no output. Manually inspect the unified-enum section to confirm it lists all thirteen types and describes duplicate-safe selected-table type creation.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/paper_trading.md
git commit -m "Document selected table restore safeguards"
```

### Task 4: Run the Focused Verification Suite

**Files:**
- Verify: `tools/db_common.sh`
- Verify: `tools/db_export.sh`
- Verify: `tools/db_import.sh`
- Verify: `test/tools/test_db_scripts.py`
- Verify: `test/tools/test_db_scripts_postgresql.py`
- Verify: `docs/paper_trading.md`

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: fresh evidence that portable script behavior, PostgreSQL behavior when configured, and shell quality gates are clean.

- [ ] **Step 1: Run portable script coverage**

Run: `uv run pytest test/tools/test_db_scripts.py -v`

Expected: PASS.

- [ ] **Step 2: Run PostgreSQL integration coverage**

Run: `TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/tools/test_db_scripts_postgresql.py -v`

Expected: PASS against the local database service, proving constraints remain. If `TEST_POSTGRESQL_URL` is intentionally unset, run without the fallback and report the explicit skips instead.

- [ ] **Step 3: Run formatting and linting for changed Python tests**

Run: `uv run ruff format --check test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py && uv run ruff check test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py`

Expected: PASS with no formatting or lint errors.

- [ ] **Step 4: Inspect the final diff and status**

Run: `git diff --check && git diff -- docs/paper_trading.md tools/db_common.sh tools/db_export.sh tools/db_import.sh test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py && git status --short`

Expected: no whitespace errors, only intentional changes, and no modifications to unrelated `data/` files.
