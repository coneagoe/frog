# Paper Trading Historical Replay Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make historical paper-account replay preserve source facts, regenerate one coherent derived ledger, coordinate with account matching, and prove order #33 behavior.

**Architecture:** Keep the existing full-account replay in `OrderDeleteService.rebuild_account_from` as the single reconstruction path. Add a repository-level account row lock shared by replay and account-scoped matching, then validate behavior through service tests that inspect persisted orders, cash, trades, positions, lots, round trips, snapshots, diagnostics, and matching runs.

**Tech Stack:** Python 3.11+, SQLAlchemy, PostgreSQL/SQLite test fixtures, pytest, Ruff, mypy, uv.

## Global Constraints

- Use `uv run` for all Python and test commands.
- Preserve existing order matching, fee, lot-size, suspension, limit-price, and A-share T+1 semantics.
- Preserve source facts and historical execution records; rebuild only the current derived ledger.
- Replay accepted orders in ascending `(trade_date, order_id)` order.
- Expected business outcomes do not abort replay; unexpected exceptions roll back the complete transaction.
- Do not introduce a process-local lock; coordination must work across workers through the database.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLA.

---

### Task 1: Add Account-Level Replay Coordination

**Files:**
- Modify: `paper_trading/storage/repository.py` near account accessors and matching queries
- Modify: `paper_trading/services/matching_service.py` in the account-scoped run entrypoint
- Modify: `paper_trading/services/order_delete_service.py` at `rebuild_account_from`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_order_delete_service.py`

**Interfaces:**
- Produce `PaperTradingRepository.lock_account(account_id: int) -> PaperTradingAccount` (using the repository's account model and `with_for_update()` on the current transaction).
- Consume the lock in `MatchingService.run(trade_date, account_id)` when `account_id` is not `None`.
- Consume the same lock at the beginning of `OrderDeleteService.rebuild_account_from` and hold it through audit-row creation.

- [ ] **Step 1: Write the failing same-account coordination test**

Add a repository/service test that starts an account-scoped replay seam while the account row is locked, then verifies the matching path cannot enter the same account until the transaction releases the lock. Add a separate test showing two different account IDs do not share the coordination key or lock path. Keep the test at the repository/service boundary; do not assert private helper calls.

- [ ] **Step 2: Run the focused tests and verify the new test fails**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py -k "account_lock or coordination or concurrent"`

Expected: the new coordination assertion fails because replay and matching do not yet acquire a shared account lock.

- [ ] **Step 3: Implement the repository account lock**

Add `lock_account` next to `get_account`. Load the account by primary key with `with_for_update()` and raise the repository's existing account-not-found error when absent. Do not create a lock table or use a Python mutex.

- [ ] **Step 4: Integrate the lock into matching and replay**

In the account-scoped `MatchingService.run`, acquire the account lock before selecting or mutating orders, reservations, positions, and cash. In `rebuild_account_from`, acquire it before `clear_account_rebuild_state` and keep the same transaction/nested transaction active until `create_ledger_rebuild` returns.

- [ ] **Step 5: Run the focused coordination tests**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py -k "account_lock or coordination or concurrent"`

Expected: all coordination tests pass, including independent-account behavior.

- [ ] **Step 6: Run the existing matching and rebuild tests**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_delete_service.py`

Expected: all existing tests pass without changing the established matching-run ownership behavior.

### Task 2: Prove Full-Replay Integrity and Business-Outcome Isolation

**Files:**
- Modify: `paper_trading/storage/repository.py` in `clear_account_rebuild_state` and derived-row helpers only if failing tests expose a real duplication issue
- Modify: `paper_trading/services/order_delete_service.py` only where replay state handling is needed
- Test: `test/paper_trading/services/test_order_delete_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py` if valuation-gap assertions need the existing snapshot seam

**Interfaces:**
- Preserve `OrderDeleteService.rebuild_account_from(account_id: int, start_date: date, triggering_order_ids: list[int])` return type and audit behavior.
- Continue using repository upsert methods for snapshots and valuation gaps; do not add a second ledger writer.

- [ ] **Step 1: Add the failing repeated-rebuild integrity test**

Create an account with an early buy and later sell, a manual deposit, a comment, and a cancelled order. Run `rebuild_account_from` twice. Assert source orders and manual cash rows remain, cancelled status remains cancelled, and the current counts contain exactly one trade per filled order, one current lot per buy fill, one round trip per completed cycle, one snapshot per date, and no duplicate derived cash event for an order.

- [ ] **Step 2: Run the integrity test and confirm failure**

Run: `uv run pytest test/paper_trading/services/test_order_delete_service.py -k "repeated_rebuild or integrity or duplicate"`

