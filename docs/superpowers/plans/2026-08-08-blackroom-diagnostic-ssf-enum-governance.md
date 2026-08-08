# Blackroom, Diagnostic, and SSF Enum Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce Blackroom, daily-bar diagnostic, and SSF change-signal finite values through application validation, native PostgreSQL enums, and JSON checks.

**Architecture:** A dedicated Storage enum-governance adapter owns the three cross-domain tables and is appended to the unified adapter registry. A storage-domain `StrEnum` module feeds value-persisting SQLAlchemy mappings and portable validation helpers at the existing repository and `StorageDb` write boundaries. PostgreSQL migration adds five scalar enum types and two JSON checks; SQLite relies on the same application validation.

**Tech Stack:** Python 3.11 `StrEnum`, SQLAlchemy, PostgreSQL native enum/JSONB check constraints, SQLite, pytest, uv.

## Global Constraints

- Use readable `StrEnum.value` labels; never introduce integer encodings.
- Apply PostgreSQL DDL only through the unified `tools/migrate_enums.py` command and its adapter registry.
- Preserve Blackroom defaults: `market='A'`, `source='manual'`; preserve SSF status default `signal`.
- Keep provider names, provider detail, and SSF `detail_json` unconstrained.
- Reject invalid application writes before persistence on SQLite and PostgreSQL.
- Reject invalid direct PostgreSQL JSON writes through stable named checks.
- Reject unknown legacy values during migration; never coerce, rename, or delete them.
- Use `uv run` for all Python, pytest, Ruff, and mypy commands.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLAs.

---

## File Structure

- Create: `storage/domain_enums.py` - canonical `StrEnum` definitions and portable validators for scalar and JSON finite contracts.
- Modify: `storage/model/blackroom_record.py` - map Blackroom market/source to named value enums.
- Modify: `storage/model/paper_trading.py` - map daily diagnostic adjustment/classification to named value enums.
- Modify: `storage/model/ssf_change_signal.py` - map SSF status to its named value enum.
- Modify: `paper_trading/storage/repository.py` - validate and normalize diagnostic values before Core/ORM upsert.
- Modify: `storage/storage_db.py` - validate SSF payload status/event types before building each insert.
- Create: `storage/enum_migration.py` - dedicated Storage adapter with preflight, apply, verify, and rollback of five scalar enums and two JSON checks.
- Modify: `storage/enum_governance.py` - append the Storage adapter to the unified registry.
- Modify: `test/storage/test_blackroom_storage_db.py` - cover portable Blackroom scalar validation while retaining CRUD regression coverage.
- Modify: `test/paper_trading/storage/test_repository.py` - cover diagnostic enum/JSON validation and canonical normal flow.
- Modify: `test/storage/test_storage_db.py` - cover SSF scalar/JSON validation and signal/no-signal flow.
- Create: `test/storage/test_enum_migration.py` - isolated PostgreSQL coverage for Storage adapter conversion, checks, idempotence, preflight rejection, and rollback.
- Modify: `test/storage/test_enum_governance.py` - add legacy Storage tables, assert registry order, and prove unified atomic behavior with Storage preflight failure.
- Modify: `docs/superpowers/specs/2026-08-08-blackroom-diagnostic-ssf-enum-design.md` - correct the scalar enum type count from seven to five.

### Task 1: Define Storage Domain Enums and Map Scalar Columns

**Files:**
- Create: `storage/domain_enums.py`
- Modify: `storage/model/blackroom_record.py:1-46`
- Modify: `storage/model/paper_trading.py:1-66,399-410`
- Modify: `storage/model/ssf_change_signal.py:1-33`
- Test: `test/storage/test_blackroom_storage_db.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/storage/model/test_ssf_change_signal.py`

**Interfaces:**
- Produces: `BlackroomMarket`, `BlackroomSource`, `DailyBarDiagnosticAdjust`, `DailyBarDiagnosticClassification`, `ProviderOutcomeStatus`, `SSFChangeSignalStatus`, and `SSFEventType`, all `StrEnum` types in `storage.domain_enums`.
- Produces: `validate_provider_outcomes(value: object) -> list[dict[str, object]]` and `validate_ssf_event_types(value: object) -> list[str]`; both raise `ValueError` for an invalid JSON contract.
- Produces: value-persisting SQLAlchemy mappings named `blackroom_market`, `blackroom_source`, `daily_bar_diagnostic_adjust`, `daily_bar_diagnostic_classification`, and `ssf_change_signal_status`.

