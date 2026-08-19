# Catalogue ETF Paper Order Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify new Paper Trading orders for six-digit ETF catalogue symbols as `etf` before eligibility validation and matching.

**Architecture:** Resolve the authoritative market in `OrderService.place_order`, before idempotency matching and market-specific dispatch. A catalogue-backed `ETFBasic` symbol resolves to `Market.ETF` whether the request omits `market`, supplies `a_share`, or supplies `etf`; the existing ETF admission branch then preserves eligibility, fees, rules, and raw `etf_daily` matching behavior. Symbols absent from the catalogue retain the current requested/default market handling.

**Tech Stack:** Python 3.11+, SQLAlchemy, pandas, pytest, Ruff, mypy, uv.

## Global Constraints

- `ETFBasic` catalogue membership determines ETF market identity only; `ETFEligibilityService` remains the ETF order-admission authority.
- A catalogue-backed ETF resolves to `etf` before idempotency matching and any market-specific validation.
- Invalid supplied market values retain the existing `INVALID_MARKET` rejected-order behavior.
- Catalogue membership requires a bare six-digit symbol and an `ETFBasic` row; do not add prefix-based inference.
- Preserve existing ETF fees, lot, tick, T+1, settlement, validity, and raw `etf_daily` matching behavior.
- Preserve existing A-share and Hong Kong Stock Connect behavior for symbols absent from the ETF catalogue.
- Do not change API schemas, CLI arguments, catalogue ingestion, database schema, historical-order repair, DAG scheduling, dependencies, retries, task boundaries, or SLA.
- Use `uv run` for Python commands in this repository.
- Do not commit unless the user explicitly requests a commit.

---

## File Structure

- `paper_trading/services/order_service.py`: Resolves the authoritative market before idempotency handling and dispatches orders to the existing ETF branch.
- `test/paper_trading/services/test_order_service.py`: Proves catalogue classification, eligibility rejection identity, non-catalogue regression behavior, and idempotency behavior at the service boundary.
- `test/paper_trading/services/test_matching_service.py`: Proves an order entered without `market=etf` for `518880` follows the existing raw ETF daily matching route.

### Task 1: Resolve Catalogue ETF Market At Order Entry

**Files:**
- Modify: `paper_trading/services/order_service.py:54-83`
- Test: `test/paper_trading/services/test_order_service.py:947-1100`

**Interfaces:**
- Consumes: `OrderService.place_order(..., market: str | None = None) -> PaperOrder`, `ETFBasic`, `Market`, and `ETFEligibilityService.validate_etf_eligibility(symbol)`.
- Produces: an authoritative `resolved_market: Market` that is `Market.ETF` for a bare six-digit symbol with an `ETFBasic` row before `_matches_order_request` and `_place_etf_order` are reached.

- [ ] **Step 1: Replace the explicit-market rejection test with failing omitted-market classification coverage**

  In `test/paper_trading/services/test_order_service.py`, replace
  `test_known_etf_symbol_requires_explicit_etf_market` with:

  ```python
  def test_catalogue_etf_without_market_resolves_to_etf(tmp_path):
      engine, session, repo, _ = _repo_and_service(tmp_path)
      _add_supported_etf(repo)
      service = _etf_order_service(repo, FakeMarketDataProvider())
      account = repo.create_account("catalogue-etf", Decimal("100000.00"))

      order = service.place_order(
          account.id,
          "510300",
          OrderSide.BUY,
          100,
          Decimal("3.001"),
          date(2026, 6, 16),
      )
      session.commit()

      assert (order.status, order.market) == (OrderStatus.ACCEPTED.value, Market.ETF.value)
      assert repo.list_trade_validity_checks(order.id)[0].market == Market.ETF.value
      engine.dispose()
  ```

- [ ] **Step 2: Run the new test to verify the current rejection**

  Run: `uv run pytest test/paper_trading/services/test_order_service.py::test_catalogue_etf_without_market_resolves_to_etf -v`

  Expected: FAIL because the current implementation persists a rejected A-share order with `MARKET_SYMBOL_MISMATCH`.

- [ ] **Step 3: Add failing coverage for explicit A-share override and unreviewed ETF identity**

  Add these tests immediately after the omitted-market test:

  ```python
  def test_catalogue_etf_overrides_explicit_a_share_market(tmp_path):
      engine, session, repo, _ = _repo_and_service(tmp_path)
      _add_supported_etf(repo)
      service = _etf_order_service(repo, FakeMarketDataProvider())
      account = repo.create_account("catalogue-etf-override", Decimal("100000.00"))

      order = service.place_order(
          account.id,
          "510300",
          OrderSide.BUY,
          100,
          Decimal("3.001"),
          date(2026, 6, 16),
          market=Market.A_SHARE,
      )
      session.commit()

      assert (order.status, order.market) == (OrderStatus.ACCEPTED.value, Market.ETF.value)
      engine.dispose()


  def test_unreviewed_catalogue_etf_rejection_persists_etf_market(tmp_path):
      engine, session, repo, _ = _repo_and_service(tmp_path)
      session.add(ETFBasic(基金代码="510301", 中文简称="Unreviewed ETF", 交易所="SH", 存续状态="L"))
      session.flush()
      service = _etf_order_service(repo, FakeMarketDataProvider())
      account = repo.create_account("unreviewed-catalogue-etf", Decimal("100000.00"))

      order = service.place_order(
          account.id,
          "510301",
          OrderSide.BUY,
          100,
          Decimal("3.001"),
          date(2026, 6, 16),
          market=Market.A_SHARE,
      )
      session.commit()

      assert (order.status, order.market) == (OrderStatus.REJECTED.value, Market.ETF.value)
      assert order.rejection_code == "ETF_ELIGIBILITY_UNREVIEWED"
      engine.dispose()
  ```

