# ETF Historical Replay Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that explicit historical ETF orders replay through account rebuild with correct ETF-specific settlement and derived records, without regressing A-share or HK Connect behavior.

**Architecture:** Retain the existing `OrderService` historical ETF branch and `OrderDeleteService.rebuild_account_from` replay lifecycle. Expand the focused lifecycle test so it asserts all persisted results required by issue #47; production code changes only when this acceptance test exposes a concrete defect.

**Tech Stack:** Python 3.11+, pytest, SQLAlchemy, SQLite test database, Ruff, uv.

## Global Constraints

- Use `uv run` for every Python command.
- Preserve explicit `Market.ETF` routing; never infer ETF market from symbol.
- ETF replay must preserve eligibility, 100-unit lots, CNY 0.001 ticks, commission-only fees, T+1 lots, immediate sell proceeds, and ETF daily-bar routing.
- Rebuild processing remains ordered by trade date and order ID and must preserve market-qualified identity.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLA.
- Do not change production code without a failing acceptance assertion demonstrating the gap.

---

## File Structure

- Modify: `test/paper_trading/services/test_matching_service.py` — extend the existing historical ETF replay lifecycle fixture and assertions.
- Inspect: `paper_trading/services/order_service.py` — current ETF historical-order admission and rebuild trigger; modify only if the focused test fails.
- Inspect: `paper_trading/services/order_delete_service.py` — replay ordering and regeneration flow; modify only if the focused test fails.
- Inspect: `paper_trading/services/matching_service.py` — fill, fee, and settlement lifecycle; modify only if the focused test fails.
- Inspect: `paper_trading/storage/market_data.py` — ETF exact-date routing; modify only if the focused test fails.

### Task 1: Strengthen Historical ETF Replay Acceptance Coverage

**Files:**
- Modify: `test/paper_trading/services/test_matching_service.py:153-188`
- Inspect: `paper_trading/services/order_service.py:335-421`
- Inspect: `paper_trading/services/order_delete_service.py:119-188`
- Test: `test/paper_trading/services/test_matching_service.py::test_historical_etf_buy_then_next_date_sell_rebuilds_full_lifecycle`

**Interfaces:**
- Consumes: `OrderService.place_order(account_id: int, symbol: str, side: OrderSide, quantity: int, limit_price: Decimal, trade_date: date, market: Market) -> PaperOrder`.
- Consumes: `OrderDeleteService.rebuild_account_from(account_id: int, start_date: date, triggering_order_ids: list[int]) -> PaperLedgerRebuild`.
- Produces: A regression test proving the persisted ETF historical replay contract.

- [ ] **Step 1: Expand the lifecycle test with ETF acceptance and routing observability**

  Add a small local recording provider inside the test. It subclasses `FakeMarketDataProvider`, appends each `market` argument received by `get_daily_bar`, and delegates to the parent implementation. Replace the test's `FakeMarketDataProvider` construction with this provider.

  ```python
  class RecordingETFMarketDataProvider(FakeMarketDataProvider):
      def __init__(self, bars: dict[tuple[str, date], DailyBar]) -> None:
          super().__init__(bars)
          self.requested_markets: list[str | None] = []

      def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
          self.requested_markets.append(market)
          return super().get_daily_bar(symbol, trade_date, market)
  ```

  After placing the buy and sell orders, assert that both are initially accepted, retain `Market.ETF.value`, and that the buy freezes `Decimal("315.0315")` for 100 units at CNY 3.150 with a 0.0001 ETF commission rate.

- [ ] **Step 2: Run the focused test to verify the new acceptance contract**

  Run: `uv run pytest test/paper_trading/services/test_matching_service.py::test_historical_etf_buy_then_next_date_sell_rebuilds_full_lifecycle -v`

  Expected: PASS if historical ETF replay already applies the documented rules. If it fails, record the observed behavior before modifying production code.

- [ ] **Step 3: Assert replayed trades, cash, snapshots, and round trip**

  Extend the existing post-rebuild assertions with the following exact checks:

  ```python
  trades = repo.list_trades(account.id)
  assert [(trade.market, trade.side, trade.fees) for trade in trades] == [
      (Market.ETF, OrderSide.BUY.value, Decimal("0.0315")),
      (Market.ETF, OrderSide.SELL.value, Decimal("0.0325")),
  ]
  assert market_data.requested_markets == [Market.ETF.value, Market.ETF.value]
  assert repo.get_cash_available(account.id) == Decimal("100009.9360")
  assert repo.list_pending_settlements(account.id) == []
  assert [snapshot.trade_date for snapshot in repo.list_snapshots(account.id)] == [buy_date, sell_date]
  round_trips = repo.list_round_trips(account.id)
  assert len(round_trips) == 1
  assert round_trips[0].market == Market.ETF.value
  assert round_trips[0].status == "closed"
  assert {event.order_id for event in repo.list_cash_ledger(account.id) if event.order_id} == {buy.id, sell.id}
  ```

  Preserve the existing assertions for regenerated counts, filled orders, ETF trade order, and absent final ETF position.