- [ ] **Step 1: Write failing scalar-mapping tests**

Add model assertions that prove the mapped type names and the allowed labels:

```python
from storage.domain_enums import BlackroomMarket, SSFChangeSignalStatus
from storage.model import BlackroomRecord
from storage.model.ssf_change_signal import SSFChangeSignal


def test_blackroom_scalar_columns_use_value_enums():
    assert BlackroomRecord.__table__.c.market.type.name == "blackroom_market"
    assert BlackroomRecord.__table__.c.source.type.name == "blackroom_source"
    assert tuple(member.value for member in BlackroomMarket) == ("A", "HK", "ETF")


def test_ssf_status_uses_value_enum():
    assert SSFChangeSignal.__table__.c.status.type.name == "ssf_change_signal_status"
    assert tuple(member.value for member in SSFChangeSignalStatus) == ("signal", "no_signal")
```

Add an equivalent `DailyBarDiagnostic` assertion for `daily_bar_diagnostic_adjust` and `daily_bar_diagnostic_classification` in `test_repository.py`.

- [ ] **Step 2: Run the new mapping tests to verify failure**

Run: `uv run pytest test/storage/test_blackroom_storage_db.py test/paper_trading/storage/test_repository.py test/storage/model/test_ssf_change_signal.py -q`

Expected: FAIL because `storage.domain_enums` and the new native mappings do not exist.

- [ ] **Step 3: Define enum types and reusable value enum mappings**

Create `storage/domain_enums.py` with these exact definitions and validators:

```python
from enum import StrEnum
from typing import Any


class BlackroomMarket(StrEnum):
    A = "A"
    HK = "HK"
    ETF = "ETF"


class BlackroomSource(StrEnum):
    MANUAL = "manual"
    SHAREHOLDER_SELLING = "shareholder_selling"
    SHAREHOLDER_REDUCTION = "shareholder_reduction"


class DailyBarDiagnosticAdjust(StrEnum):
    BFQ = "bfq"
    QFQ = "qfq"
    HFQ = "hfq"


class DailyBarDiagnosticClassification(StrEnum):
    MISSING_MARKET_DATA = "missing_market_data"
    MISSING_EXACT_DATE = "missing_exact_date"
    DOWNLOADED = "downloaded"


class ProviderOutcomeStatus(StrEnum):
    DOWNLOADED = "downloaded"
    EMPTY = "empty"
    ERROR = "error"


class SSFChangeSignalStatus(StrEnum):
    SIGNAL = "signal"
    NO_SIGNAL = "no_signal"


class SSFEventType(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    NEW_ENTRY = "new_entry"
    EXIT = "exit"
```

Implement the two validators with `isinstance(value, list)` checks, `isinstance(item, dict)` / `isinstance(item, str)` checks, and `ProviderOutcomeStatus(item["status"])` / `SSFEventType(item)` conversion. Return copied normalized lists and raise clear `ValueError` messages identifying `provider_outcomes` or `event_types`.

Add a local `_value_enum` helper to each affected model if one is not already available in that file. Use SQLAlchemy `Enum(..., values_callable=lambda enum_type: [member.value for member in enum_type], native_enum=True, validate_strings=True, _create_events=False)`. Replace only the five target `String` columns; preserve annotations and all existing defaults.

- [ ] **Step 4: Run the mapping tests to verify pass**

Run: `uv run pytest test/storage/test_blackroom_storage_db.py test/paper_trading/storage/test_repository.py test/storage/model/test_ssf_change_signal.py -q`

Expected: PASS, including the existing Blackroom CRUD and SSF schema tests.

- [ ] **Step 5: Commit scalar contracts**

```bash
git add storage/domain_enums.py storage/model/blackroom_record.py storage/model/paper_trading.py storage/model/ssf_change_signal.py test/storage/test_blackroom_storage_db.py test/paper_trading/storage/test_repository.py test/storage/model/test_ssf_change_signal.py
git commit -m "Define storage enum contracts"
```

### Task 2: Validate Existing Diagnostic and SSF Write Boundaries

