# Paper Trading ETF Order And Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete accepted ETF order placement, matching, settlement, validity, replay, and market-qualified ETF name exposure for issue #46.

**Architecture:** Add a narrow `Market.ETF` branch to the existing order and validity services, injecting the existing `ETFEligibilityService` through the API composition root. Preserve the shared matching, fee, cash, position, diagnostic, snapshot, and replay lifecycle, modifying only ETF-specific policy points. Extend the existing security-name provider to resolve ETF metadata using the same `(market, symbol)` input contract.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, Decimal, pytest, Ruff, mypy, uv.

## Global Constraints

- Use `uv run` for all Python commands.
- Do not add a web UI, automatic market inference, money-market ETF support, ETF-specific T+0 handling, or a security-type column.
- Preserve explicit `market` selection and market-qualified identity `(account_id, market, symbol)`.
- ETF symbols must be bare six-digit strings; `.SH` and `.SZ` suffixes are invalid at the ETF entry point.
- ETF orders require positive 100-unit quantities and positive CNY 0.001-aligned limit prices.
- ETF trades charge ETF commission only; ETF sell proceeds are immediately available after a fill.
- ETF units use T+1 sellability, including imported lots through `buy_trade_date`.
- ETF matching and validity use ETF daily low/high without A-share limit-up/down analysis or A-share/fund data fallback.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLA.

---

## File Structure

- `paper_trading/services/order_service.py`: dispatch ETF requests, validate ETF eligibility/rules, reuse common buy/sell acceptance and historical rebuilding.
- `paper_trading/domain/rules.py`: hold the reusable CNY 0.001 ETF price-tick validator.
- `paper_trading/services/trade_validity_service.py`: analyze ETF daily range without stock limit-price logic.
- `paper_trading/services/order_delete_service.py`: preserve ETF-specific T+1 replay rejection details.
- `paper_trading/api/deps.py`: create the ETF eligibility service from the request session.
- `paper_trading/api/routers/orders.py`: inject and pass ETF eligibility validation into `OrderService`.
- `paper_trading/storage/security_metadata.py`: resolve ETF display names from `ETFBasic`.
- `test/paper_trading/services/test_order_service.py`: verify ETF acceptance, rejection, cash reservation, T+1, and historical replay.
- `test/paper_trading/services/test_trade_validity_service.py`: verify ETF validity range behavior and market routing.
- `test/paper_trading/services/test_order_delete_service.py`: verify ETF replay preserves the ETF T+1 policy.
- `test/paper_trading/storage/test_security_metadata.py`: verify ETF market-qualified names and mixed-market collision safety.
- `test/paper_trading/api/test_orders_api.py`: verify API composition accepts ETF requests and exposes ETF names/market.

### Task 1: Add ETF Order Admission Rules

**Files:**
- Modify: `paper_trading/domain/rules.py`
- Modify: `paper_trading/services/order_service.py`
- Test: `test/paper_trading/services/test_order_service.py`

**Interfaces:**
- Consumes: `ETFEligibilityService.validate_etf_eligibility(symbol: str) -> ETFEligibilityValidation`.
- Produces: `validate_etf_tick_size(price: Decimal) -> None` and an `OrderService` constructor that accepts `etf_eligibility: ETFEligibilityService | None = None`.
- Produces: `_place_etf_order(...) -> PaperOrder`, which creates only ETF-market orders after eligibility, trade-date, lot, and tick checks.

- [ ] **Step 1: Write failing ETF admission tests**

Add an SQLite fixture helper that inserts `ETFBasic` and a matching `supported` eligibility row. Add tests that assert accepted ETF orders persist `market == "etf"`, reserve `quantity * limit_price + ETF commission`, and call market data validity with `market="etf"`.

```python
order = service.place_order(
    account.id, "510300", OrderSide.BUY, 100, Decimal("3.001"), trade_date, market="etf"
)
assert order.status == OrderStatus.ACCEPTED.value
assert order.market == Market.ETF.value
assert order.frozen_cash == Decimal("300.1200")
```

Parametrize rejected order cases for `"510300.SH"`, unknown/unreviewed eligibility, `quantity=50`, `limit_price=Decimal("3.0005")`, and a closed date. Assert the stored rejected order has the corresponding code: `INVALID_ETF_SYMBOL`, `ETF_ELIGIBILITY_UNREVIEWED`, `INVALID_LOT_SIZE`, `INVALID_TICK_SIZE`, or `INVALID_TRADE_DATE`.

- [ ] **Step 2: Run the focused admission tests and verify they fail**

Run: `uv run pytest test/paper_trading/services/test_order_service.py -k etf -v`

