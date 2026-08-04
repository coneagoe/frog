# Paper Position Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove fully closed paper positions from active holdings while preserving cumulative realized PnL and safely cleaning legacy rows.

**Architecture:** `PaperAccount` becomes the durable owner of cumulative realized PnL. Sell settlement updates that value and later removes an eligible closed `PaperPosition` after recording its round trip. New snapshots read the account total. A temporary command backfills deployed data before removing old closed aggregate rows.

**Tech Stack:** Python 3.11+, SQLAlchemy, FastAPI, pytest, Ruff, uv.

## Global Constraints

- Use `uv run` for all Python commands.
- `PaperPosition` is an active-holding aggregate; do not delete lots, orders, trades, round trips, ledger entries, pending settlements, or snapshots.
- Delete a position only when `total_quantity <= 0` and `frozen_quantity == 0`.
- Record the sell fill in the round-trip service before deleting a closed position.
- Historical snapshots must not be rewritten.
- The temporary cleanup command must validate all deletion candidates before mutation and execute its writes atomically.
- Do not add a frontend-only zero-position filter; the existing positions API/UI flow consumes active rows only.

---

### Task 1: Persist Account Cumulative Realized PnL

**Files:**
- Modify: `storage/model/paper_trading.py`
- Modify: `storage/storage_db.py`
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/services/matching_service.py`
- Modify: `paper_trading/services/snapshot_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`

**Interfaces:**
- Produces: `PaperAccount.realized_pnl: Decimal` and a repository operation that increments it in the caller transaction.
- Consumes: existing FIFO `cost_reduction` and existing sell fee calculation.

- [ ] **Step 1: Write failing matching and snapshot tests**

```python
assert repo.get_account(account.id).realized_pnl == Decimal("44.4900")
assert snapshot.realized_pnl == Decimal("44.4900")
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -q`
Expected: FAIL because `PaperAccount` has no cumulative realized-PnL value and snapshots sum only position rows.

- [ ] **Step 3: Implement the smallest complete account-level PnL path**

```python
class PaperAccount(Base):
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, server_default=text("0"))

def add_account_realized_pnl(self, account: PaperAccount, amount: Decimal) -> PaperAccount:
    account.realized_pnl = (Decimal(account.realized_pnl or 0) + amount).quantize(Decimal("0.0001"))
    self.session.flush()
    return account
```

Add the deployed-schema column with default `0`, use the same sell PnL expression already assigned to the position, and make future snapshots read the account field.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -q`
Expected: PASS.

### Task 2: Remove Closed Aggregate Positions

**Files:**
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/services/matching_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/api/test_accounts_api.py`
- Test: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`

**Interfaces:**
- Consumes: account-level cumulative PnL from Task 1.
- Produces: a repository operation that deletes an explicitly supplied eligible `PaperPosition`.

- [ ] **Step 1: Write failing lifecycle and API/UI tests**

```python
assert repo.get_position(account.id, "000001.SZ") is None
assert response.json() == []
```

Use a partial sale control case that retains the row, a full-sale case that closes the round trip then removes the row, and a later buy case that recreates it.

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_accounts_api.py -q`
Expected: FAIL because full sales leave the zero-quantity aggregate row stored and returned.

- [ ] **Step 3: Implement closed-position deletion after round-trip recording**

```python
def delete_position(self, position: PaperPosition) -> None:
    self.session.delete(position)
    self.session.flush()
```

After sell settlement has reduced cost and quantity, let the fill record its post-sell quantity in the round-trip service, then delete only an unfrozen zero/negative aggregate. Reuse the existing buy upsert behavior for later purchases.

- [ ] **Step 4: Run focused backend and frontend tests to verify they pass**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_accounts_api.py -q && npm --prefix frontend/paper-trading test -- --run features/accounts/accounts-page.test.tsx`
Expected: PASS.

### Task 3: Clean Up Legacy Closed Positions

**Files:**
- Create: `tools/cleanup_zero_paper_positions.py`
- Test: `test/tools/test_cleanup_zero_paper_positions.py`

**Interfaces:**
- Consumes: durable account `realized_pnl` from Task 1 and existing SQLAlchemy models.
- Produces: a command that returns non-zero without writes for frozen deletion candidates and otherwise reports account/position counts after an atomic cleanup.

- [ ] **Step 1: Write failing command tests for success and frozen preflight rejection**

```python
assert account.realized_pnl == Decimal("75.0000")
assert repo.get_position(account.id, "000001") is None
assert result.exit_code != 0
assert account.realized_pnl == Decimal("0.0000")
```

- [ ] **Step 2: Run the command tests to verify they fail**

Run: `uv run pytest test/tools/test_cleanup_zero_paper_positions.py -q`
Expected: FAIL because no cleanup command exists.

- [ ] **Step 3: Implement the disposable operational command**

The command must load configuration with the repository bootstrap, query all zero/negative aggregate positions, reject the entire run before writes when any candidate has non-zero frozen quantity, set every account total from the sum of all current aggregate-position PnL, delete eligible rows in one transaction, and print affected account and position counts.

- [ ] **Step 4: Run cleanup tests to verify they pass**

Run: `uv run pytest test/tools/test_cleanup_zero_paper_positions.py -q`
Expected: PASS.

### Task 4: Full Verification

**Files:**
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`
- Test: `test/paper_trading/api/test_accounts_api.py`
- Test: `test/tools/test_cleanup_zero_paper_positions.py`

- [ ] **Step 1: Format and lint touched Python files**

Run: `uv run ruff format storage/model/paper_trading.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/services/matching_service.py paper_trading/services/snapshot_service.py tools/cleanup_zero_paper_positions.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/api/test_accounts_api.py test/tools/test_cleanup_zero_paper_positions.py && uv run ruff check storage/model/paper_trading.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/services/matching_service.py paper_trading/services/snapshot_service.py tools/cleanup_zero_paper_positions.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/api/test_accounts_api.py test/tools/test_cleanup_zero_paper_positions.py`
Expected: PASS.

- [ ] **Step 2: Run the targeted Python suite and frontend Accounts test**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/api/test_accounts_api.py test/tools/test_cleanup_zero_paper_positions.py && npm --prefix frontend/paper-trading test -- --run features/accounts/accounts-page.test.tsx`
Expected: PASS.