**Files:**
- Modify: `paper_trading/storage/repository.py:61-122`
- Modify: `storage/storage_db.py:2090-2170`
- Modify: `test/paper_trading/storage/test_repository.py:56-124`
- Modify: `test/storage/test_storage_db.py:3361-3551`

**Interfaces:**
- Consumes: `DailyBarDiagnosticAdjust`, `DailyBarDiagnosticClassification`, `SSFChangeSignalStatus`, `validate_provider_outcomes`, and `validate_ssf_event_types` from `storage.domain_enums`.
- Produces: `PaperTradingRepository.upsert_daily_bar_diagnostic(...)` raises `ValueError` for unknown adjustment, classification, or provider outcome status before executing its upsert.
- Produces: `StorageDb._save_ssf_change_signal_records(...)` rejects an invalid `status` or `event_types` payload without inserting that record, preserving its existing per-record error isolation.

- [ ] **Step 1: Write failing repository validation tests**

Add direct SQLite repository tests:

```python
@pytest.mark.parametrize(
    ("adjust", "classification", "outcomes"),
    [
        ("raw", "downloaded", []),
        ("bfq", "partial", []),
        ("bfq", "downloaded", [{"provider": "tushare", "status": "partial"}]),
        ("bfq", "downloaded", {"provider": "tushare", "status": "downloaded"}),
    ],
)
def test_upsert_daily_bar_diagnostic_rejects_invalid_finite_values(sqlite_session, adjust, classification, outcomes):
    Base.metadata.create_all(sqlite_session.get_bind())
    with pytest.raises(ValueError):
        PaperTradingRepository(sqlite_session).upsert_daily_bar_diagnostic(
            date(2026, 8, 8), "000001", adjust, classification, outcomes, resolved=False
        )
```

Add `StorageDb` tests that call `save_ssf_change_signals` with an invalid explicit `status` and with `event_types=["split"]`, then assert an empty returned ID list and zero persisted rows. Retain the current test proving valid signal payload insertion and no-signal marker insertion.