Expected: the test exposes whichever derived row or source-fact behavior is currently not idempotent. Record the exact failing count before editing implementation.

- [ ] **Step 3: Add the failing outcome-isolation test**

Seed same-account orders covering a missing exact-date bar, an untouched limit, and a suspended symbol alongside a fillable order on a later date. Run the rebuild and assert the expected order-level statuses/diagnostics while the independent fill and its downstream snapshot still exist.

- [ ] **Step 4: Run the outcome-isolation test and confirm failure**

Run: `uv run pytest test/paper_trading/services/test_order_delete_service.py -k "missing or untouched or suspended or independent"`

Expected: the test fails only for an unsupported status/diagnostic or for replay aborting unrelated work; do not weaken existing matching rules to make it pass.

- [ ] **Step 5: Implement the smallest derived-state fix**

Use the existing clear/reset/replay/upsert seams to remove only the duplication or preservation defect demonstrated by the tests. Keep manual cash event types outside the derived deletion set, keep cancelled/rejected orders outside replay reset, and keep valuation-gap resolution tied to the existing exact-date bar behavior. Do not change `start_date` into an incremental boundary.

- [ ] **Step 6: Run the focused integrity and outcome tests**

Run: `uv run pytest test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_snapshot_service.py -k "rebuild or missing or untouched or suspended or duplicate or integrity"`

Expected: all new and existing integrity tests pass.

### Task 3: Strengthen Order #33 and Historical Inventory Regression Coverage

**Files:**
- Modify: `test/paper_trading/services/test_order_service.py` around existing historical order #33 tests
- Modify: `test/paper_trading/services/test_order_delete_service.py` if the complementary replay assertion belongs at the rebuild seam

**Interfaces:**
- Exercise `OrderService.place_order` and `OrderDeleteService.rebuild_account_from` as public service seams.
- Assert `PaperOrder.status`, `rejection_code`, `PaperTrade`, `PaperPosition`, and position lots through repository reads.

- [ ] **Step 1: Add the failing complementary order #33 test**

Use the existing 2026-07-30 `002558` bar and historical date fixture, but provide either no prior position or only same-day 1,100 shares. Place the sell after the historical date and assert the final result is `INSUFFICIENT_POSITION` or `A_SHARE_T1_VIOLATION` according to the seeded ledger, and explicitly assert it is not `HISTORICAL_TRADE_DATE_NOT_ELIGIBLE`.

- [ ] **Step 2: Run both order #33 tests**

Run: `uv run pytest test/paper_trading/services/test_order_service.py -k "order_33 or historical.*sell"`

Expected: the existing fill test passes and the new historical-inventory test initially fails if replay reservation handling still emits the wrong result.

- [ ] **Step 3: Fix only the historical replay rejection mapping**

Ensure replay reservation checks report the applicable inventory or T+1 code and retain the replay marker, while historical-date eligibility is never consulted after the order is accepted. Preserve current-date sell reservation behavior.

- [ ] **Step 4: Run the complete historical order service tests**

Run: `uv run pytest test/paper_trading/services/test_order_service.py`

Expected: all historical buy, sell, idempotency, current-date reservation, and market-specific tests pass.

### Task 4: Verify and Close the Issue

**Files:**
- Modify: `docs/paper_trading.md` only if the implemented behavior changes documented user-visible semantics
- Modify: GitHub Issue #23 through `gh` only after all verification passes

- [ ] **Step 1: Run the full paper-trading test suite**

Run: `uv run pytest test/paper_trading`

Expected: exit code 0 with zero failures.

- [ ] **Step 2: Run repository quality gates**

Run: `uv run ruff format --check .`, `uv run ruff check .`, and `uv run mypy`

Expected: all commands exit 0. Fix only issues caused by the implementation.

- [ ] **Step 3: Inspect the final diff and workspace**

Run: `git diff --check`, `git diff -- paper_trading test/paper_trading docs/paper_trading.md docs/superpowers/specs/2026-08-05-paper-trading-replay-integrity-design.md docs/superpowers/plans/2026-08-05-paper-trading-replay-integrity.md`, and `git status --short`.

Expected: only intended files are changed; unrelated untracked `data/` remains untouched.

- [ ] **Step 4: Update Issue #23 with evidence**

Comment the issue with the test and quality-gate commands plus their results, check off the acceptance items that are directly evidenced, and leave the issue open if any acceptance item lacks evidence.

- [ ] **Step 5: Close Issue #23 only after all acceptance items are evidenced**

Run: `gh issue close 23 --comment "Implemented and verified historical replay integrity, account coordination, source-fact preservation, rollback, outcome isolation, and order #33 regression. Focused and full paper-trading tests plus quality gates pass."`

Expected: GitHub reports Issue #23 closed and its final state is `CLOSED`.
