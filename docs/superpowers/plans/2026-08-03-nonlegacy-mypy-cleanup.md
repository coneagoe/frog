# Non-Legacy Mypy Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `uv run mypy` check the active non-legacy codebase with zero errors while preserving ORM and runtime behavior.

**Architecture:** Configure mypy with explicit active package targets, excluding repository runtime artifacts and retaining existing legacy-module exemptions. Modernize the shared paper-trading ORM mappings first so model instances expose domain values rather than SQLAlchemy `Column` descriptors, then resolve the remaining independent active-module annotations revealed by that root-cause fix.

**Tech Stack:** Python 3.12, mypy 1.18, SQLAlchemy 2.x, pytest, Ruff.

## Global Constraints

- Preserve existing `ignore_errors` overrides for `app.*`, `stock.*`, `fund.*`, `tools.*`, and `backtest.deprecate.*`.
- Do not add new first-party `ignore_errors` overrides, blanket `type: ignore` directives, or mass casts.
- Do not change table names, column names, SQL types, nullability, defaults, indexes, foreign keys, unique constraints, relationships, or query behavior.
- Use `uv run` for Python commands.
- Keep third-party missing-import handling only where dependency stubs are unavailable.
- Ensure `uv run mypy` exits successfully with no errors for its configured active scope.

---

### Task 1: Define the Default Active Mypy Scope

**Files:**
- Modify: `pyproject.toml:75-153`
- Test: `test/tools/test_packaging_metadata.py`

**Interfaces:**
- Consumes: repository package layout and current per-module mypy overrides.
- Produces: a no-argument `uv run mypy` command that checks only active source packages.

- [ ] **Step 1: Write the failing configuration test**

```python
def test_mypy_config_has_explicit_active_source_targets():
    config = tomllib.loads(Path("pyproject.toml").read_text())
    assert config["tool"]["mypy"]["files"] == [
        "celery_app.py", "common", "conf", "dags", "download", "factor",
        "monitor", "ocr", "paper_trading", "storage", "task",
        "top10_floatholder", "utility",
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/tools/test_packaging_metadata.py::test_mypy_config_has_explicit_active_source_targets -v`

Expected: FAIL because `[tool.mypy]` has no `files` entry.

- [ ] **Step 3: Configure active package targets**

```toml
[tool.mypy]
files = [
    "celery_app.py", "common", "conf", "dags", "download", "factor",
    "monitor", "ocr", "paper_trading", "storage", "task",
    "top10_floatholder", "utility",
]
```

Keep all existing legacy overrides unchanged. Do not include `.slim`, `.worktrees`, `.venv`, test fixtures, frontend code, generated runtime files, or excluded legacy package roots.

- [ ] **Step 4: Run the configuration test and inspect mypy discovery**

Run: `uv run pytest test/tools/test_packaging_metadata.py::test_mypy_config_has_explicit_active_source_targets -v && uv run mypy`

Expected: the test PASSes; mypy reports source type errors instead of `Missing target module, package, files, or command`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml test/tools/test_packaging_metadata.py
git commit -m "Configure active mypy targets"
```

### Task 2: Type Paper Trading ORM Models

**Files:**
- Modify: `storage/model/paper_trading.py`
- Test: `test/paper_trading/storage/test_models.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Consumes: SQLAlchemy declarative `Base` and all existing paper-trading table constants.
- Produces: model attributes typed as runtime domain values, including `int`, `str`, `Decimal`, `date`, `datetime`, `bool`, `dict[str, Any]`, and nullable variants.

- [ ] **Step 1: Add an ORM instance-type regression test**

```python
def test_paper_order_round_trips_nullable_and_non_nullable_values(session):
    order = PaperOrder(
        account_id=1,
        symbol="000001",
        side="buy",
        quantity=100,
        limit_price=Decimal("10.00"),
        trade_date=date(2026, 6, 16),
        status="accepted",
    )
    session.add(order)
    session.flush()
    assert order.quantity == 100
    assert order.rejection_code is None
```

- [ ] **Step 2: Run the test and capture current mypy errors**

Run: `uv run pytest test/paper_trading/storage/test_models.py -v && uv run mypy storage/model/paper_trading.py paper_trading`

