# Enum Export, Import, and Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make business database export, clean import, and unified enum rollback preserve all governed PostgreSQL enum types, JSON checks, defaults, indexes, and dependency ordering.

**Architecture:** Keep `tools/db_common.sh` as the explicit business catalog used by the Bash backup scripts. Extend the catalog for Storage-domain enums, while leaving SQLAlchemy enum adapters as the owners of migration and rollback semantics. Use portable fake-Docker script tests plus isolated PostgreSQL integration tests to prove ordering and rollback behavior without changing command interfaces or application contracts.

**Tech Stack:** Bash, PostgreSQL `pg_dump`/`psql`, SQLAlchemy, pytest, Ruff, Docker Compose.

## Global Constraints

- Run repository Python commands with `uv run`.
- Preserve the existing business-table selection, command arguments, shared-enum behavior, and full-clean ordering.
- Do not silently add, rename, remove, coerce, or truncate enum labels.
- Selected-table clean must reject unselected inbound foreign keys before destructive SQL runs.
- `pg_dump` remains responsible for table-owned indexes, foreign keys, defaults, and JSON `CHECK` constraints; do not duplicate them in manual DDL.
- Rollback must reject unmanaged enum dependencies before mutation and drop enum types only after all managed columns and other dependencies are gone.
- PostgreSQL integration tests skip with an explicit reason when `TEST_POSTGRESQL_URL` is unavailable.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLAs.

---

### Task 1: Extend the Business Enum Catalog

**Files:**
- Modify: `tools/db_common.sh:54-104`
- Modify: `test/tools/test_db_scripts.py`

**Interfaces:**
- Consumes: `BUSINESS_ENUM_TYPES`, `business_enum_is_needed`, and `business_enum_can_be_dropped` used by both database scripts.
- Produces: Storage enum names and table mappings for `blackroom_records`, `daily_bar_diagnostics`, and `ssf_change_signals`, while preserving shared-type retention rules.

- [ ] **Step 1: Add failing catalog assertions**

Add tests beside the existing Paper Trading and Monitor catalog tests:

```python
def test_full_export_includes_storage_enum_types_before_table_dump(tmp_path: Path):
    output_file = tmp_path / "storage.sql"
    _run_script("db_export.sh", ["--no-gzip", "--out", str(output_file)], tmp_path)

    dump = output_file.read_text(encoding="utf-8")
    for type_name in (
        "blackroom_market",
        "blackroom_source",
        "daily_bar_diagnostic_adjust",
        "daily_bar_diagnostic_classification",
        "ssf_change_signal_status",
    ):
        assert f'CREATE TYPE "public"."{type_name}"' in dump
        assert dump.index(f'CREATE TYPE "public"."{type_name}"') < dump.index("-- dump output")


def test_selected_storage_table_exports_only_required_storage_types(tmp_path: Path):
    output_file = tmp_path / "diagnostics.sql"
    _run_script(
        "db_export.sh",
        ["--no-gzip", "--table", "daily_bar_diagnostics", "--out", str(output_file)],
        tmp_path,
    )

    dump = output_file.read_text(encoding="utf-8")
    assert 'CREATE TYPE "public"."daily_bar_diagnostic_adjust"' in dump
    assert 'CREATE TYPE "public"."daily_bar_diagnostic_classification"' in dump
    assert 'CREATE TYPE "public"."blackroom_market"' not in dump
    assert 'CREATE TYPE "public"."ssf_change_signal_status"' not in dump


def test_selected_storage_table_clean_drops_private_types_only(tmp_path: Path):
    input_file = tmp_path / "diagnostics.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")
    _run_script(
        "db_import.sh",
        ["--clean", "--table", "daily_bar_diagnostics", "--in", str(input_file)],
        tmp_path,
    )

    drop_sql = (tmp_path / "commands.log").read_text(encoding="utf-8").split(" -c ", 1)[1]
    assert 'DROP TYPE IF EXISTS "public"."daily_bar_diagnostic_adjust"' in drop_sql
    assert 'DROP TYPE IF EXISTS "public"."daily_bar_diagnostic_classification"' in drop_sql
    assert 'DROP TYPE IF EXISTS "public"."blackroom_market"' not in drop_sql
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest test/tools/test_db_scripts.py -k "storage_enum or selected_storage" -v
```