Expected: FAIL because `OrderService` does not validate ETF eligibility or ticks and routes ETF orders through `_place_a_share_order`.

- [ ] **Step 3: Implement a precise ETF tick validator**

In `paper_trading/domain/rules.py`, add:

```python
def validate_etf_tick_size(price: Decimal) -> None:
    tick_size = Decimal("0.001")
    if price <= 0 or price != price.quantize(tick_size):
        raise PaperTradingError(
            "INVALID_TICK_SIZE",
            "ETF limit price must be a positive multiple of CNY 0.001",
            {"price": str(price), "tick_size": "0.001"},
        )
```

Comparing the value with `price.quantize(Decimal("0.001"))` accepts harmless trailing zeros such as `3.0010` and rejects values such as `3.0005` that cannot be represented on the CNY 0.001 grid.

- [ ] **Step 4: Implement ETF order dispatch and acceptance**

Extend `OrderService.__init__` with an optional `etf_eligibility` dependency. In `place_order`, dispatch `Market.ETF` before the A-share branch. The ETF path must:

```python
validation = self.etf_eligibility.validate_etf_eligibility(symbol)
if not validation.eligible:
    raise PaperTradingError(validation.code, validation.message, {"symbol": symbol, "market": market.value})
ensure_lot_size(quantity)
validate_etf_tick_size(limit_price)
if not self.market_data.is_trade_date(trade_date):
    raise PaperTradingError("INVALID_TRADE_DATE", "Trade date is not open", {"trade_date": str(trade_date)})
```

For current dates, call the existing `_accept_buy_order` or `_accept_sell_order` with `Market.ETF`; those functions already select ETF fees and use market-qualified positions/lots. For a past date, create an accepted ETF order with the same frozen-cash/frozen-quantity contract as A-share, call `OrderDeleteService(...).rebuild_account_from(...)`, and return the refreshed order. Do not apply the A-share historical diagnostic gate to ETFs.

- [ ] **Step 5: Run focused order-service tests**

Run: `uv run pytest test/paper_trading/services/test_order_service.py -k etf -v`

Expected: PASS, including admission, rejection, and existing ETF fee coverage.

- [ ] **Step 6: Commit the admission change**

```bash
git add paper_trading/domain/rules.py paper_trading/services/order_service.py test/paper_trading/services/test_order_service.py
git commit -m "feat: validate ETF paper orders"
```

### Task 2: Make ETF Validity And Replay Policy Explicit

**Files:**
- Modify: `paper_trading/services/trade_validity_service.py`
- Modify: `paper_trading/services/order_delete_service.py`
- Test: `test/paper_trading/services/test_trade_validity_service.py`
- Test: `test/paper_trading/services/test_order_delete_service.py`

**Interfaces:**
- Consumes: ETF orders persisted by Task 1 with `market="etf"`.
- Produces: ETF validity checks with daily-range outcomes and no A-share limit metadata.
- Produces: replay T+1 rejections whose code/detail identify ETF policy rather than A-share policy.

- [ ] **Step 1: Write failing ETF validity tests**

Add an ETF order and a bar with `up_limit=Decimal("3.100")` and `down_limit=Decimal("2.900")`. Assert an in-range ETF price is `valid`, `reason_code == "VALID"`, and all four limit analysis fields are `None`.

```python
assert check.daily_low == Decimal("2.950")
assert check.daily_high == Decimal("3.050")
assert check.limit_up_price is None
assert check.touched_limit_up is None
```

Add an out-of-range case expecting `PRICE_OUT_OF_DAILY_RANGE`, and assert a capturing provider receives `market="etf"`. Add a replay test where same-date ETF lots cannot restore a sell reservation and assert a market-neutral or ETF-specific T+1 reason, never `A_SHARE_T1_VIOLATION` text.