Expected: model persistence tests PASS; mypy reports `Column[...]` values flowing into paper-trading services.

- [ ] **Step 3: Migrate model declarations without changing schema options**

```python
from sqlalchemy.orm import Mapped, mapped_column

class PaperOrder(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    rejection_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

Convert every paper-trading model attribute. Preserve every existing `Column(...)` argument inside `mapped_column(...)`, including table constants, `ForeignKey`, `server_default`, `onupdate`, `index`, `unique`, and `nullable`. Type JSON fields with their actual persisted shape and use typed relationships where present.

- [ ] **Step 4: Run persistence and paper-trading tests**

Run: `uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/paper_trading/services -v`

Expected: PASS.

- [ ] **Step 5: Run the narrowed type check**

Run: `uv run mypy storage/model/paper_trading.py paper_trading`

Expected: no `Column[...]` instance-value errors remain; any residual errors identify concrete repository, protocol, or service signatures for Tasks 3 and 4.

- [ ] **Step 6: Commit**

```bash
git add storage/model/paper_trading.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py
git commit -m "Type paper trading ORM models"
```

### Task 3: Resolve Paper Trading Service and Repository Contracts

**Files:**
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/storage/security_metadata.py`
- Modify: `paper_trading/services/analytics_service.py`
- Modify: `paper_trading/services/cash_service.py`
- Modify: `paper_trading/services/hk_settlement_service.py`
- Modify: `paper_trading/services/matching_service.py`
- Modify: `paper_trading/services/order_delete_service.py`
- Modify: `paper_trading/services/order_service.py`
- Modify: `paper_trading/services/round_trip_service.py`
- Modify: `paper_trading/services/snapshot_service.py`
- Modify: `paper_trading/services/trade_validity_service.py`
- Modify: `paper_trading/api/routers/accounts.py`
- Modify: `paper_trading/api/routers/matching.py`
- Test: `test/paper_trading/services/`
- Test: `test/paper_trading/api/`

**Interfaces:**
- Consumes: typed paper-trading ORM instances from Task 2.
- Produces: accurately typed repository methods, market-data providers, service results, and API response enrichment.

- [ ] **Step 1: Capture the first remaining type error per paper-trading file**

Run: `uv run mypy paper_trading`

Expected: errors are concrete contract mismatches, not ORM instance `Column[...]` cascades.

- [ ] **Step 2: Add a focused behavior test for each corrected contract**

```python
def test_security_metadata_returns_symbol_and_name_strings(sqlite_session):
    provider = SecurityMetadataProvider(sqlite_session)
    assert provider.resolve_names(["000001"]) == {"000001": "Ping An Bank"}
```

Keep existing behavior assertions as the test authority for repository updates, matching outcomes, cash events, snapshot values, and API response shapes.

- [ ] **Step 3: Correct contracts at their definitions**

```python
def resolve_names(self, securities: Iterable[str]) -> dict[str, str]:
    ...

def get_order(self, order_id: int) -> PaperOrder:
    ...
```

Use typed collection values, explicit optional returns, and protocol-compatible provider methods. Remove redundant casts only when the typed ORM migration makes them unnecessary. Do not change matching, settlement, fees, T+1, replay, or API behavior.

- [ ] **Step 4: Run paper-trading behavior tests**

Run: `uv run pytest test/paper_trading/api test/paper_trading/services test/paper_trading/storage -v`

Expected: PASS.

- [ ] **Step 5: Run paper-trading mypy**

Run: `uv run mypy paper_trading storage/model/paper_trading.py`

Expected: PASS with zero errors.

- [ ] **Step 6: Commit**

```bash
git add paper_trading storage/model/paper_trading.py test/paper_trading
git commit -m "Fix paper trading type contracts"
```

### Task 4: Resolve Shared Storage Type Contracts

**Files:**
- Modify: `storage/storage_db.py`
- Modify: affected files under `storage/model/`
- Test: `test/storage/model/`
- Test: `test/storage/test_storage_db.py`

**Interfaces:**
- Consumes: existing storage declarative base and PostgreSQL/SQLite upsert paths.
- Produces: consistent types for storage model instances and database-dialect insert construction.

