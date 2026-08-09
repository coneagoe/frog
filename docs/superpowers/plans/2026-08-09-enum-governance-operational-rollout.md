# Enum Governance Operational Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an auditable enum-governance dry run, a tested maintenance-window runbook, and writer smoke evidence for issue #40.

**Architecture:** Extend the unified enum-governance result with immutable PostgreSQL catalog audit facts collected after each successful adapter preflight. The `--dry-run --json` command serializes those facts without DDL. Keep the three domain migrations authoritative for their own tables, enum labels, JSON checks, indexes, defaults, and rollback dependencies; add a focused integration smoke module that exercises existing public writer APIs after unified migration.

**Tech Stack:** Python 3.11+, SQLAlchemy, PostgreSQL, SQLite, pytest, Ruff, mypy, shell database export/import tools.

## Global Constraints

- Use `uv run` for all project Python commands.
- Preserve the single supported operator interface: `tools/migrate_enums.py` with `--dry-run`, `--rollback`, and `--json`.
- Dry runs must issue no DDL or DML and must preserve existing all-domain preflight atomicity.
- Do not alter normal application startup, Airflow schedules, task boundaries, retries, or SLAs.
- PostgreSQL owns native enum and JSON CHECK enforcement; SQLite tests prove portable application validation and writer contracts.
- API, CLI, Airflow, Celery, frontend-facing payloads, and export artifacts must retain canonical readable labels.
- Rollback is schema rollback only: do not add destructive table drops or implicit startup migration behavior.
- Preserve unrelated worktree changes and stage only issue #40 files per commit.

---

## File Structure

- Modify: `storage/enum_governance_adapter.py` — add the read-only audit callback to the domain-adapter contract.
- Modify: `storage/enum_governance.py` — define serializable audit dataclasses, capture audit facts after preflight, and return them in `EnumGovernanceResult`.
- Modify: `paper_trading/storage/enum_migration.py` — report Paper Trading group, column, index/default, observed-value, and rollback-dependency facts.
- Modify: `monitor/storage/enum_migration.py` — report Monitor/Forecast group facts and the condition JSON check status.
- Modify: `storage/enum_migration.py` — report Storage group facts and daily-bar/SSF JSON check status.
- Modify: `tools/migrate_enums.py` — retain concise text output and serialize the additive audit report in JSON.
- Modify: `test/storage/test_enum_governance.py` — unit-test coordinator audit collection, dry-run ordering, and PostgreSQL full-schema facts.
- Modify: `test/tools/test_migrate_enums.py` — assert stable JSON report serialization for every audit field.
- Create: `test/storage/test_enum_governance_smoke.py` — test migrated PostgreSQL writer flows and SQLite portable writer contracts.
- Modify: `docs/paper_trading.md` — make the unified enum section an executable maintenance window runbook, including independent verification, smoke, restart, and rollback decisions.
- Modify: `test/tools/test_db_scripts.py` and `test/tools/test_db_scripts_postgresql.py` only if a missing canonical-label/export assertion is observed while implementing the smoke suite.

### Task 1: Define a Serializable Unified Audit Contract

**Files:**
- Modify: `storage/enum_governance_adapter.py`
- Modify: `storage/enum_governance.py`
- Test: `test/storage/test_enum_governance.py`

**Interfaces:**
- Consumes: existing `EnumGovernanceAdapter.preflight(connection, *, rollback)` and domain migration result objects.
- Produces: `EnumGovernanceColumnAudit`, `EnumGovernanceGroupAudit`, `EnumGovernanceCheckAudit`, `EnumGovernanceDomainAudit`, and `EnumGovernanceResult.audits: tuple[EnumGovernanceDomainAudit, ...]`.
- Produces: `EnumGovernanceAdapter.audit(connection, *, rollback) -> EnumGovernanceDomainAudit` called only after that adapter's successful preflight.