- [ ] **Step 2: Run validity and replay tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_order_delete_service.py -k etf -v`

Expected: FAIL because ETFs currently use `_analyze_a_share` and replay returns A-share-specific policy detail.

- [ ] **Step 3: Implement ETF daily-range validity**

Add `_analyze_etf(order: PaperOrder) -> PaperTradeValidityCheck`, modeled on the HK daily-range persistence but without HK metadata or tick validation. Fetch the bar with `market="etf"`; for missing data, persist the existing `MARKET_DATA_UNAVAILABLE` unchecked result. Otherwise use:

```python
price_in_range = bar.low <= Decimal(order.limit_price) <= bar.high
status = TradeValidityStatus.VALID if price_in_range else TradeValidityStatus.INVALID
reason_code = "VALID" if price_in_range else "PRICE_OUT_OF_DAILY_RANGE"
```

Persist `daily_low`/`daily_high`, `price_in_range`, and `market="etf"`; persist `None` for `limit_up_price`, `limit_down_price`, `touched_limit_up`, and `touched_limit_down`. Dispatch this method from `analyze_order` when `order.market == "etf"`.

- [ ] **Step 4: Correct the replay T+1 label without changing maturity math**

Change `OrderDeleteService._check_sell_reservation` to receive `market: str` and select the policy code/message from the market. Both A-share and ETF retain the existing `< order_trade_date` maturity predicate. ETF failures must use `ETF_T1_VIOLATION` and text describing ETF T+1; A-share retains `A_SHARE_T1_VIOLATION`. Pass `order.market` from `_restore_single_reservation`.

- [ ] **Step 5: Run focused validity and replay tests**

Run: `uv run pytest test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_order_delete_service.py -k etf -v`

Expected: PASS, with existing A-share/HK tests still passing when run without `-k`.

- [ ] **Step 6: Commit the validity and replay change**

```bash
git add paper_trading/services/trade_validity_service.py paper_trading/services/order_delete_service.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_order_delete_service.py
git commit -m "feat: apply ETF validity and T1 rules"
```

### Task 3: Wire ETF Eligibility Through The API And Resolve ETF Names

**Files:**
- Modify: `paper_trading/api/deps.py`
- Modify: `paper_trading/api/routers/orders.py`
- Modify: `paper_trading/storage/security_metadata.py`
- Test: `test/paper_trading/api/test_orders_api.py`
- Test: `test/paper_trading/storage/test_security_metadata.py`

**Interfaces:**
- Consumes: `ETFEligibilityService(repo)` and Task 1's `OrderService(..., etf_eligibility=...)` constructor.
- Produces: API ETF admission with the same stored rejection contract as direct service calls.
- Produces: `SecurityNameProvider.resolve_names` entries keyed as `("etf", symbol)` using `ETFBasic.基金代码` and `ETFBasic.中文简称`.

- [ ] **Step 1: Write failing API and name-resolution tests**

In `test_security_metadata.py`, insert one `AStockBasic` and one `ETFBasic` with the same six-digit code but distinct names. Assert:

```python
assert provider.resolve_names([("a_share", "510300"), ("etf", "510300")]) == {
    ("a_share", "510300"): "A-share collision name",
    ("etf", "510300"): "CSI 300 ETF",
}
```

In `test_orders_api.py`, seed ETF basic metadata and a supported eligibility row, post an ETF buy request, and assert status `accepted`, `market == "etf"`, and later order/trade list responses include the ETF `stock_name`. Add an unreviewed ETF API request that returns the normal order response with `status == "rejected"` and `rejection_code == "ETF_ELIGIBILITY_UNREVIEWED"`.

- [ ] **Step 2: Run API and metadata tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_security_metadata.py test/paper_trading/api/test_orders_api.py -k etf -v`

Expected: FAIL because dependency injection does not construct the eligibility service and `SecurityNameProvider` ignores ETF securities.

- [ ] **Step 3: Add the API composition dependency**

In `paper_trading/api/deps.py`, add:

```python
def get_etf_eligibility_service(session: Session = Depends(get_session)) -> ETFEligibilityService:
    return ETFEligibilityService(PaperTradingRepository(session))
```

In the create-order route, depend on it and pass `etf_eligibility=etf_eligibility_service` to `OrderService`. Preserve the existing account existence check, transaction commit, request schema, and HTTP response behavior.

- [ ] **Step 4: Add ETF metadata name resolution**

Import `ETFBasic`. Partition requested symbols with:

```python
etf_symbols = {symbol for market, symbol in requested if market == "etf"}
```

Query `ETFBasic.基金代码.in_(etf_symbols)` inside the same nested-transaction/`SQLAlchemyError` containment pattern used by the other resolvers. Return only nonblank `ETFBasic.中文简称` values under `("etf", code)` keys. Do not alter A-share or HK lookup behavior.

- [ ] **Step 5: Run focused API and metadata tests**

Run: `uv run pytest test/paper_trading/storage/test_security_metadata.py test/paper_trading/api/test_orders_api.py -k etf -v`

Expected: PASS, including collision-safe names and the direct API acceptance/rejection path.

- [ ] **Step 6: Commit the composition and read-path change**

```bash
git add paper_trading/api/deps.py paper_trading/api/routers/orders.py paper_trading/storage/security_metadata.py test/paper_trading/api/test_orders_api.py test/paper_trading/storage/test_security_metadata.py
git commit -m "feat: expose ETF paper order metadata"
```