Expected: the new tests fail because `db_common.sh` does not yet list or map the Storage enum types.

- [ ] **Step 3: Add the five Storage enum names and mappings**

Append these names to `BUSINESS_ENUM_TYPES`:

```bash
  blackroom_market
  blackroom_source
  daily_bar_diagnostic_adjust
  daily_bar_diagnostic_classification
  ssf_change_signal_status
```

Extend the `business_enum_is_needed` case with:

```bash
blackroom_market:blackroom_records|blackroom_source:blackroom_records|daily_bar_diagnostic_adjust:daily_bar_diagnostics|daily_bar_diagnostic_classification:daily_bar_diagnostics|ssf_change_signal_status:ssf_change_signals)
```

Leave these Storage types drop-safe under the existing default branch. Do not mark any of them as shared because each is used by one governed table.

- [ ] **Step 4: Run all portable database script tests**

Run:

```bash
uv run pytest test/tools/test_db_scripts.py test/tools/test_db_common.py -v
```

Expected: PASS, including existing Paper Trading, Monitor, Forecast SSF, full-clean, and selected-table safety tests.

- [ ] **Step 5: Commit the catalog change**

```bash
git add tools/db_common.sh test/tools/test_db_scripts.py
git commit -m "Include storage enums in database backups"
```

### Task 2: Prove Export and Clean Restore Ordering in PostgreSQL

**Files:**
- Modify: `test/tools/test_db_scripts_postgresql.py`
- Modify: `tools/db_export.sh` only if the integration test exposes an ordering or schema propagation defect
- Modify: `tools/db_import.sh` only if the integration test exposes a clean-drop defect

**Interfaces:**
- Consumes: `db_export.sh` and `db_import.sh` with `--schema`, `--table`, `--in`, `--out`, and `--clean`.
- Produces: isolated-schema evidence that Storage enum definitions and JSON checks survive an actual selected-table backup and restore.

- [ ] **Step 1: Add PostgreSQL catalog helpers and a governed fixture**

Extend `test/tools/test_db_scripts_postgresql.py` with helpers that query the current schema:

```python
STORAGE_ENUM_TYPES = {
    "blackroom_market",
    "blackroom_source",
    "daily_bar_diagnostic_adjust",
    "daily_bar_diagnostic_classification",
    "ssf_change_signal_status",
}


def enum_type_exists(connection: Connection, schema: str, type_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = :schema AND t.typname = :type_name)"
            ),
            {"schema": schema, "type_name": type_name},
        ).scalar_one()
    )


def constraint_exists(connection: Connection, schema: str, table: str, name: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT EXISTS (SELECT FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :schema AND t.relname = :table AND c.conname = :name)"
            ),
            {"schema": schema, "table": table, "name": name},
        ).scalar_one()
    )
```

Create the three Storage tables in the fixture as legacy `varchar`/`jsonb` tables with valid values, then call the unified migration from a SQLAlchemy connection before invoking the scripts. This ensures the dump contains actual enum columns and actual JSON checks rather than relying on mocked output.

- [ ] **Step 2: Write the selected-table export/restore integration test**

Add a test that:

1. Runs `migrate_enums(connection)` in the isolated schema.
2. Exports `daily_bar_diagnostics` with `db_export.sh --no-gzip --schema <schema> --table daily_bar_diagnostics --out <dump>`.
3. Asserts its two Storage `CREATE TYPE` statements precede the table output and that the dump contains `ck_daily_bar_diagnostics_provider_outcome_status`.
4. Drops the isolated schema and recreates it.
5. Imports the dump with `db_import.sh --schema <schema> --table daily_bar_diagnostics --in <dump>`.
6. Verifies the two enum types, their labels, the table, its data, and its JSON check exist after restore.