- [ ] **Step 1: Write failing coordinator audit-order tests**

  Add a fake adapter audit callback in `test/storage/test_enum_governance.py` and assert a dry run produces its audit only after all preflights succeed:

  ```python
  def test_dry_run_collects_audits_only_after_every_preflight() -> None:
      events: list[str] = []
      result = migrate_enums(
          cast(Connection, FakeConnection()),
          dry_run=True,
          adapters=(
              _adapter("paper", events, audit=_audit("paper", events)),
              _adapter("monitor", events, audit=_audit("monitor", events)),
          ),
      )

      assert events == [
          "paper.preflight", "monitor.preflight", "paper.audit", "monitor.audit"
      ]
      assert [audit.name for audit in result.audits] == ["paper", "monitor"]
  ```

  Add a preflight-failure test asserting no `*.audit` event occurs. Add a non-PostgreSQL test asserting an empty audit tuple, because the command cannot inspect PostgreSQL catalog facts through SQLite.

- [ ] **Step 2: Run the focused tests to verify failure**

  Run: `uv run pytest test/storage/test_enum_governance.py -k audit -v`

  Expected: FAIL because `EnumGovernanceAdapter` lacks `audit` and `EnumGovernanceResult` lacks `audits`.

- [ ] **Step 3: Add the audit dataclasses and adapter callback**

  In `storage/enum_governance.py`, add frozen dataclasses with only JSON-serializable fields:

  ```python
  @dataclass(frozen=True)
  class EnumGovernanceColumnAudit:
      table_name: str
      column_name: str
      expected_type: str
      observed_type: str | None
      expected_labels: tuple[str, ...]
      observed_values: tuple[str | None, ...]
      expected_default: str | None
      observed_default: str | None
      index_names: tuple[str, ...]
      indexes_ready: bool
      ready: bool
      reason: str | None

  @dataclass(frozen=True)
  class EnumGovernanceGroupAudit:
      type_name: str
      expected_labels: tuple[str, ...]
      observed_labels: tuple[str, ...]
      columns: tuple[EnumGovernanceColumnAudit, ...]
      dependencies: tuple[str, ...]
      ready: bool
      reason: str | None

  @dataclass(frozen=True)
  class EnumGovernanceCheckAudit:
      table_name: str
      name: str
      expected: bool
      observed_definition: str | None
      ready: bool
      reason: str | None

  @dataclass(frozen=True)
  class EnumGovernanceDomainAudit:
      name: str
      groups: tuple[EnumGovernanceGroupAudit, ...]
      checks: tuple[EnumGovernanceCheckAudit, ...]
      missing_tables: tuple[str, ...]
      ready: bool
  ```

  Add `audit: Callable[..., EnumGovernanceDomainAudit]` to `EnumGovernanceAdapter`. Add `audits` to `EnumGovernanceResult`. In `migrate_enums`, retain the preflight loop unchanged, then call `adapter.audit(connection, rollback=rollback)` only after all preflights finish successfully and before the early `dry_run` return. Include the collected audits in all PostgreSQL results; use an empty tuple for non-PostgreSQL results. Keep `EnumGovernanceError` wrapping by running audits through `_run_phase(adapter, "audit", ...)`.

- [ ] **Step 4: Run focused tests to verify pass**

  Run: `uv run pytest test/storage/test_enum_governance.py -k audit -v`

  Expected: PASS. The event order proves failed preflight prevents report collection, and SQLite returns no fabricated catalog report.

- [ ] **Step 5: Commit the coordinator contract**

  ```bash
  git add storage/enum_governance.py storage/enum_governance_adapter.py test/storage/test_enum_governance.py
  git commit -m "Add enum governance audit contract"
  ```

### Task 2: Collect Domain Catalog Facts for Full-Schema Dry Runs

**Files:**
- Modify: `paper_trading/storage/enum_migration.py`
- Modify: `monitor/storage/enum_migration.py`
- Modify: `storage/enum_migration.py`
- Modify: `test/storage/test_enum_governance.py`
- Test: `test/paper_trading/storage/test_enum_migration.py`
- Test: `test/monitor/storage/test_enum_migration.py`
- Test: `test/storage/test_storage_enum_migration.py`