- [ ] **Step 2: Run the write-boundary tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q`

Expected: FAIL because Core upserts currently accept unvalidated diagnostic and SSF JSON values.

- [ ] **Step 3: Normalize and validate before every existing persistence call**

In `PaperTradingRepository.upsert_daily_bar_diagnostic`, retain `canonical_adjust_label`, then normalize with:

```python
adjust = DailyBarDiagnosticAdjust(canonical_adjust_label(adjust)).value
classification = DailyBarDiagnosticClassification(classification).value
provider_outcomes = validate_provider_outcomes(provider_outcomes)
```

Do this before constructing `values` so the PostgreSQL and SQLite Core upsert paths share the same behavior.

In `StorageDb._save_ssf_change_signal_records`, validate within the existing per-payload `try` block before the statement is built:

```python
status = SSFChangeSignalStatus(payload.get("status", SSF_CHANGE_SIGNAL_STATUS_SIGNAL)).value
event_types = validate_ssf_event_types(payload["event_types"])
```

Store `status` and `event_types` in `signal_payload`. This preserves existing behavior: a malformed record is logged and skipped, valid records in the same input list still commit, `save_ssf_change_signals` defaults to `signal`, and `mark_ssf_change_candidates_processed` still writes `no_signal` plus `[]`.

- [ ] **Step 4: Run focused tests to verify pass**

Run: `uv run pytest test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q`

Expected: PASS, including canonical diagnostic upserts, SSF idempotence, valid signal writes, and no-signal marker behavior.

- [ ] **Step 5: Commit portable write validation**

```bash
git add paper_trading/storage/repository.py storage/storage_db.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py
git commit -m "Validate diagnostic and SSF writes"
```

### Task 3: Add the Dedicated Storage PostgreSQL Migration Adapter

**Files:**
- Create: `storage/enum_migration.py`
- Modify: `storage/enum_governance.py:30-33`
- Create: `test/storage/test_enum_migration.py`

**Interfaces:**
- Consumes: enum types and models from Tasks 1-2 and `EnumGovernanceAdapter` from `storage.enum_governance_adapter`.
- Produces: `STORAGE_ENUM_GROUPS`, `STORAGE_ENUM_ADAPTER`, `StorageEnumMigrationError`, and `migrate_storage_enums(connection, *, dry_run=False, rollback=False)`.
- Produces: PostgreSQL types `blackroom_market`, `blackroom_source`, `daily_bar_diagnostic_adjust`, `daily_bar_diagnostic_classification`, and `ssf_change_signal_status`; checks `ck_daily_bar_diagnostics_provider_outcome_status` and `ck_ssf_change_signals_event_types`.
- Produces: `ENUM_GOVERNANCE_ADAPTERS == (PAPER_TRADING_ENUM_ADAPTER, MONITOR_ENUM_ADAPTER, STORAGE_ENUM_ADAPTER)`.

- [ ] **Step 1: Write failing PostgreSQL adapter tests**

Create an isolated-schema fixture with these legacy tables:

```sql
CREATE TABLE blackroom_records (
  id integer primary key,
  market varchar(5) NOT NULL DEFAULT 'A',
  source varchar(50) NOT NULL DEFAULT 'manual'
);
CREATE TABLE daily_bar_diagnostics (
  id integer primary key,
  adjust varchar(10) NOT NULL,
  classification varchar(50) NOT NULL,
  provider_outcomes jsonb NOT NULL
);
CREATE TABLE ssf_change_signals (
  id integer primary key,
  status varchar(20) NOT NULL DEFAULT 'signal',
  event_types jsonb NOT NULL
);
```

Test `STORAGE_ENUM_ADAPTER.apply(connection)` then assert all five column types, all enum labels, Blackroom and SSF defaults, and both check names. Insert direct SQL values that violate every scalar enum, `provider_outcomes='[{"provider":"x","status":"partial"}]'::jsonb`, and `event_types='["split"]'::jsonb`; each must raise the database driver’s integrity/data error.

Add tests that an invalid legacy provider JSON row makes `preflight(..., rollback=False)` raise `StorageEnumMigrationError` without creating types; a second `apply` returns `False`; and `rollback` restores exact `varchar` widths, removes checks, and removes all five types.

- [ ] **Step 2: Run Storage migration tests to verify failure**

Run: `uv run pytest test/storage/test_enum_migration.py -q`

Expected: FAIL because the Storage adapter and its migration contracts do not exist.

- [ ] **Step 3: Implement adapter facts, migration, checks, and rollback**

Mirror `monitor/storage/enum_migration.py` for the adapter lifecycle and use only the three governed models. Define a `StorageEnumColumn` with table, column, legacy type, default, and nullability; define one `StorageEnumGroup` per scalar type. Use exact legacy types:

```python
_column("blackroom_records", "market", "VARCHAR(5)", "'A'")
_column("blackroom_records", "source", "VARCHAR(50)", "'manual'")
_column("daily_bar_diagnostics", "adjust", "VARCHAR(10)")
_column("daily_bar_diagnostics", "classification", "VARCHAR(50)")
_column("ssf_change_signals", "status", "VARCHAR(20)", "'signal'")
```

Preflight scalar values with a parameterized `NOT IN :labels` query. Preflight JSON by selecting each JSON document, passing the value to `validate_provider_outcomes` or `validate_ssf_event_types`, and raising `StorageEnumMigrationError` with the table ID and original `ValueError` text. Use explicit `USING column::text::target` casts and type dependency checks before dropping types.

Add checks using JSONB `jsonb_array_elements` and `NOT EXISTS` predicates. The provider check must reject non-arrays, non-object elements, missing/null statuses, and statuses outside `('downloaded', 'empty', 'error')`. The SSF check must reject non-arrays and any entry outside `('increase', 'decrease', 'new_entry', 'exit')`. Implement check-definition normalization and validation following the Monitor adapter so an identically named incompatible constraint fails preflight.

Import `STORAGE_ENUM_ADAPTER` in `storage/enum_governance.py` and append it to `ENUM_GOVERNANCE_ADAPTERS`, preserving Paper Trading then Monitor order.

- [ ] **Step 4: Run migration tests to verify pass**

Run: `uv run pytest test/storage/test_enum_migration.py -q`

Expected: PASS when `TEST_POSTGRESQL_URL` is configured; otherwise tests report skipped because PostgreSQL is unavailable.

- [ ] **Step 5: Commit Storage migration adapter**

```bash
git add storage/enum_migration.py storage/enum_governance.py test/storage/test_enum_migration.py
git commit -m "Migrate storage finite values to enums"
```

### Task 4: Extend Unified Governance Coverage and Run Full Verification

**Files:**
- Modify: `test/storage/test_enum_governance.py:10-18,38-125,274-315`
- Modify: `docs/superpowers/specs/2026-08-08-blackroom-diagnostic-ssf-enum-design.md:76-79`

**Interfaces:**
- Consumes: `STORAGE_ENUM_GROUPS` and `STORAGE_ENUM_ADAPTER` from Task 3.
- Verifies: the public unified command aggregates the Storage adapter after Paper Trading and Monitor, and an invalid Storage preflight prevents every adapter’s DDL in the shared transaction.

- [ ] **Step 1: Write failing unified command tests**

Extend `_create_*_legacy_schema` with the three Storage tables and add:

```python
def test_default_adapters_are_paper_trading_monitor_then_storage() -> None:
    assert tuple(adapter.name for adapter in ENUM_GOVERNANCE_ADAPTERS) == (
        "paper_trading", "monitor", "storage"
    )