Add the corresponding `ssf_change_signals` selected-table case for
`ssf_change_signal_status` and `ck_ssf_change_signals_event_types`. Full
business export ordering remains covered by the portable script tests because a
minimal isolated schema deliberately does not contain every entry in
`BUSINESS_TABLES`.

Use the existing `_run_script` fixture and preserve its explicit Compose environment defaults. The test must assert `result.returncode == 0` before inspecting the restored schema.

- [ ] **Step 3: Run the integration test before implementation changes**

Run:

```bash
TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/tools/test_db_scripts_postgresql.py -k "storage or restore" -v
```

Expected: PASS after Task 1 adds the Storage catalog entries. If PostgreSQL is unavailable, record the explicit skip; the portable test suite still proves the generated command ordering.

- [ ] **Step 4: Implement only the required script corrections**

Use the catalog from Task 1 as the only source for Storage enum selection. Keep the existing `pg_dump` invocation and `--table` list unchanged. If the integration test identifies a defect, fix it so:

- enum DDL is written before `pg_dump` output;
- schema-qualified type and table names use the requested `--schema` value;
- `pg_dump` emits table-owned JSON checks;
- full clean drops tables before types;
- shared types are not dropped during selected-table clean.

Do not add a second hand-written JSON-check DDL block.

- [ ] **Step 5: Run the portable and PostgreSQL script suites**

Run:

```bash
uv run pytest test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py -v
```

Expected: PASS or explicit PostgreSQL skips when unavailable; portable tests must pass without relying on PostgreSQL.

- [ ] **Step 6: Commit restore coverage**

```bash
git add test/tools/test_db_scripts_postgresql.py tools/db_export.sh tools/db_import.sh
git commit -m "Verify enum backup restore ordering"
```

### Task 3: Complete Rollback Evidence for All Governed Domains

**Files:**
- Modify: `test/storage/test_enum_governance.py`
- Modify: `test/storage/test_storage_enum_migration.py`
- Modify: `test/monitor/storage/test_enum_migration.py`
- Modify: `test/paper_trading/storage/test_enum_migration.py`
- Modify: `storage/enum_migration.py` only if a test demonstrates a rollback dependency or verification gap
- Modify: `monitor/storage/enum_migration.py` only if a test demonstrates a rollback dependency or verification gap
- Modify: `paper_trading/storage/enum_migration.py` only if a test demonstrates a rollback dependency or verification gap

**Interfaces:**
- Consumes: `migrate_enums(connection, rollback=True)` and the three domain adapters.
- Produces: PostgreSQL evidence that rollback restores legacy column types/defaults/indexes, removes JSON checks, and refuses unmanaged dependencies atomically.

- [ ] **Step 1: Add failing assertions for complete unified rollback state**

Add `bindparam` to the existing SQLAlchemy imports in
`test/storage/test_enum_governance.py`, then add this helper:

```python
MANAGED_CHECK_NAMES = {
    "ck_stock_monitor_targets_condition_type",
    "ck_daily_bar_diagnostics_provider_outcome_status",
    "ck_ssf_change_signals_event_types",
}


def _managed_check_names(connection: Connection) -> set[str]:
    return set(
        connection.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace = current_schema()::regnamespace "
                "AND conname IN :names"
            ).bindparams(bindparam("names", expanding=True)),
            {"names": MANAGED_CHECK_NAMES},
        ).scalars()
    )
```

Then extend the existing unified PostgreSQL fixture assertions after a successful `migrate_enums(connection)` followed by `migrate_enums(connection, rollback=True)`:

```python
def test_unified_rollback_restores_all_domains_and_removes_checks(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        assert migrate_enums(connection).converted is True
        result = migrate_enums(connection, rollback=True)

        assert result.rolled_back is True
        assert _all_managed_enum_types(connection) == set()
        assert _managed_check_names(connection) == set()
        assert _column_type(connection, "paper_orders", "side") == "character varying(10)"
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _column_type(connection, "blackroom_records", "market") == "character varying(5)"
        assert _column_type(connection, "daily_bar_diagnostics", "classification") == "character varying(50)"
        assert _column_type(connection, "ssf_change_signals", "status") == "character varying(20)"
```

Use the existing fixture-specific helpers and include all managed check names: `ck_stock_monitor_targets_condition_type`, `ck_daily_bar_diagnostics_provider_outcome_status`, and `ck_ssf_change_signals_event_types`.

- [ ] **Step 2: Add rollback dependency failure coverage for Storage**

Create a view using a Storage enum after forward migration:

```python
connection.execute(text("CREATE VIEW blackroom_market_dependency AS SELECT 'A'::blackroom_market AS market"))
with pytest.raises(StorageEnumMigrationError, match="blackroom_market: dependencies remain"):
    migrate_storage_enums(connection, rollback=True)
```

Assert all Storage enum types remain and `blackroom_records.market` is still `blackroom_market`. Add equivalent unified-command coverage if the failure must be wrapped as `EnumGovernanceError`.

- [ ] **Step 3: Run the new rollback tests to verify current behavior**

Run:

```bash
TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py test/monitor/storage/test_enum_migration.py test/paper_trading/storage/test_enum_migration.py -k "rollback" -v
```

Expected: existing domain tests pass; any failure identifies a concrete adapter gap. Do not change adapters merely to increase assertions if the current implementation already satisfies them.

- [ ] **Step 4: Fix only demonstrated rollback gaps**

If a test fails, preserve the adapter sequence:

1. preflight all adapters;
2. rollback all adapters in registration order;
3. verify all adapters in rollback mode;
4. commit only after the caller’s transaction succeeds.

For a dependency failure, perform no column conversion before dependency validation. For a JSON-check failure, leave enum columns and checks unchanged. For a successful rollback, restore indexes/defaults before dropping types and retain explicit type-dependency verification.

- [ ] **Step 5: Run the complete governance test set**

Run:

```bash
uv run pytest test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py test/monitor/storage/test_enum_migration.py test/paper_trading/storage/test_enum_migration.py -v
```

Expected: PASS or explicit PostgreSQL skips where the environment is unavailable.

- [ ] **Step 6: Commit rollback coverage and fixes**

```bash
git add test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py test/monitor/storage/test_enum_migration.py test/paper_trading/storage/test_enum_migration.py storage/enum_migration.py monitor/storage/enum_migration.py paper_trading/storage/enum_migration.py
git commit -m "Verify governed enum rollback safety"
```

### Task 4: Align Operational Documentation

**Files:**
- Modify: `docs/paper_trading.md:548-655`

**Interfaces:**
- Consumes: final catalog and script behavior from Tasks 1-3.
- Produces: one authoritative operator guide for full/selected export, clean restore, JSON checks, and rollback.

- [ ] **Step 1: Replace the incomplete governed-type description**

Update the unified migration section so it lists all governed domains:

- the 13 Paper Trading enum types already documented;
- the four Monitor/Forecast SSF types;
- the five Storage types: `blackroom_market`, `blackroom_source`, `daily_bar_diagnostic_adjust`, `daily_bar_diagnostic_classification`, and `ssf_change_signal_status`.

State that full exports create every managed type before dependent tables, selected-table exports create only required types with duplicate-safe DDL, and `pg_dump` preserves table-owned defaults, indexes, foreign keys, and JSON checks.

- [ ] **Step 2: Document clean restore and rollback limits**

Add this behavior next to the existing selected-table clean guidance:

```markdown
Selected-table clean export is unsupported. Selected-table clean import refuses
to run when an unselected table has a foreign key referencing the selected
table. This prevents the restore from silently dropping a constraint that the
selected-table dump cannot recreate. Use a full business-database clean restore
when the required tables are managed together, or use a separately reviewed
recovery procedure.
```