**Interfaces:**
- Consumes: audit dataclasses from Task 1, each module's `*_ENUM_GROUPS`, `_column_facts`, `_column_default`, `_enum_labels`, existing check readers, index readers, and `_type_dependencies`.
- Produces: each adapter's `audit(connection, *, rollback) -> EnumGovernanceDomainAudit` implementation and an `EnumGovernanceAdapter` initialized with that callback.
- Produces: preflight JSON facts for every selected enum column, expected/observed labels and values, required JSON checks, rollback dependencies, and readiness.

- [ ] **Step 1: Write PostgreSQL integration tests for full audit facts**

  In `test/storage/test_enum_governance.py`, use the existing `postgres_schema` fixture and assert a unified dry run on the legacy schema reports all groups and no mutation:

  ```python
  def test_dry_run_reports_all_schema_readiness_facts(postgres_schema) -> None:
      engine, schema = postgres_schema
      with engine.begin() as connection:
          connection.execute(text(f'SET search_path TO "{schema}"'))
          connection.execute(
              text("INSERT INTO paper_orders (id, side, status, market) VALUES (1, 'buy', 'accepted', 'a_share')")
          )

          result = migrate_enums(connection, dry_run=True)

      audits = {audit.name: audit for audit in result.audits}
      paper = next(group for group in audits["paper_trading"].groups if group.type_name == "paper_order_side")
      assert paper.expected_labels == ("buy", "sell")
      assert paper.observed_labels == ()
      assert paper.columns[0].observed_values == ("buy",)
      assert paper.columns[0].observed_type == "character varying(10)"
      assert audits["monitor"].checks[0].name == "ck_stock_monitor_targets_condition_type"
      assert {check.name for check in audits["storage"].checks} == {
          "ck_daily_bar_diagnostics_provider_outcome_status",
          "ck_ssf_change_signals_event_types",
      }
      assert all(audit.ready for audit in result.audits)
  ```

  Add a converted-schema case asserting enum labels become `observed_labels`, required checks are ready, and observed values remain readable strings. Add a rollback-preflight case that creates a view using `blackroom_market` and asserts the Storage group reports the dependency before the unified command raises.

- [ ] **Step 2: Run focused PostgreSQL tests to verify failure**

  Run: `uv run pytest test/storage/test_enum_governance.py -k "readiness_facts or audit" -v`

  Expected: FAIL because the three production adapters do not provide audit callbacks or catalog facts.

- [ ] **Step 3: Implement one consistent domain-audit pattern**

  In each migration module, add a private `_adapter_audit(connection, *, rollback)` that:

  1. derives `missing_tables` from its existing governed-table list;
  2. creates one `EnumGovernanceGroupAudit` for every existing `*_ENUM_GROUPS` item, preserving group order;
  3. reads `observed_labels` with the existing `_enum_labels` helper;
  4. reads each present column's type/default with existing catalog helpers and its distinct values with a parameterized `SELECT DISTINCT ... ORDER BY ...` query; use an empty observed-value tuple for missing tables;
  5. lists configured index names for Paper Trading and Monitor, and marks `indexes_ready` by reusing each module's existing index catalog validation logic without raising from the audit path;
  6. emits check audits for Monitor's condition check and Storage's two existing `_CHECKS`; Paper Trading returns an empty check tuple;
  7. on `rollback=True`, reads existing `_type_dependencies` for present enum types; on conversion dry-run, returns an empty dependency tuple;
  8. calculates `ready` and `reason` from observed catalog facts, without duplicating or weakening preflight's validation decision.

  Keep audit functions read-only. They must not call `_create_type`, `_alter_group`, `_add_condition_check`, `_ensure_indexes`, `_rollback`, or metadata creation. Register each function in `PAPER_TRADING_ENUM_ADAPTER`, `MONITOR_ENUM_ADAPTER`, and `STORAGE_ENUM_ADAPTER`.

- [ ] **Step 4: Run domain and coordinator integration tests**

  Run: `uv run pytest test/storage/test_enum_governance.py test/paper_trading/storage/test_enum_migration.py test/monitor/storage/test_enum_migration.py test/storage/test_storage_enum_migration.py -v`

  Expected: PASS with `TEST_POSTGRESQL_URL` configured; otherwise PostgreSQL cases are explicitly skipped while non-PostgreSQL tests pass.

