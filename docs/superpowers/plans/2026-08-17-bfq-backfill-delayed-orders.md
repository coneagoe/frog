# BFQ Delayed Order Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After successful A-share daily-history downloads, rebuild delayed accepted A-share BFQ orders whose exact-date missing-data diagnostics now have readable BFQ daily bars.

**Architecture:** Reuse the existing `/paper/matching/runs/rebuilds` endpoint and the daily-history DAG hook. The endpoint filters accepted unresolved A-share BFQ `missing_exact_date` diagnostics, probes market data for readable exact-date bars, resolves readable diagnostics, groups by account, and rebuilds once from each account's earliest qualifying trade date. Unexpected rebuild failures propagate through the CLI and DAG so Airflow can retry and expose the failure.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, pytest, Airflow DAG PythonOperator, repo-local CLI via `uv run`.

## Global Constraints

- Use `uv run` for Python commands; do not use bare `python` or `python3`.
- Preserve DAG schedule, dependencies, retries, task boundaries, and SLA.
- Do not introduce new database tables, migrations, or external dependencies.
- Follow TDD: write failing tests first, verify RED, implement minimally, verify GREEN.
- A-share order symbols remain bare six-digit stock codes.
- Rebuild failures must remain visible to Airflow by bubbling out of `run_paper_trading_matching_for_active_accounts`.
- Do not commit changes unless explicitly requested by the user.

---

### Task 1: Repository Eligibility Filter

**Files:**
- Modify: `paper_trading/storage/repository.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Interfaces:**
- Consumes: `PaperTradingRepository.list_eligible_daily_bar_rebuild_orders() -> list[PaperOrder]`
- Produces: An ordered list of accepted A-share BFQ orders with unresolved `missing_exact_date` diagnostics.

- [ ] **Step 1: Write the failing test**

Add/adjust repository tests proving eligible rebuild orders include only accepted A-share BFQ unresolved `missing_exact_date` diagnostics and exclude resolved, non-BFQ, HK, and non-accepted orders.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -k eligible_daily_bar_rebuild_orders -v`

- [ ] **Step 3: Implement minimal repository filter**

Update `list_eligible_daily_bar_rebuild_orders()` to match issue #19's A-share BFQ scope while preserving account/date/id ordering.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -k eligible_daily_bar_rebuild_orders -v`

### Task 2: Rebuild Endpoint Resolution and Grouping

**Files:**
- Modify: `paper_trading/api/routers/matching.py`
- Test: `test/paper_trading/api/test_matching_api.py`

**Interfaces:**
- Consumes: `MarketDataProvider.get_daily_bar(symbol, trade_date, market=...)`
- Produces: `POST /paper/matching/runs/rebuilds` that resolves readable diagnostics and rebuilds each affected account once.

- [ ] **Step 1: Write failing API tests**

Cover: readable BFQ diagnostic resolves even when limit price is not touched; unreadable diagnostics remain unresolved and do not block rebuild; same-account orders rebuild once from the earliest readable date with all readable triggering order IDs.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest test/paper_trading/api/test_matching_api.py -k rebuild -v`

- [ ] **Step 3: Implement endpoint orchestration**

Probe readable bars, mark the exact diagnostic resolved using `upsert_daily_bar_diagnostic(..., resolved=True)`, group readable orders by account, sort each account's orders, and call `OrderDeleteService.rebuild_account_from(account_id, earliest_date, triggering_ids)` once per account.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest test/paper_trading/api/test_matching_api.py -k rebuild -v`

### Task 3: Replay Warning Tolerance and Failure Visibility

**Files:**
- Modify: `paper_trading/services/matching_service.py` if needed
- Modify: `tools/paper_trading_cli.py` if needed
- Modify: `dags/download_stock_history_daily.py` only if needed for bubbling behavior
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/tools/test_paper_trading_cli.py`
- Test: `test/dags/test_partition_dag_sources.py`

**Interfaces:**
- Consumes: `MatchingService.match_order(order)` outcome semantics and CLI rebuild helper.
- Produces: readable diagnostics resolve before price-range skip, unrelated missing bars remain warnings/skips, and rebuild failures surface with useful detail.

- [ ] **Step 1: Write failing tests**

Cover diagnostic resolution before price-range skip if not already covered by endpoint tests, CLI error detail on rebuild 500, and DAG bubbling of rebuild exceptions.

- [ ] **Step 2: Verify RED**

Run focused commands for the added tests, e.g. `uv run pytest test/paper_trading/services/test_matching_service.py -k diagnostic -v`, `uv run pytest test/tools/test_paper_trading_cli.py -k rebuild -v`, and `uv run pytest test/dags/test_partition_dag_sources.py -k paper_trading_matching -v`.

- [ ] **Step 3: Implement minimal changes**

Move/confirm diagnostic resolution happens after a readable bar is fetched and before limit-price range checks; include rebuild endpoint error detail in CLI-raised exceptions; leave DAG exceptions unhandled so Airflow marks the task failed.

- [ ] **Step 4: Verify GREEN**

Run the same focused test commands until green.

### Task 4: Final Verification

**Files:**
- No new production files expected.

**Interfaces:**
- Produces: Verified issue #19 implementation ready for review.

- [ ] **Step 1: Run formatting/lint checks**

Run: `uv run ruff check paper_trading tools dags test/paper_trading test/tools/test_paper_trading_cli.py test/dags/test_partition_dag_sources.py`

- [ ] **Step 2: Run focused test suite**

Run: `uv run pytest test/paper_trading/storage/test_repository.py -k eligible_daily_bar_rebuild_orders -v`, `uv run pytest test/paper_trading/api/test_matching_api.py -k rebuild -v`, `uv run pytest test/paper_trading/services/test_matching_service.py -k diagnostic -v`, `uv run pytest test/tools/test_paper_trading_cli.py -k rebuild -v`, and `uv run pytest test/dags/test_partition_dag_sources.py -k paper_trading_matching -v`.

- [ ] **Step 3: Simplify review**

Use the simplify skill to check whether touched code can be clarified without changing behavior; apply only targeted improvements that preserve verified behavior.

- [ ] **Step 4: Report final state**

Summarize changed files, tests run, and any limitations. Do not claim completion without passing focused verification.

## Self-Review

- Spec coverage: all issue #19 acceptance criteria map to Tasks 1-3; verification maps to Task 4.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: repository, endpoint, CLI, and DAG interfaces match existing code names.