- [ ] **Step 1: Capture storage-only mypy errors after Task 3**

Run: `uv run mypy storage`

Expected: errors are limited to remaining active storage model mappings and dialect-dependent insert variable inference.

- [ ] **Step 2: Add focused storage behavior tests where absent**

```python
def test_storage_upsert_uses_the_runtime_dialect(session):
    # Exercise the existing SQLite upsert path and assert its persisted result.
    ...
```

Use existing storage tests when they already cover the affected query; add a test only if a corrected type boundary has no behavior coverage.

- [ ] **Step 3: Type remaining model fields and dialect union values**

```python
from sqlalchemy.dialects.postgresql import Insert as PostgreSQLInsert
from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert

insert_stmt: PostgreSQLInsert | SQLiteInsert
```

Preserve current dialect selection and SQL statement behavior. Use `Mapped[...]` only for models whose instance fields are checked by active code; keep schema options identical.

- [ ] **Step 4: Run storage tests and type checks**

Run: `uv run pytest test/storage/model test/storage/test_storage_db.py -v && uv run mypy storage`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add storage test/storage
git commit -m "Fix shared storage type contracts"
```

### Task 5: Resolve Independent Active Module Errors

**Files:**
- Modify: `celery_app.py`
- Modify: affected files under `dags/`
- Modify: `download/dl/downloader_yfinance.py`
- Modify: affected files under `factor/`
- Modify: affected files under `task/`
- Test: corresponding tests under `test/dags/`, `test/download/`, `test/factor/`, and `test/task/`

**Interfaces:**
- Consumes: active module public functions and existing Celery, DAG, provider, and factor contracts.
- Produces: accurate annotations for the final independent errors outside storage and paper trading.

- [ ] **Step 1: Record the remaining file/error inventory**

Run: `uv run mypy`

Expected: only independent active-module errors in Celery setup, DAG task callables, yfinance downloader handling, factor helpers, and task entrypoints remain.

- [ ] **Step 2: Add or identify behavior coverage per error cluster**

```python
def test_download_yfinance_returns_none_when_provider_has_no_history(monkeypatch):
    assert download_history("000001") is None
```

Use the owning module's existing tests. Add a regression only when a new union, optional return, or callable annotation represents behavior not already asserted.

- [ ] **Step 3: Apply narrow annotations and control-flow narrowing**

```python
result: DataFrame | None = fetch_history(...)
if result is None:
    return None
```

Correct signatures at the provider, callback, or task boundary. Do not change DAG schedules, retries, dependencies, task boundaries, provider selection, or execution semantics.

- [ ] **Step 4: Run owning subsystem tests**

Run: `uv run pytest test/dags test/download test/factor test/task -v`

Expected: PASS.

- [ ] **Step 5: Run mypy**

Run: `uv run mypy`

Expected: zero errors in the configured active scope.

- [ ] **Step 6: Commit**

```bash
git add celery_app.py dags download/dl/downloader_yfinance.py factor task test/dags test/download test/factor test/task
git commit -m "Type active runtime modules"
```

### Task 6: Final Type and Runtime Verification

**Files:**
- Modify: only files required to correct verified failures from this task.

**Interfaces:**
- Consumes: all prior typed active modules.
- Produces: a stable, documented zero-error mypy gate.

- [ ] **Step 1: Run style checks**

Run: `uv run ruff format --check . && uv run ruff check .`

Expected: PASS.

- [ ] **Step 2: Run the default type check**

Run: `uv run mypy`

Expected: PASS with zero errors and no unused configuration warnings.

- [ ] **Step 3: Run the complete test suite**

Run: `uv run pytest test`

Expected: PASS; distinguish any unrelated pre-existing environment failure if one occurs.

- [ ] **Step 4: Inspect the final diff**

Run: `git diff --check && git diff --stat && git status --short`

Expected: no whitespace errors, unchanged legacy exemptions, and only intentional type/config/test/documentation changes.

- [ ] **Step 5: Commit verification fixes if any**

```bash
git add <verified-files>
git commit -m "Verify active mypy cleanup"
git commit -m "Verify active mypy cleanup"
```