- [ ] **Step 5: Commit domain audit reporting**

  ```bash
  git add paper_trading/storage/enum_migration.py monitor/storage/enum_migration.py storage/enum_migration.py test/storage/test_enum_governance.py test/paper_trading/storage/test_enum_migration.py test/monitor/storage/test_enum_migration.py test/storage/test_storage_enum_migration.py
  git commit -m "Report enum migration schema readiness"
  ```

### Task 3: Expose Audit Facts Through the Operator CLI

**Files:**
- Modify: `tools/migrate_enums.py`
- Modify: `test/tools/test_migrate_enums.py`

**Interfaces:**
- Consumes: `EnumGovernanceResult` with `audits` from Tasks 1-2.
- Produces: `uv run tools/migrate_enums.py --dry-run --json` JSON that includes `audits` and is safe to retain as a maintenance record.

- [ ] **Step 1: Write the failing JSON shape test**

  Replace the local fake result in `test/tools/test_migrate_enums.py` with the actual audit dataclasses or construct equivalent test data. Assert exact JSON keys and serializable label/value data:

  ```python
  def test_main_emits_json_schema_readiness_audits(monkeypatch, capsys) -> None:
      monkeypatch.setattr(command, "migrate_enums", lambda connection, **kwargs: _result_with_audits())
      monkeypatch.setattr(command, "parse_config", lambda: None)
      monkeypatch.setattr(command, "get_storage", lambda: FakeStorage(FakeTransaction()))

      assert command.main(["--dry-run", "--json"]) == 0

      output = json.loads(capsys.readouterr().out)
      audit = output["audits"][0]
      assert audit["name"] == "paper_trading"
      assert audit["groups"][0]["expected_labels"] == ["buy", "sell"]
      assert audit["groups"][0]["columns"][0]["observed_values"] == ["buy"]
      assert audit["checks"] == []
  ```

  Keep the existing compact text-output test, extending only its fake result construction as necessary.

- [ ] **Step 2: Run the CLI test to verify failure**

  Run: `uv run pytest test/tools/test_migrate_enums.py -v`

  Expected: FAIL because the fake result and production `EnumGovernanceResult` do not yet expose the requested JSON audit shape.

- [ ] **Step 3: Serialize additive audit data without new flags**

  Keep `_print_result` using `json.dumps(asdict(result), ensure_ascii=False, sort_keys=True)` for JSON so nested frozen dataclasses become arrays and objects. Update test fakes to match the production `audits` field. Do not add flags, do not alter non-JSON output fields, and do not convert canonical labels to enum member names.

- [ ] **Step 4: Run the CLI and format checks**

  Run: `uv run pytest test/tools/test_migrate_enums.py -v && uv run ruff format --check tools/migrate_enums.py test/tools/test_migrate_enums.py && uv run ruff check tools/migrate_enums.py test/tools/test_migrate_enums.py`

  Expected: PASS.

- [ ] **Step 5: Commit CLI audit output**

  ```bash
  git add tools/migrate_enums.py test/tools/test_migrate_enums.py
  git commit -m "Expose enum readiness audit in migration CLI"
  ```

### Task 4: Add Focused Writer Smoke Coverage for PostgreSQL and SQLite

**Files:**
- Create: `test/storage/test_enum_governance_smoke.py`
- Modify: `test/paper_trading/api/test_matching_api.py` only if a reusable fixture/helper must be extracted without changing its existing behavior.
- Modify: `test/storage/test_storage_db.py` only if existing SQLite storage fixtures need a small reusable helper.

**Interfaces:**
- Consumes: `migrate_enums(connection)`, `PaperTradingRepository`, `MonitorTargetService`, `StorageDb.create_monitor_target`, `StorageDb.create_blackroom_record`, `StorageDb.save_ssf_change_signals`, and the existing daily-bar diagnostic writer.
- Produces: focused smoke evidence for matching `completed_with_warnings`, Paper Trading order/ledger writes, Monitor target writes, Blackroom writes, daily-bar diagnostics, and SSF signal writes.

