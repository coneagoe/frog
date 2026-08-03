# Historical Paper Order Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow past-date A-share orders to be recorded and reconstructed against the account state that existed on their trade date.

**Architecture:** Historical A-share orders become source facts without reserving current balances. After acceptance, the existing account ledger replay service clears derived state and replays orders by date and ID, restoring each order's reservation only against the reconstructed historical ledger. Current-date order reservation remains unchanged.

**Tech Stack:** Python 3.12, SQLAlchemy, FastAPI service layer, pytest, Ruff.

## Global Constraints

- Use `uv run` for all Python commands.
- Preserve A-share lot size, T+1, suspension, fee, price-range, cancellation, and manual cash-event semantics.
- Preserve current-date A-share immediate reservation behavior.
- Do not add a direct filled-trade import API or alter HK Connect behavior.
- Tests must use controllable local market-data fakes rather than external providers.

---

### Task 1: Establish Historical Buy Replay Behavior

**Files:**
- Modify: `test/paper_trading/services/test_order_service.py`
- Modify: `paper_trading/services/order_service.py`
- Modify: `paper_trading/services/order_delete_service.py`

**Interfaces:**
- Consumes: `OrderService.place_order(...) -> PaperOrder` and `OrderDeleteService.rebuild_account_from(account_id, start_date, triggering_order_ids)`.
- Produces: accepted historical A-share buy orders that trigger an account rebuild and are evaluated using historical cash.

- [ ] **Step 1: Write the failing test**

```python
def test_place_order_replays_past_a_share_buy_without_current_cash_freeze(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("historical-buy", Decimal("100000.00"))

    order = service.place_order(
        account.id, "000002.SZ", OrderSide.BUY, 100, Decimal("10.00"), date(2026, 6, 16)
    )

    assert order.status == OrderStatus.FILLED.value
    assert repo.get_cash_available(account.id) == Decimal("98993.0000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/paper_trading/services/test_order_service.py::test_place_order_replays_past_a_share_buy_without_current_cash_freeze -v`

Expected: FAIL because past A-share orders are rejected with `HISTORICAL_TRADE_DATE_NOT_ELIGIBLE`.

- [ ] **Step 3: Write minimal implementation**

```python
if trade_date < date.today():
    order = self._create_historical_a_share_order(...)
    OrderDeleteService(self.repo, self.market_data, self.hk_metadata).rebuild_account_from(
        account_id, trade_date, [order.id]
    )
    return self.repo.get_order(order.id)
```

Create historical orders with their normal calculated reservation amount or quantity retained on the order, but without applying a current-ledger cash event or position freeze. During replay, reuse `_restore_single_reservation` so sufficient historical cash is reserved before the normal matching fill.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/paper_trading/services/test_order_service.py::test_place_order_replays_past_a_share_buy_without_current_cash_freeze -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add test/paper_trading/services/test_order_service.py paper_trading/services/order_service.py paper_trading/services/order_delete_service.py
git commit -m "feat: replay historical A-share buy orders"
```

### Task 2: Establish Historical Sell Replay Behavior

**Files:**
- Modify: `test/paper_trading/services/test_order_service.py`
- Modify: `paper_trading/services/order_service.py`
- Modify: `paper_trading/services/order_delete_service.py`

**Interfaces:**
- Consumes: historical account replay produced by Task 1 and A-share position lots.
- Produces: historical sells evaluated against replayed dated inventory and T+1 maturity.

- [ ] **Step 1: Write the failing test**

```python
def test_place_order_replays_past_sell_against_historical_matured_position(tmp_path):
    engine, session, repo, service = _repo_and_service(tmp_path)
    account = repo.create_account("historical-sell", Decimal("100000.00"))
    service.place_order(account.id, "000001.SZ", OrderSide.BUY, 1100, Decimal("10.00"), date(2026, 6, 15))

    sell = service.place_order(
        account.id, "000001.SZ", OrderSide.SELL, 1100, Decimal("11.00"), date(2026, 6, 16)
    )

    assert sell.status == OrderStatus.FILLED.value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/paper_trading/services/test_order_service.py::test_place_order_replays_past_sell_against_historical_matured_position -v`

Expected: FAIL because historical sell entry uses current-position validation or historical-date rejection instead of replayed inventory.

- [ ] **Step 3: Write minimal implementation**

```python
def _create_historical_a_share_order(...):
    if side == OrderSide.BUY:
        frozen_cash = calculated_order_cost
        frozen_quantity = 0
    else:
        frozen_cash = Decimal("0")
        frozen_quantity = quantity
    return self.repo.create_order(..., frozen_cash=frozen_cash, frozen_quantity=frozen_quantity)
```

Bypass entry-time current position and T+1 checks for past A-share sells. Preserve the quantity as an order reservation definition; replay validates and restores it through `_check_sell_reservation` before matching.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/paper_trading/services/test_order_service.py -v`

Expected: PASS, including insufficient historical inventory and A-share T+1 scenarios added alongside the primary test.

- [ ] **Step 5: Commit**

```bash
git add test/paper_trading/services/test_order_service.py paper_trading/services/order_service.py paper_trading/services/order_delete_service.py
git commit -m "feat: replay historical A-share sell orders"
```

### Task 3: Protect Replay Integrity and Order 33 Regression

**Files:**
- Modify: `test/paper_trading/services/test_order_service.py`
- Modify: `test/paper_trading/services/test_matching_service.py`
- Modify: `docs/paper_trading.md`

**Interfaces:**
- Consumes: historical order creation and account replay from Tasks 1 and 2.
- Produces: regression coverage for historical historical sell entry, explicit documentation of historical-order replay behavior.

- [ ] **Step 1: Write the failing regression tests**

```python
def test_historical_sell_matching_order_33_is_not_rejected_for_past_date(tmp_path):
    # Seed a historically mature 002558 position and daily bar spanning 28.00.
    # Assert the sell is not rejected with HISTORICAL_TRADE_DATE_NOT_ELIGIBLE.
```

- [ ] **Step 2: Run regression tests to verify the expected failure**

Run: `uv run pytest test/paper_trading/services/test_order_service.py -v`

Expected: FAIL only until Tasks 1 and 2 make the historical source-fact and replay path active.

- [ ] **Step 3: Add only required consistency fixes and documentation**

```markdown
Past-date A-share orders are recorded as historical source orders. The account ledger is rebuilt from the affected date, so historical cash, holdings, T+1, and market data determine the result.
```

Add assertions that manual source facts and unaffected current-date reservation behavior remain intact. Do not add an import mode or modify matching semantics unrelated to historical replay.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py docs/paper_trading.md
```

### Task 4: Run Project Verification

**Files:**
- Modify: only files required by failures found during verification.

**Interfaces:**
- Consumes: completed historical-order replay behavior and focused coverage.
- Produces: verified implementation suitable for review.

- [ ] **Step 1: Run format and lint checks**

Run: `uv run ruff format --check . && uv run ruff check .`

Expected: PASS.

- [ ] **Step 2: Run the paper-trading test suite**

Run: `uv run pytest test/paper_trading test/tools/test_paper_trading_cli.py`

Expected: PASS.

- [ ] **Step 3: Run full project tests if focused checks are clean**

Run: `uv run pytest test`

Expected: PASS, or report pre-existing unrelated failures separately.

- [ ] **Step 4: Inspect final diff**

Run: `git diff --check && git diff --stat && git status --short`

Expected: no whitespace errors and only intended historical-order replay files changed.