- [ ] **Step 4: Run the classification tests to verify failure**

  Run: `uv run pytest test/paper_trading/services/test_order_service.py -k "catalogue_etf or unreviewed_catalogue" -v`

  Expected: FAIL because omitted or explicit A-share known ETF requests still resolve to A-share and the ETF eligibility branch is not reached.

- [ ] **Step 5: Implement the minimal authoritative market resolution**

  In `OrderService.place_order`, keep invalid-market parsing as the first operation. Then replace the known-ETF rejection block with resolution that only executes when parsing succeeded:

  ```python
  resolved_market = Market.A_SHARE
  idempotency_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
  market_error: PaperTradingError | None = None
  try:
      resolved_market = Market(market) if market else Market.A_SHARE
  except ValueError:
      market_error = PaperTradingError(
          "INVALID_MARKET",
          f"Unsupported market: {market}",
          {"market": market},
      )
  if market_error is None and self._is_known_etf_symbol(symbol):
      resolved_market = Market.ETF
  ```

  Delete the `MARKET_SYMBOL_MISMATCH` construction for a known ETF with omitted market. Keep `_is_known_etf_symbol` unchanged: its bare-six-digit regular expression and `ETFBasic` lookup are the catalogue membership contract.

- [ ] **Step 6: Run the classification tests and existing ETF admission regression tests**

  Run: `uv run pytest test/paper_trading/services/test_order_service.py -k "catalogue_etf or unreviewed_catalogue or etf_order_admission" -v`

  Expected: PASS. Supported catalogue ETFs are accepted and persist `etf`; the unreviewed ETF remains rejected with `ETF_ELIGIBILITY_UNREVIEWED` and persists `etf`; existing explicit ETF admission cases remain unchanged.

- [ ] **Step 7: Inspect the task diff before continuing**

  Run: `git diff --check -- paper_trading/services/order_service.py test/paper_trading/services/test_order_service.py`

  Expected: PASS with no whitespace errors. Do not commit unless the user
  explicitly requests it.

### Task 2: Preserve Non-Catalogue And Idempotent Request Behavior

**Files:**
- Modify: `test/paper_trading/services/test_order_service.py` near the catalogue ETF tests
- Test: `test/paper_trading/services/test_order_service.py`

**Interfaces:**
- Consumes: Task 1's `OrderService.place_order` market resolution and `_matches_order_request(order, ..., market: Market) -> bool`.
- Produces: regression evidence that only catalogue members resolve to `Market.ETF`, and that equivalent omitted/A-share retry requests reuse the resolved ETF order.

- [ ] **Step 1: Add failing non-catalogue A-share regression coverage**

  Add this test beside the Task 1 tests:

  ```python
  def test_six_digit_symbol_absent_from_etf_catalogue_remains_a_share(tmp_path):
      engine, session, repo, service = _repo_and_service(tmp_path)
      account = repo.create_account("non-catalogue-six-digit", Decimal("100000.00"))

      order = service.place_order(
          account.id,
          "510399",
          OrderSide.BUY,
          100,
          Decimal("10.00"),
          date(2026, 6, 16),
      )
      session.commit()

      assert (order.status, order.market) == (OrderStatus.ACCEPTED.value, Market.A_SHARE.value)
      engine.dispose()
  ```

- [ ] **Step 2: Add failing idempotency coverage for the resolved ETF identity**

  Add this test:

  ```python
  def test_catalogue_etf_idempotency_reuses_order_across_omitted_and_a_share_market(tmp_path):
      engine, session, repo, _ = _repo_and_service(tmp_path)
      _add_supported_etf(repo)
      service = _etf_order_service(repo, FakeMarketDataProvider())
      account = repo.create_account("catalogue-etf-idempotency", Decimal("100000.00"))

      first = service.place_order(
          account.id,
          "510300",
          OrderSide.BUY,
          100,
          Decimal("3.001"),
          date(2026, 6, 16),
          idempotency_key="catalogue-etf-order",
      )
      second = service.place_order(
          account.id,
          "510300",
          OrderSide.BUY,
          100,
          Decimal("3.001"),
          date(2026, 6, 16),
          idempotency_key="catalogue-etf-order",
          market=Market.A_SHARE,
      )
      session.commit()

      assert (first.id, first.market) == (second.id, Market.ETF.value)
      assert len(repo.list_orders(account.id)) == 1
      engine.dispose()
  ```