- [ ] **Step 4: Run the focused test to verify it passes**

  Run: `uv run pytest test/paper_trading/services/test_matching_service.py::test_historical_etf_buy_then_next_date_sell_rebuilds_full_lifecycle -v`

  Expected: PASS with two filled ETF trades, two snapshots, one closed ETF round trip, no pending settlement, and immediate cash of `100009.9360`.

- [ ] **Step 5: Apply the smallest production fix only if the focused test fails**

  Diagnose the failing assertion before editing. Make a localized correction in the existing owner module:

  - `paper_trading/services/order_service.py` for historical order creation or ETF reservation;
  - `paper_trading/services/order_delete_service.py` for replay ordering or reservation restoration;
  - `paper_trading/services/matching_service.py` for fill, ETF fee, cash settlement, or trade persistence;
  - `paper_trading/storage/market_data.py` for ETF daily-bar routing.

  Do not introduce a new replay abstraction or alter A-share/HK logic to satisfy an ETF-only assertion. Re-run the focused test after every correction.

- [ ] **Step 6: Commit the acceptance coverage and any required minimal fix**

  ```bash
  git add test/paper_trading/services/test_matching_service.py paper_trading/services/order_service.py paper_trading/services/order_delete_service.py paper_trading/services/matching_service.py paper_trading/storage/market_data.py
  git commit -m "test: cover ETF historical replay lifecycle"
  ```

  Stage only files actually modified; do not stage existing untracked `data/` or unrelated `docs/superpowers/` artifacts.

### Task 2: Run Cross-Market Regression Verification

**Files:**
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_order_service.py:318-387,505-526`
- Test: `test/paper_trading/services/test_order_delete_service.py:240-310`
- Inspect: `paper_trading/services/order_service.py`
- Inspect: `paper_trading/services/order_delete_service.py`

**Interfaces:**
- Consumes: The historical replay test contract produced by Task 1.
- Produces: Verified evidence that changed or asserted replay paths retain A-share and HK Connect behavior.

- [ ] **Step 1: Run targeted historical-order and replay regressions**

  Run:

  ```bash
  uv run pytest \
    test/paper_trading/services/test_order_service.py::test_place_order_replays_past_a_share_buy_without_current_cash_freeze \
    test/paper_trading/services/test_order_service.py::test_place_order_replays_past_sell_against_historical_matured_position \
    test/paper_trading/services/test_order_service.py::test_past_hk_connect_order_uses_hk_validation_without_bfq_diagnostic \
    test/paper_trading/services/test_order_delete_service.py::test_repeated_rebuild_preserves_source_facts_and_current_derived_counts \
    test/paper_trading/services/test_matching_service.py::test_historical_etf_buy_then_next_date_sell_rebuilds_full_lifecycle \
    -v
  ```

  Expected: PASS. A-share historical orders preserve replayed historical cash and matured-lot selling; HK Connect validation remains independent of A-share BFQ diagnostics; repeated rebuild remains idempotent.

- [ ] **Step 2: Run focused module coverage and formatting checks**

  Run:

  ```bash
  uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_order_delete_service.py
  uv run ruff format --check test/paper_trading/services/test_matching_service.py
  uv run ruff check test/paper_trading/services/test_matching_service.py
  ```

  Expected: all tests pass, formatting is unchanged or compliant, and Ruff reports no violations.

- [ ] **Step 3: Run the wider paper-trading suite**

  Run: `uv run pytest test/paper_trading`

  Expected: PASS. If environment-only PostgreSQL coverage is unavailable, run the SQLite-backed suite successfully and report the unavailable integration coverage without weakening tests.

- [ ] **Step 4: Inspect final diff and commit any verification-driven correction**

  Run:

  ```bash
  git status --short
  git diff --check
  git diff -- test/paper_trading/services/test_matching_service.py paper_trading/services/order_service.py paper_trading/services/order_delete_service.py paper_trading/services/matching_service.py paper_trading/storage/market_data.py
  ```

  Expected: no whitespace errors; diff limited to the focused test and a demonstrated minimal production fix, if any. Commit only a subsequently required correction with a specific English subject such as `fix: preserve ETF replay settlement`.