Explain that rollback converts enum columns back to their documented legacy string types, restores defaults and indexes, removes managed JSON checks, rejects unmanaged dependencies, and drops types only after dependencies are gone.

- [ ] **Step 3: Remove stale or contradictory statements**

Run:

```bash
rg -n "only.*paper_matching_runs|enum-aware for|matching-only|Backup restore ordering" docs/paper_trading.md
```

Expected: no stale matching-run-only backup claim remains. Keep the existing warning that clean import is not atomic and can leave a partial restore after the drop phase.

- [ ] **Step 4: Review documentation diff**

Run:

```bash
git diff --check && git diff -- docs/paper_trading.md
```

Expected: only the unified enum backup/restore/rollback section changes.

- [ ] **Step 5: Commit documentation**

```bash
git add docs/paper_trading.md
git commit -m "Document governed database restore procedures"
```

### Task 5: Run the Full Verification Gate

**Files:**
- Verify: `tools/db_common.sh`
- Verify: `tools/db_export.sh`
- Verify: `tools/db_import.sh`
- Verify: `test/tools/test_db_scripts.py`
- Verify: `test/tools/test_db_scripts_postgresql.py`
- Verify: `test/storage/test_enum_governance.py`
- Verify: `test/storage/test_storage_enum_migration.py`
- Verify: `test/monitor/storage/test_enum_migration.py`
- Verify: `test/paper_trading/storage/test_enum_migration.py`
- Verify: `docs/paper_trading.md`

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: fresh evidence for issue #39 acceptance criteria and a clean final diff.

- [ ] **Step 1: Run focused portable checks**

```bash
uv run pytest test/tools/test_db_common.py test/tools/test_db_scripts.py -v
uv run ruff format --check test/tools/test_db_common.py test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py test/monitor/storage/test_enum_migration.py test/paper_trading/storage/test_enum_migration.py
uv run ruff check test/tools/test_db_common.py test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py test/monitor/storage/test_enum_migration.py test/paper_trading/storage/test_enum_migration.py
```

Expected: all portable tests and Ruff checks pass.

- [ ] **Step 2: Run PostgreSQL integration coverage**

```bash
TEST_POSTGRESQL_URL="${TEST_POSTGRESQL_URL:-postgresql://quant:quant@localhost:5432/quant}" uv run pytest test/tools/test_db_scripts_postgresql.py test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py test/monitor/storage/test_enum_migration.py test/paper_trading/storage/test_enum_migration.py -v
```

Expected: all configured PostgreSQL tests pass. If the URL is unavailable, tests must show explicit skips and the final report must state that live PostgreSQL coverage was not available.

- [ ] **Step 3: Run repository quality gates**

```bash
uv run pre-commit run --all-files
uv run pytest test
uv run mypy
```

Expected: quality gates pass. If unrelated pre-existing failures occur, capture their exact test names and do not modify unrelated files.

- [ ] **Step 4: Inspect final diff and status**

```bash
git diff --check
git status --short
git log --oneline -10
git diff HEAD~4 -- tools/db_common.sh tools/db_export.sh tools/db_import.sh test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py test/storage/test_enum_governance.py test/storage/test_storage_enum_migration.py test/monitor/storage/test_enum_migration.py test/paper_trading/storage/test_enum_migration.py storage/enum_migration.py monitor/storage/enum_migration.py paper_trading/storage/enum_migration.py docs/paper_trading.md
```

Expected: only intended issue #39 files changed; existing unrelated `data/` and prior worktree artifacts remain untouched.

- [ ] **Step 5: Record acceptance evidence**

Confirm each issue criterion from the command output and tests:

- every introduced enum is emitted before dependent tables;
- clean import removes dependent objects before types;
- rollback restores string columns, defaults, indexes, and constraints before dropping types;
- Storage and Monitor JSON checks are preserved through export/import and removed consistently during rollback;
- isolated PostgreSQL tests prove forward restore and rollback ordering.
