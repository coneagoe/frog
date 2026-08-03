# Airflow SQLAlchemy ORM Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Airflow 2.9.2's SQLAlchemy 1.4 runtime to parse DAGs that import the repository's typed ORM models.

**Architecture:** Keep the repository's SQLAlchemy 2.x dependency unchanged. Add a local ORM compatibility boundary that uses native `mapped_column` on SQLAlchemy 2.x and `Column` on SQLAlchemy 1.4, then route the three affected model modules through it.

**Tech Stack:** Python 3.11+, SQLAlchemy 1.4/2.x, pytest, Ruff, Airflow 2.9.2.

## Global Constraints

- Do not force a SQLAlchemy version into the Airflow image.
- Preserve existing model call sites and column definitions.
- Use `uv run` for Python and pytest commands.
- Keep changes limited to the compatibility helper, affected imports, regression coverage, and design/plan documentation.

---

### Task 1: Add ORM Compatibility Regression Coverage

**Files:**
- Create: `test/storage/model/test_orm_compat.py`
- Test: `test/storage/model/test_orm_compat.py`

**Interfaces:**
- Consumes: `storage.model.orm_compat` with `Mapped` and `mapped_column` exports.
- Produces: A regression test demonstrating the SQLAlchemy 1.4 fallback contract.

- [ ] **Step 1: Write the failing test**

Add a test that imports the helper and asserts its fallback factory can be
used to create a SQLAlchemy `Column` when `mapped_column` is absent from the
ORM namespace. The test must fail before the helper exists because the import
path does not exist.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `uv run pytest test/storage/model/test_orm_compat.py -q`

Expected: collection fails because `storage.model.orm_compat` does not exist.

### Task 2: Implement the Compatibility Boundary

**Files:**
- Create: `storage/model/orm_compat.py`
- Modify: `storage/model/blackroom_record.py:4`
- Modify: `storage/model/stock_monitor_target.py:5`
- Modify: `storage/model/paper_trading.py:20`

**Interfaces:**
- Consumes: SQLAlchemy's `Mapped`, `mapped_column`, and `Column` symbols.
- Produces: `Mapped` and `mapped_column` from `storage.model.orm_compat`.

- [ ] **Step 1: Implement the minimal fallback**

Use a guarded import for SQLAlchemy 2.x's `mapped_column`; on

- [ ] **Step 2: Run the focused test to verify it passes**

Run: `uv run pytest test/storage/model/test_orm_compat.py -q`

Expected: the fallback test passes under the repository's SQLAlchemy 2.x
environment, and the imported model modules remain constructible.

### Task 3: Verify DAG Import and Existing Storage Behavior

**Files:**
- No additional files.

- [ ] **Step 1: Run focused storage tests**

Run: `uv run pytest test/storage/test_blackroom_storage_db.py test/monitor/test_blackroom_service.py test/monitor/test_blackroom_management_service.py test/monitor/test_blackroom_countdown.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Run static checks for touched Python files**

Run: `uv run ruff check storage/model/orm_compat.py storage/model/blackroom_record.py storage/model/stock_monitor_target.py storage/model/paper_trading.py test/storage/model/test_orm_compat.py`

Expected: no Ruff errors.

- [ ] **Step 3: Verify model package import**

Run: `uv run python -c 'import storage.model; print("storage.model import ok")'`

Expected: the command exits successfully.

- [ ] **Step 4: Review the final diff**

Run: `git diff --check && git diff -- storage/model/orm_compat.py storage/model/blackroom_record.py storage/model/stock_monitor_target.py storage/model/paper_trading.py test/storage/model/test_orm_compat.py`

Expected: no whitespace errors and only the scoped compatibility changes.