def test_atomic_migration_prevents_all_conversion_when_storage_json_is_invalid(postgres_schema) -> None:
    engine, schema = postgres_schema
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.execute(text(
            "INSERT INTO daily_bar_diagnostics "
            "(id, adjust, classification, provider_outcomes) VALUES "
            "(1, 'bfq', 'downloaded', '[{\"status\": \"partial\"}]'::jsonb)"
        ))
        with pytest.raises(EnumGovernanceError, match="storage"):
            migrate_enums(connection)
        assert _column_type(connection, "paper_matching_runs", "status") == "character varying(32)"
        assert _column_type(connection, "stock_monitor_targets", "market") == "character varying(5)"
        assert _column_type(connection, "daily_bar_diagnostics", "adjust") == "character varying(10)"
```

Update `_all_managed_enum_types` to include all `STORAGE_ENUM_GROUPS` type names.

- [ ] **Step 2: Run unified tests to verify failure**

Run: `uv run pytest test/storage/test_enum_governance.py -q`

Expected: FAIL until the Storage adapter is registered and the fixture recognizes the new managed types.

- [ ] **Step 3: Finish unified fixture assertions and correct specification**

Adjust any expected default-adapter tuples and result-domain assertions to include `storage`. Ensure the complete test suite establishes that all adapters preflight before apply, including the new Storage adapter.

Correct the approved design’s migration sentence from “seven named scalar types” to “five named scalar types” because only Blackroom market/source, diagnostic adjustment/classification, and SSF signal status are table-column enums; provider status and event types remain validated JSON values protected by checks.

- [ ] **Step 4: Run focused and project verification**

Run: `uv run pytest test/storage/test_enum_governance.py test/storage/test_enum_migration.py test/storage/test_blackroom_storage_db.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q`

Expected: PASS, with PostgreSQL tests skipped only if `TEST_POSTGRESQL_URL` is absent.

Run: `uv run ruff format --check storage paper_trading test && uv run ruff check storage paper_trading test && uv run mypy`

Expected: PASS.

Run: `uv run pytest test`

Expected: PASS, with the repository’s optional PostgreSQL integration tests skipped when no integration URL is configured.

- [ ] **Step 5: Commit unified coverage and spec correction**

```bash
git add test/storage/test_enum_governance.py docs/superpowers/specs/2026-08-08-blackroom-diagnostic-ssf-enum-design.md
git commit -m "Verify storage enum governance"
```

## Plan Self-Review

**Spec coverage:** Task 1 covers the canonical `StrEnum` contracts and value-persisting scalar mappings. Task 2 covers SQLite/application validation and regression behavior. Task 3 covers the dedicated adapter, PostgreSQL type conversion, JSON checks, direct-SQL rejection, idempotence, and rollback. Task 4 covers unified adapter ordering, atomic preflight behavior, the specification correction, lint/type checks, and the full suite.

**Placeholder scan:** The document contains no unfilled work markers, deferred implementation phrases, or unspecified test steps. Every task names exact files, public interfaces, commands, expected outcomes, and commit paths.

**Type consistency:** `storage.domain_enums` is introduced before all consumers. `STORAGE_ENUM_GROUPS`, `STORAGE_ENUM_ADAPTER`, and `StorageEnumMigrationError` are created in Task 3 before Task 4 imports them. Both JSON validators accept `object`, return normalized collections, and raise `ValueError`, matching the repository and StorageDb call sites.