- [ ] **Step 1: Write PostgreSQL smoke tests against real migrated tables**

  Create `test/storage/test_enum_governance_smoke.py`. Reuse the `TEST_POSTGRESQL_URL` guarded engine pattern and a unique schema. Build all required mapped tables through `migrate_enums(connection)`, then use a session bound to the same connection/schema. Add tests with these concrete assertions:

  ```python
  def test_postgresql_governed_writer_smoke_uses_canonical_labels(postgres_schema) -> None:
      engine, schema = postgres_schema
      with engine.begin() as connection:
          connection.execute(text(f'SET search_path TO "{schema}"'))
          assert migrate_enums(connection).converted is True

      with _session(engine, schema) as session:
          repository = PaperTradingRepository(session)
          account = repository.create_account("enum-smoke", Decimal("100000.00"))
          order = repository.create_order(
              account.id, "000001", OrderSide.BUY, 100, Decimal("10.00"),
              date(2026, 8, 9), OrderStatus.ACCEPTED, frozen_cash=Decimal("1005.00"),
          )
          assert order.side == "buy"
          assert session.query(PaperCashLedger).filter_by(account_id=account.id, event_type="freeze").count() == 1
  ```

  In the same module, exercise the existing matching API flow from `test_matching_api_records_snapshot_market_data_failure` with a PostgreSQL session override and assert JSON `status == "completed_with_warnings"`. Use `MonitorTargetService(storage=StorageDb-backed instance)` to create a valid `price_threshold` target and assert serialized `market`, `frequency`, and `reset_mode` labels. Use `create_blackroom_record`, the existing daily-bar diagnostic upsert method, and `save_ssf_change_signals` with valid payloads, then query their model rows and assert values are ordinary canonical strings.

  Assert PostgreSQL catalog data too: each selected writer table reports the expected enum type; the Monitor condition check and both Storage JSON checks exist after migration. Keep one test focused on writer behavior and one on catalog verification so failure locations are clear.

- [ ] **Step 2: Run the new PostgreSQL smoke tests to verify failure**

  Run: `uv run pytest test/storage/test_enum_governance_smoke.py -v`

  Expected: FAIL until the fixture/session setup and all smoke calls are correctly implemented; no test may use direct SQL to stand in for the required writer path.

- [ ] **Step 3: Add the minimal fixture helpers and make the smoke suite pass**

  Add local helpers only in `test/storage/test_enum_governance_smoke.py`:

  - `_engine()` skips with `TEST_POSTGRESQL_URL is unavailable` when absent.
  - `postgres_schema` creates a unique schema, sets `search_path`, runs unified migration, and drops the schema with `CASCADE` in teardown.
  - `_session(engine, schema)` opens a SQLAlchemy session whose connection executes `SET search_path TO "<schema>"` before invoking writers.
  - a deterministic fake market-data provider copied minimally from the matching API test to produce one valuation warning.

  Do not modify production writers merely to accommodate test setup. Reuse model/public storage methods, commit expected transactions, and cleanly close sessions and engines.

- [ ] **Step 4: Add SQLite portable-contract cases**

  In the same module, create a SQLite engine with `Base.metadata.create_all(engine)` and assert application-level validation remains portable:

  ```python
  @pytest.mark.parametrize(
      ("operation", "message"),
      [
          (lambda db: db.create_blackroom_record(stock_code="000001", market="US"), "market"),
          (lambda db: db.save_ssf_change_signals([{**valid_signal, "event_types": ["split"]}]), "event_types"),
          (lambda db: MonitorTargetService(storage=db).add_target("600519", "A", {"type": "unknown"}), "condition"),
      ],
  )
  def test_sqlite_writer_contract_rejects_invalid_governed_values(operation, message) -> None:
      with pytest.raises(ValueError, match=message):
          operation(sqlite_storage)
  ```

  Adapt exception assertions to the existing public method contracts where services return a validation-result dictionary rather than raising. Add valid SQLite writes for the same Blackroom, monitor target, daily-bar diagnostic, and SSF signal paths, asserting canonical labels are preserved.

- [ ] **Step 5: Run smoke and adjacent regression tests**

  Run: `uv run pytest test/storage/test_enum_governance_smoke.py test/paper_trading/api/test_matching_api.py test/monitor/test_monitor_target_service.py test/storage/test_blackroom_storage_db.py -v`

  Expected: PASS. PostgreSQL smoke cases may skip only when `TEST_POSTGRESQL_URL` is absent; SQLite cases must run.