- [ ] **Step 3: Run the two regression tests to verify the intended boundary**

  Run: `uv run pytest test/paper_trading/services/test_order_service.py -k "absent_from_etf_catalogue or catalogue_etf_idempotency" -v`

  Expected: PASS after Task 1. The non-catalogue case proves the six-digit pattern alone does not infer ETF; the idempotency case proves resolution occurs before request matching.

- [ ] **Step 4: Run the complete order-service suite**

  Run: `uv run pytest test/paper_trading/services/test_order_service.py -v`

  Expected: PASS, including A-share, ETF, Hong Kong Stock Connect, historical replay, and market/symbol mismatch coverage.

- [ ] **Step 5: Inspect the order-service diff before continuing**

  Run: `git diff --check -- test/paper_trading/services/test_order_service.py`

  Expected: PASS with no whitespace errors. Do not commit unless the user
  explicitly requests it.

### Task 3: Demonstrate Implicit `518880` Raw ETF Matching

**Files:**
- Modify: `test/paper_trading/services/test_matching_service.py:529-573`
- Test: `test/paper_trading/services/test_matching_service.py`

**Interfaces:**
- Consumes: Task 1's `OrderService.place_order` resolution and the existing `StorageMarketDataProvider.get_daily_bar(symbol, trade_date, market="etf") -> DailyBar` raw `etf_daily` branch.
- Produces: end-to-end service-seam evidence that an order for `518880` entered without `market=etf` persists as ETF and matches from raw ETF daily data.

- [ ] **Step 1: Change the existing raw ETF matching test to omit the market argument**

  In `test_matching_fills_etf_order_from_raw_etf_daily_without_adjusted_fallback`, replace the current explicit-market placement:

  ```python
  order = order_service.place_order(
      account.id, "518880", OrderSide.BUY, 100, Decimal("8.818"), trade_date, market=Market.ETF
  )
  ```

  with:

  ```python
  order = order_service.place_order(
      account.id,
      "518880",
      OrderSide.BUY,
      100,
      Decimal("8.818"),
      trade_date,
  )
  assert order.market == Market.ETF.value
  ```

- [ ] **Step 2: Run the changed matching test to verify implicit ETF routing**

  Run: `uv run pytest test/paper_trading/services/test_matching_service.py::test_matching_fills_etf_order_from_raw_etf_daily_without_adjusted_fallback -v`

  Expected: PASS. The order persists as `etf`, the matching run fills it, `storage.etf_daily_calls` is non-empty, and adjusted ETF/A-share history call collections remain empty.

- [ ] **Step 3: Run focused matching and market-data regression suites**

  Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_market_data.py -v`

  Expected: PASS, preserving both the raw ETF-only route and existing A-share/Hong Kong Stock Connect market-data routing.

- [ ] **Step 4: Inspect the matching-test diff before continuing**

  Run: `git diff --check -- test/paper_trading/services/test_matching_service.py`

  Expected: PASS with no whitespace errors. Do not commit unless the user
  explicitly requests it.

### Task 4: Verify The Completed Surface

**Files:**
- Modify only if verification identifies a defect: `paper_trading/services/order_service.py`, `test/paper_trading/services/test_order_service.py`, or `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_order_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/storage/test_market_data.py`

**Interfaces:**
- Consumes: catalogue-backed order classification, existing ETF eligibility, and existing raw ETF data routing.
- Produces: formatting, lint, type, focused-regression, and PostgreSQL-integrated test evidence for issue #55.

- [ ] **Step 1: Format the touched Python files**

  Run: `uv run ruff format paper_trading/services/order_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py`

  Expected: Ruff reports files formatted or already formatted.

- [ ] **Step 2: Run focused behavioral regression suites**

  Run: `uv run pytest test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_market_data.py -v`

  Expected: PASS. This proves catalogue classification, eligibility preservation, raw ETF matching, and market-data no-fallback behavior.

- [ ] **Step 3: Run lint and type checks for the changed surface**

  Run: `uv run ruff check paper_trading/services/order_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py`

  Expected: PASS.

  Run: `uv run mypy`

  Expected: PASS.

- [ ] **Step 4: Run PostgreSQL-integrated test coverage**

  Run: `tools/run_tests.sh test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_market_data.py -v`

  Expected: PASS. The runner starts the isolated PostgreSQL service and validates the changed Paper Trading workflow against the repository's integration environment.

- [ ] **Step 5: Inspect the final diff for scope and whitespace**

  Run: `git diff --check`

  Expected: PASS with no whitespace errors.

  Run: `git diff -- paper_trading/services/order_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py`

  Expected: the only production change resolves a valid or omitted catalogue-backed ETF market to `Market.ETF`; no API, CLI, schema, eligibility-policy, fee, settlement, or market-data-routing behavior changes appear.

- [ ] **Step 6: Report verification results and leave implementation changes unstaged**

  Report every command's exit status and any blockers. Do not stage or commit
  implementation files unless the user explicitly requests a commit.
