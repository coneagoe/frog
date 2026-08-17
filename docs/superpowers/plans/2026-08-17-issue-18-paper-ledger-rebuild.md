# Issue 18 Paper Ledger Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an atomic, account-scoped paper-trading ledger rebuild from a requested historical trade date.

**Architecture:** Add a dedicated ledger rebuild service that preserves source facts, purges only derived rows from the requested start date, and replays eligible orders through existing matching coordination. Extend the existing ledger rebuild audit table instead of duplicating derived ledger rows.

**Tech Stack:** Python 3.11+, SQLAlchemy models/repository, FastAPI routers, repo-local paper trading CLI, pytest, Ruff, mypy.

## Global Constraints

- Use `uv run` for Python commands; do not use bare `python` or `python3`.
- Preserve source facts: original orders, manual cancellations, deposits, withdrawals, manual cash adjustments, historical matching runs, and historical validity checks.
- Recreate only derived ledger state from the selected start date: trades, trade-generated cash events, positions, lots, round trips, snapshots, valuation gaps, and matching outcomes.
- Replay non-cancelled orders in `(trade_date, id)` order.
- Replay must keep current matching semantics: suspended symbols rejected, limit prices outside daily range accepted as unmatched, missing exact-date data accepted with unresolved daily-bar diagnostic.
- Use existing matching coordination (`acquire_matching_run`) for rebuild replay runs.
- Unexpected application or persistence failure must rollback the rebuild with no partial account ledger, then record a lightweight failed audit entry separately.
- Follow TDD: write failing tests, verify red, implement minimal green, verify green.
- Do not change unrelated DAG schedules, dependencies, retries, task boundaries, or SLA.

---

### Task 1: Audit and Repository Foundation

**Files:**
- Modify: `paper_trading/domain/enums.py`
- Modify: `storage/model/paper_trading.py`
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/storage/enum_migration.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/paper_trading/storage/test_enum_migration.py`
- Test: `test/storage/test_enum_governance.py`

**Interfaces:**
- Produces: `LedgerRebuildStatus.RUNNING`, `COMPLETED`, `FAILED`.
- Produces repository helpers for started/completed/failed ledger rebuild audits.
- Produces a repository primitive to purge derived ledger rows for one account from `start_date` without deleting source facts.

- [ ] Write failing repository and enum tests for audit statuses/columns and source-fact preservation.
- [ ] Run focused tests and confirm expected failures.
- [ ] Add enum labels and model columns: trigger evidence JSON, record counts JSON, finished timestamp, error detail.
- [ ] Add repository audit helpers and date-scoped purge/reset helpers.
- [ ] Run focused tests until green.

### Task 2: Ledger Rebuild Service

**Files:**
- Create: `paper_trading/services/ledger_rebuild_service.py`
- Modify as needed: `paper_trading/services/order_delete_service.py`
- Test: `test/paper_trading/services/test_ledger_rebuild_service.py`

**Interfaces:**
- Consumes Task 1 audit and purge primitives.
- Produces `LedgerRebuildService.rebuild_account_from(account_id: int, start_date: date, trigger_evidence: dict | None = None)` returning the persisted audit record.

- [ ] Write failing service tests for preserving source facts, purging/recreating derived rows, replay order, existing matching semantics, and rollback/failure audit.
- [ ] Run focused service tests and confirm expected failures.
- [ ] Implement service with one transaction for ledger mutations and separate failed-audit persistence after rollback.
- [ ] Replay orders by date/id through existing matching coordination.
- [ ] Run focused service tests until green.

### Task 3: API, CLI, and Existing Rebuild Routing

**Files:**
- Modify: `paper_trading/api/routers/` relevant account or matching router
- Modify: `tools/paper_trading_cli.py`
- Modify as needed: `paper_trading/services/order_delete_service.py`
- Test: `test/paper_trading/api/test_ledger_rebuild_api.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Interfaces:**
- Consumes `LedgerRebuildService.rebuild_account_from(...)`.
- Produces API endpoint `POST /paper/accounts/{account_id}/ledger-rebuilds` accepting `start_date` and optional trigger evidence.
- Produces CLI command `account rebuild_ledger --account-id ID --start-date YYYY-MM-DD --trigger-evidence TEXT`.

- [ ] Write failing API and CLI tests for success and request routing.
- [ ] Run focused API/CLI tests and confirm expected failures.
- [ ] Wire FastAPI endpoint and CLI command.
- [ ] Route delayed-data rebuild usage through the new service if currently using broad direct rebuild logic.
- [ ] Run focused API/CLI tests until green.

### Task 4: Verification, Simplify Review, and Docs

**Files:**
- Modify affected docs only if public CLI/API behavior changes require it.

**Interfaces:**
- Consumes complete implementation from Tasks 1-3.

- [ ] Run focused verification:
  - `uv run pytest test/paper_trading/services/test_ledger_rebuild_service.py -v`
  - `uv run pytest test/paper_trading/storage/test_repository.py -v`
  - `uv run pytest test/paper_trading/api/test_ledger_rebuild_api.py -v`
  - `uv run pytest test/tools/test_paper_trading_cli.py -v`
  - `uv run pytest test/paper_trading/storage/test_enum_migration.py test/storage/test_enum_governance.py -v`
- [ ] Run `uv run ruff check .` and `uv run mypy`.
- [ ] Run `tools/run_tests.sh test/storage/test_storage_enum_migration.py -v` if enum migration behavior touches PostgreSQL integration.
- [ ] Invoke simplify review before completion and apply only targeted simplifications.
- [ ] Report any blocked full-suite or PostgreSQL-dependent checks clearly.