- [ ] **Step 6: Commit smoke evidence**

  ```bash
  git add test/storage/test_enum_governance_smoke.py test/paper_trading/api/test_matching_api.py test/storage/test_storage_db.py
  git commit -m "Add enum governance writer smoke tests"
  ```

### Task 5: Publish and Test the Maintenance-Window Runbook

**Files:**
- Modify: `docs/paper_trading.md`
- Modify: `test/tools/test_db_scripts.py` only if documentation reveals a missing full-export label assertion.
- Modify: `test/tools/test_db_scripts_postgresql.py` only if documentation reveals a missing restored readable-label assertion.

**Interfaces:**
- Consumes: `tools/migrate_enums.py --dry-run --json`, apply, rollback; `tools/db_export.sh`; `tools/db_import.sh`; Task 4 smoke suite.
- Produces: the authoritative operator procedure, including backup verification, writer shutdown, preflight review, independent catalog verification, smoke gate, controlled restart, and non-destructive rollback.

- [ ] **Step 1: Write precise runbook acceptance assertions or identify existing coverage**

  Inspect `test/tools/test_db_scripts.py` and `test/tools/test_db_scripts_postgresql.py`. Preserve their existing assertions that full and selected exports place enum `CREATE TYPE` before dependent tables, that imported rows retain labels such as `bfq`, `downloaded`, `signal`, and `increase`, and that clean selected restores are rejected before mutation. Add a narrowly scoped assertion only if no existing test proves a governed export/import returns readable labels.

- [ ] **Step 2: Run export/import evidence tests**

  Run: `uv run pytest test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py -v`

  Expected: PASS or explicit PostgreSQL skips when `TEST_POSTGRESQL_URL` is unavailable. Any new assertion must fail first if it exposes a real missing contract.

- [ ] **Step 3: Replace the unified migration prose with an executable checklist**

  In `docs/paper_trading.md` under `### Unified enum governance migration`, retain the governed type inventory and add these explicit sections in order:

  ```markdown
  #### Preconditions

  - Record database, schema, deployment revision, maintenance owner, and start time.
  - Stop API/CLI automation, Airflow scheduling and workers, Celery workers, and all other business writers; leave PostgreSQL running.
  - Create a full business-database export with `tools/db_export.sh`, and prove it can be inspected and restored in an isolated target before production DDL.

  #### Preflight and Migration

  uv run tools/migrate_enums.py --dry-run --json
  uv run tools/migrate_enums.py --json

  Retain both JSON documents. Do not proceed while any group, column, check, or dependency is non-ready.

  #### Independent Verification and Smoke

  Verify enum labels, column types, defaults, indexes, and JSON checks through PostgreSQL catalog queries independent of the command output. Run `uv run pytest test/storage/test_enum_governance_smoke.py -v` with `TEST_POSTGRESQL_URL` targeting an isolated migrated database. Resume compatible services only after this gate passes.

  #### Schema Rollback

  uv run tools/migrate_enums.py --rollback --json

  Keep writers stopped. This converts columns back to documented varchar types and removes managed types/checks after dependency verification. It does not restore lost data or replace a verified backup restore. Never drop governed tables to force rollback and never rely on application startup to migrate schema.
  ```

  State exact restart ordering for the deployment: database remains running; start application/API and one worker class at a time; confirm canonical labels in API/CLI task output and export before returning schedules to normal. Do not claim frontend, Airflow, or Celery runtime verification where the repository only has contract tests; name their observable label contracts and the required operator observation.

- [ ] **Step 4: Run documentation-adjacent tests and formatting checks**

  Run: `uv run pytest test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py test/tools/test_migrate_enums.py -v && uv run ruff format --check storage/enum_governance.py storage/enum_governance_adapter.py paper_trading/storage/enum_migration.py monitor/storage/enum_migration.py storage/enum_migration.py tools/migrate_enums.py test/storage/test_enum_governance.py test/storage/test_enum_governance_smoke.py test/tools/test_migrate_enums.py && uv run ruff check storage/enum_governance.py storage/enum_governance_adapter.py paper_trading/storage/enum_migration.py monitor/storage/enum_migration.py storage/enum_migration.py tools/migrate_enums.py test/storage/test_enum_governance.py test/storage/test_enum_governance_smoke.py test/tools/test_migrate_enums.py`

  Expected: PASS, with PostgreSQL integration cases explicitly skipped only when the environment variable is unavailable.