### Task 4: Verify End-To-End ETF Matching, Snapshot, And Replay

**Files:**
- Modify: `test/paper_trading/services/test_matching_service.py`
- Modify: `test/paper_trading/services/test_snapshot_service.py`
- Modify: `test/paper_trading/services/test_order_service.py`

**Interfaces:**
- Consumes: ETF orders accepted through Task 1, ETF validity from Task 2, and API/name wiring from Task 3.
- Produces: evidence that shared matching, immediate settlement, diagnostics, snapshots, and historical rebuild work under `market="etf"` without A-share fallback.

- [ ] **Step 1: Write failing workflow tests**

Create a supported ETF buy on the fixed current date with a matching ETF bar. Run matching and assert a filled ETF order/trade/position/lot, commission-only fees, and no pending settlement. Attempt a same-date sell and assert rejection; place the sell on the next trading date, match it, and assert available cash increases immediately and the position is removed.

Add a limit outside ETF low/high and assert it stays accepted/skipped. Add an ETF order with a missing exact-date bar and assert an unresolved diagnostic with `market == "etf"` and `adjust == "qfq"`; make the bar available and assert the eligible rebuild path fills it exactly once. Add an ETF position snapshot test that asserts the provider is called only with `market="etf"` and a missing ETF bar creates an ETF-qualified valuation-gap detail.

- [ ] **Step 2: Run workflow tests to establish the baseline**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_order_service.py -k etf -v`

Expected: Any remaining failure identifies an integration point missed by Tasks 1-3. Do not weaken assertions or introduce fallback behavior.

- [ ] **Step 3: Make only integration fixes exposed by the workflow tests**

Keep fixes constrained to existing market dispatch points. Preserve `MatchingService._record_missing_exact_date_diagnostic` ETF `qfq` behavior, `MatchingService._fill_order` commission-only fee dispatch, `MatchingService._settle_sell` immediate cash path, `SnapshotService` market forwarding, and repository market-qualified retry join unless a test demonstrates a concrete defect. Add production code only for a failing workflow assertion.

- [ ] **Step 4: Run the focused ETF workflow suite**

Run: `uv run pytest test/paper_trading/services/test_order_service.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/storage/test_security_metadata.py test/paper_trading/api/test_orders_api.py -k 'etf or market_collision' -v`

Expected: PASS.

- [ ] **Step 5: Run affected regression suites and static checks**

Run: `uv run pytest test/paper_trading/services/test_order_service.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/storage/test_security_metadata.py test/paper_trading/api/test_orders_api.py`

Expected: PASS.

Run: `uv run ruff format --check paper_trading test/paper_trading && uv run ruff check paper_trading test/paper_trading && uv run mypy paper_trading`

Expected: all checks exit zero.

- [ ] **Step 6: Commit workflow tests and integration fixes**

```bash
git add paper_trading test/paper_trading
git commit -m "test: cover ETF paper trading workflow"
```

### Task 5: Final Documentation And Repository Verification

**Files:**
- Modify: only documentation identified by the repository `update_doc` workflow, if any.
- Test: repository paper-trading test suite and changed-file formatting/lint/type checks.

**Interfaces:**
- Consumes: implementation and passing focused checks from Tasks 1-4.
- Produces: documentation synchronized with the delivered public behavior and recorded verification evidence.

- [ ] **Step 1: Inspect the implementation diff and affected documentation**

Run: `git diff --check && git diff --stat && git status --short`

Read the repository-local `update_doc` skill and inspect only docs linked to paper-trading API, CLI, data contract, or ETF support. Do not change unrelated documentation.

- [ ] **Step 2: Update only affected documentation**

Document explicit `market=etf`, supported ETF eligibility, 100-unit/CNY 0.001 constraints, T+1 sellability, commission-only fees, and immediate ETF sell proceeds only if the inspected documentation exposes paper-trading order behavior and is now incomplete. Use the repository’s existing wording and examples.

- [ ] **Step 3: Run final verification**

Run: `uv run pytest test/paper_trading`

Expected: PASS.

Run: `uv run pre-commit run --files paper_trading/domain/rules.py paper_trading/services/order_service.py paper_trading/services/trade_validity_service.py paper_trading/services/order_delete_service.py paper_trading/api/deps.py paper_trading/api/routers/orders.py paper_trading/storage/security_metadata.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/storage/test_security_metadata.py test/paper_trading/api/test_orders_api.py`

Expected: PASS. Report any skipped PostgreSQL integration checks explicitly.

- [ ] **Step 4: Commit documentation only when it changed**

```bash
git add docs
git commit -m "docs: describe ETF paper order workflow"
```

Skip this commit when no documentation changes were required.