- [ ] **Step 5: Commit operational documentation and any evidence test**

  ```bash
  git add docs/paper_trading.md test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py
  git commit -m "Document enum governance maintenance rollout"
  ```

### Task 6: Run the Issue #40 Verification Gate

**Files:**
- Verify only: all files changed by Tasks 1-5.

**Interfaces:**
- Consumes: all implementation, runbook, and tests from Tasks 1-5.
- Produces: evidence that every issue #40 acceptance criterion has a direct passing test or documented operator check.

- [ ] **Step 1: Run the complete focused enum-governance test matrix**

  Run:

  ```bash
  uv run pytest test/tools/test_migrate_enums.py test/storage/test_enum_governance.py test/storage/test_enum_governance_smoke.py test/paper_trading/storage/test_enum_migration.py test/monitor/storage/test_enum_migration.py test/storage/test_storage_enum_migration.py test/tools/test_db_scripts.py test/tools/test_db_scripts_postgresql.py -v
  ```

  Expected: PASS with `TEST_POSTGRESQL_URL` configured. Without it, record the skipped PostgreSQL tests and do not claim PostgreSQL acceptance is verified.

- [ ] **Step 2: Run static gates for changed Python files**

  Run:

  ```bash
  uv run ruff format --check storage/enum_governance.py storage/enum_governance_adapter.py paper_trading/storage/enum_migration.py monitor/storage/enum_migration.py storage/enum_migration.py tools/migrate_enums.py test/storage/test_enum_governance.py test/storage/test_enum_governance_smoke.py test/tools/test_migrate_enums.py
  uv run ruff check storage/enum_governance.py storage/enum_governance_adapter.py paper_trading/storage/enum_migration.py monitor/storage/enum_migration.py storage/enum_migration.py tools/migrate_enums.py test/storage/test_enum_governance.py test/storage/test_enum_governance_smoke.py test/tools/test_migrate_enums.py
  uv run mypy storage/enum_governance.py storage/enum_governance_adapter.py paper_trading/storage/enum_migration.py monitor/storage/enum_migration.py storage/enum_migration.py tools/migrate_enums.py
  git diff --check
  ```

  Expected: PASS. Resolve formatting, lint, typing, or whitespace failures before issue closure.

- [ ] **Step 3: Inspect the final diff and working tree**

  Run: `git status --short && git diff --check && git diff HEAD~5..HEAD --stat`

  Expected: only intended issue #40 commits/files plus pre-existing user worktree items. Do not add or modify `data/` or unrelated untracked specs/plans.

- [ ] **Step 4: Commit any final verification-only correction**

  ```bash
  git add <only-files-corrected-by-verification>
  git commit -m "Verify enum governance rollout"
  ```

  Do not create an empty commit. If verification requires no correction, do not commit this task.

## Self-Review

Spec coverage:

- Full-schema dry-run detail is implemented by Tasks 1-3 and PostgreSQL-tested in Task 2.
- Maintenance backup, writer stop, live migration, independent verification, smoke, restart, and rollback procedure are documented in Task 5.
- Matching, Paper Trading, Monitor, Blackroom, diagnostics, and SSF writer paths are covered in Task 4.
- PostgreSQL integration and SQLite portable application contracts are separated in Task 4 and enforced in Task 6.
- Rollback/no destructive table drops is covered by existing migration tests, Task 2 dependency facts, and Task 5 procedure.
- API/CLI/export readable labels are covered by Task 3, Task 4 matching response, and Task 5 export/import evidence.

Completeness scan: every action, test, command, and production interface is concrete. Each new production interface is defined in Task 1 before later tasks consume it. The audit callback is additive and all audit collection occurs after the existing full preflight loop, preserving no-DDL-on-failure behavior.
