# Paper Trading ETF Market Data Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route paper-trading ETF bars and close valuation exclusively to the existing ETF daily-data pipeline, retaining recoverable missing-bar retries.

**Architecture:** Add an explicit `etf` branch to `StorageMarketDataProvider` for exact-date OHLC bars and latest closes, using the ETF storage helper with its existing QFQ adjustment basis. Remove the A-share-only restriction from market-qualified delayed-bar rebuild selection, and make request-time ETF valuation skip the A-share real-time quote adapter so it falls back to the ETF daily close.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy, pytest, Ruff, mypy, uv.

## Global Constraints

- ETF daily bars and latest daily closes read from `etf_daily` and use one price-adjustment basis for matching and valuation.
- ETF market-data reads never fall back to A-share stock history or `fund_daily` data.
- ETF valuation and snapshots use ETF daily closes and retain ETF market identity.
- An exact-date missing ETF bar leaves an accepted order retryable and records a market-qualified diagnostic and warning.
- Do not change ETF eligibility, order acceptance, fees, quantity or tick rules, T+1 sellability, DAG schedules, dependencies, retries, task boundaries, or SLA.
- Preserve existing A-share and Hong Kong Stock Connect behavior.
- Use `uv run` for every Python command.
- Do not commit unless the user explicitly requests a commit.

---

## File Structure

- `paper_trading/storage/market_data.py`: Explicitly route `market="etf"` daily-bar and latest-close requests to ETF storage without price-limit lookup.
- `paper_trading/storage/repository.py`: Return any accepted order with an unresolved market-qualified missing-exact-date diagnostic for delayed rebuild, including ETFs.
- `paper_trading/services/position_valuation_service.py`: Exclude ETF positions from the A-share/HK live-quote batch and use the ETF daily-close fallback.
- `test/paper_trading/fakes.py`: Add ETF-history and latest-ETF-close fakes plus call capture needed by provider tests.
- `test/paper_trading/storage/test_market_data.py`: Verify provider routing, adjustment basis, no-fallback behavior, and missing ETF data semantics.
- `test/paper_trading/storage/test_repository.py`: Verify ETF accepted orders are eligible for missing-bar rebuild selection.
- `test/paper_trading/services/test_matching_service.py`: Verify ETF matching warning diagnostics and subsequent retry/fill behavior.
- `test/paper_trading/services/test_snapshot_service.py`: Verify ETF snapshot values positions from ETF bars and preserves ETF valuation-gap identity.
- `test/paper_trading/services/test_position_valuation_service.py`: Verify ETF request-time valuation bypasses live A-share quotes and reads the ETF daily close.

### Task 1: Route ETF Daily Bars And Latest Closes To ETF Storage

**Files:**
- Modify: `paper_trading/storage/market_data.py:66-127`
- Modify: `test/paper_trading/fakes.py:11-37`
- Modify: `test/paper_trading/storage/test_market_data.py`

**Interfaces:**
- Consumes: `StorageDB.load_history_data_etf(etf_id, period, adjust, start_date, end_date)` and `DailyBar`.
- Produces: `StorageMarketDataProvider.get_daily_bar(symbol, trade_date, market="etf") -> DailyBar` and `get_latest_daily_close(symbol, trade_date, market="etf") -> Decimal | None`, both using `AdjustType.QFQ` ETF history.

- [ ] **Step 1: Write failing ETF provider-routing tests**

```python
def test_etf_daily_bar_reads_etf_history_without_stock_or_limit_queries():
    trade_date = date(2026, 8, 10)
    storage = FakeHistoryStorage(
        {},
        etf_data={
            "510300": pd.DataFrame(
                {
                    COL_STOCK_ID: ["510300"],
                    COL_DATE: [trade_date.isoformat()],
                    COL_OPEN: [3.001],
                    COL_HIGH: [3.125],
                    COL_LOW: [2.999],
                    COL_CLOSE: [3.100],
                }
            )
        },
    )
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([trade_date]))

    bar = provider.get_daily_bar("510300", trade_date, market="etf")

    assert bar == DailyBar("510300", trade_date, Decimal("3.001"), Decimal("3.125"), Decimal("2.999"), Decimal("3.1"))
    assert storage.etf_calls == [("510300", PeriodType.DAILY, AdjustType.QFQ, "2026-08-10", "2026-08-10")]
    assert storage.calls == []
    assert storage.hk_calls == []


def test_etf_latest_close_reads_qfq_etf_history_without_stock_fallback():
    trade_date = date(2026, 8, 10)
    storage = FakeHistoryStorage({}, etf_data={"510300": _etf_frame("510300", "2026-08-08", 3.1)})
    provider = StorageMarketDataProvider(storage, FakeTradeCalendar([trade_date]))

    assert provider.get_latest_daily_close("510300", trade_date, market="etf") == Decimal("3.1")
    assert storage.etf_calls == [("510300", PeriodType.DAILY, AdjustType.QFQ, None, "2026-08-10")]
    assert storage.calls == []
    assert storage.hk_calls == []


def test_missing_etf_bar_raises_without_stock_or_fund_fallback():
    provider = StorageMarketDataProvider(FakeHistoryStorage({}, etf_data={}), FakeTradeCalendar([]))

    with pytest.raises(KeyError, match="No ETF daily bar for 510300"):
        provider.get_daily_bar("510300", date(2026, 8, 10), market="etf")
```

- [ ] **Step 2: Run the focused provider tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_market_data.py -v`

Expected: FAIL because ETF requests take the current A-share path and `FakeHistoryStorage` has no ETF-history interface.

- [ ] **Step 3: Extend the test fake with ETF-specific history loading**

```python
class FakeHistoryStorage:
    def __init__(self, data: dict[str, pd.DataFrame], etf_data: dict[str, pd.DataFrame] | None = None):
        self._data = data
        self._etf_data = etf_data or {}
        self.calls: list[tuple[Any, ...]] = []
        self.hk_calls: list[tuple[Any, ...]] = []
        self.etf_calls: list[tuple[Any, ...]] = []

    def load_history_data_etf(self, etf_id, period, adjust, start_date=None, end_date=None):
        self.etf_calls.append((etf_id, period, adjust, start_date, end_date))
        df = self._etf_data.get(etf_id, pd.DataFrame()).copy()
        if start_date:
            df = df[df[COL_DATE] >= start_date]
        if end_date:
            df = df[df[COL_DATE] <= end_date]
        return df
```

- [ ] **Step 4: Add ETF routing branches to `StorageMarketDataProvider`**

```python
def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
    stock_id = self._to_storage_stock_id(symbol)
    if market == "hk_connect":
        return self._get_hk_daily_bar(stock_id, symbol, trade_date)
    if market == "etf":
        return self._get_etf_daily_bar(stock_id, symbol, trade_date)
    return self._get_a_share_daily_bar(stock_id, symbol, trade_date)

def _get_etf_daily_bar(self, etf_id: str, symbol: str, trade_date: date) -> DailyBar:
    df = self._storage.load_history_data_etf(
        etf_id, PeriodType.DAILY, AdjustType.QFQ, trade_date.isoformat(), trade_date.isoformat()
    )
    if df.empty:
        raise KeyError(f"No ETF daily bar for {symbol} on {trade_date.isoformat()}")
    row = df.iloc[-1]
    return DailyBar(
        symbol=symbol,
        trade_date=trade_date,
        open=self._decimal_field(row, COL_OPEN, symbol, trade_date),
        high=self._decimal_field(row, COL_HIGH, symbol, trade_date),
        low=self._decimal_field(row, COL_LOW, symbol, trade_date),
        close=self._decimal_field(row, COL_CLOSE, symbol, trade_date),
    )
```

Implement ETF latest close by loading ETF QFQ daily data through `trade_date`, returning `None` when the frame is empty and extracting `COL_CLOSE` from its final row. Do not call `_load_limit_prices`, `load_history_data_stock`, or any `fund_daily` access for this market.

- [ ] **Step 5: Run provider tests and related existing market-data tests**

Run: `uv run pytest test/paper_trading/storage/test_market_data.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -v`

Expected: PASS, including existing A-share and HK Connect storage routing assertions.

### Task 2: Allow Market-Qualified ETF Missing-Bar Rebuilds

**Files:**
- Modify: `paper_trading/storage/repository.py:215-233`
- Modify: `test/paper_trading/storage/test_repository.py`
- Modify: `test/paper_trading/services/test_matching_service.py`

**Interfaces:**
- Consumes: persisted `PaperOrder.market`, `DailyBarDiagnostic.market`, and existing rebuild router behavior.
- Produces: `PaperTradingRepository.list_eligible_daily_bar_rebuild_orders() -> list[PaperOrder]` that includes accepted ETF orders with an unresolved matching `missing_exact_date` diagnostic.

- [ ] **Step 1: Write failing repository selection coverage for ETF**

```python
def test_eligible_daily_bar_rebuild_orders_include_etf_missing_exact_date(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("etf-retry", Decimal("100000"))
    order = repo.create_order(
        account.id,
        "510300",
        OrderSide.BUY,
        100,
        Decimal("3.100"),
        date(2026, 8, 10),
        OrderStatus.ACCEPTED,
        market=Market.ETF,
    )
    repo.upsert_daily_bar_diagnostic(
        order.trade_date, Market.ETF, order.symbol, "bfq", "missing_exact_date", [], resolved=False
    )

    assert [item.id for item in repo.list_eligible_daily_bar_rebuild_orders()] == [order.id]
```

- [ ] **Step 2: Run the selection test to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_repository.py::test_eligible_daily_bar_rebuild_orders_include_etf_missing_exact_date -v`

Expected: FAIL because `list_eligible_daily_bar_rebuild_orders` filters `PaperOrder.market == "a_share"`.

- [ ] **Step 3: Remove only the A-share market predicate**

```python
.filter(
    PaperOrder.status == OrderStatus.ACCEPTED.value,
    DailyBarDiagnostic.resolved.is_(False),
    DailyBarDiagnostic.classification == "missing_exact_date",
)
```

Keep the existing date, market, symbol, and adjustment join conditions intact so an ETF diagnostic cannot make an A-share or HK order eligible.

- [ ] **Step 4: Write a matching retry test that uses ETF market identity**

```python
def test_matching_etf_missing_bar_warns_then_same_date_retry_fills(tmp_path):
    engine, session, repo, order_service, _, trade_date = _services(tmp_path)
    account = repo.create_account("etf-retry", Decimal("100000.00"))
    order = order_service.place_order(
        account.id, "510300", OrderSide.BUY, 100, Decimal("3.100"), trade_date, market=Market.ETF
    )
    market_data = RetryETFMarketData()
    matching = MatchingService(repo, market_data, SnapshotService(repo, market_data))

    assert matching.match_order(order) == "warning"
    diagnostic = repo.list_daily_bar_diagnostics()[0]
    assert (diagnostic.market, diagnostic.stock_id, diagnostic.classification) == ("etf", "510300", "missing_exact_date")
    market_data.available = True
    assert matching.match_order(order) == "filled"
    assert repo.get_order(order.id).status == OrderStatus.FILLED.value
```

Make `RetryETFMarketData.get_daily_bar` assert `market == "etf"`, raise `KeyError` while unavailable, and return a bar whose low/high includes `3.100` after availability is enabled.

- [ ] **Step 5: Run repository and matching retry coverage**

Run: `uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_matching_service.py -v`

Expected: PASS; the accepted ETF order remains accepted during its first missing-bar attempt and fills on retry with an ETF-qualified diagnostic.

### Task 3: Keep ETF Snapshot And Request-Time Valuation On ETF Closes

**Files:**
- Modify: `paper_trading/services/position_valuation_service.py:34-64`
- Modify: `test/paper_trading/services/test_snapshot_service.py`
- Modify: `test/paper_trading/services/test_position_valuation_service.py`

**Interfaces:**
- Consumes: Task 1 `StorageMarketDataProvider` ETF routing and existing market-qualified positions.
- Produces: ETF snapshots through `get_daily_bar(..., market="etf")`; ETF request-time `PositionValuationService` calls `get_latest_daily_close(..., market="etf")` without passing ETF symbols to `fetch_price_map` as A-share quotes.

- [ ] **Step 1: Write failing snapshot routing and gap tests**

```python
def test_snapshot_values_etf_position_from_etf_daily_bar(tmp_path):
    # Build an ETF position with 100 units and ETF QFQ close 3.100.
    snapshot = SnapshotService(repo, StorageMarketDataProvider(storage, calendar)).generate_snapshot(account.id, trade_date)

    assert snapshot.market_value == Decimal("310.0000")
    assert storage.etf_calls == [("510300", PeriodType.DAILY, AdjustType.QFQ, "2026-08-10", "2026-08-10")]
    assert storage.calls == []


def test_missing_etf_snapshot_bar_creates_etf_qualified_valuation_gap(sqlite_session):
    repo.upsert_position(account.id, Market.ETF, "510300", 100, 0, Decimal("300.00"))
    outcome = SnapshotService(repo, MissingETFBarProvider()).generate_snapshot_or_gap(account.id, trade_date)

    assert outcome.status == "valuation_gap"
    assert outcome.valuation_gap.details == [
        {"symbol": "510300", "market": "etf", "error": "'No ETF daily bar for 510300 on 2026-08-10'"}
    ]
```

- [ ] **Step 2: Write a failing request-time ETF valuation test**

```python
def test_etf_valuation_bypasses_a_share_live_quotes_and_uses_etf_daily_close():
    market_data = _FakeMarketData({("510300", "etf"): Decimal("3.10")})
    live_calls = []
    service = PositionValuationService(
        market_data,
        fetch_prices=lambda items: live_calls.append(list(items)) or {},
        today=date(2026, 8, 10),
    )

    result = service.value(_position(symbol="510300", market="etf", total_quantity=100, cost_amount=Decimal("300")))

    assert live_calls == []
    assert result.mark_price == Decimal("3.10")
    assert result.price_source == "db_close"
    assert market_data.calls == [("510300", date(2026, 8, 10), "etf")]
```

- [ ] **Step 3: Run snapshot and valuation tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_position_valuation_service.py -v`

Expected: FAIL because ETF storage routing does not exist before Task 1 and `PositionValuationService._source_market("etf")` currently returns `"A"`.

- [ ] **Step 4: Filter live quote inputs to A-share and HK Connect only**

```python
def value_many(self, positions: Iterable) -> list[PositionValuation]:
    rows = list(positions)
    prices: dict[tuple[str, str], object] = {}
    quote_rows = [row for row in rows if row.market in {"a_share", "hk_connect"}]
    if quote_rows:
        try:
            items = [(row.symbol, self._source_market(row.market)) for row in quote_rows]
            prices = dict(self.fetch_prices(items))
        except Exception:
            prices = {}
    return [self._value_with_price(row, prices) for row in rows]
```

Keep `_db_close(position.symbol, position.market)` unchanged: Task 1 provides ETF-specific close routing. Preserve existing A-share/HK real-time quote behavior and failure isolation.

- [ ] **Step 5: Run the snapshot and valuation suites**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_position_valuation_service.py -v`

Expected: PASS; ETF snapshots and request-time valuation read ETF data, and absent ETF snapshot bars persist an ETF-qualified valuation gap.

### Task 4: Run Focused Regression And Quality Verification

**Files:**
- Modify only if verification exposes an issue: files from Tasks 1-3.
- Test: `test/paper_trading/storage/test_market_data.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`
- Test: `test/paper_trading/services/test_position_valuation_service.py`

**Interfaces:**
- Consumes: completed ETF routing, missing-bar selection, and valuation behavior.
- Produces: formatting, lint, type, and regression evidence for issue #45.

- [ ] **Step 1: Format changed Python files**

Run: `uv run ruff format paper_trading/storage/market_data.py paper_trading/storage/repository.py paper_trading/services/position_valuation_service.py test/paper_trading/fakes.py test/paper_trading/storage/test_market_data.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_position_valuation_service.py`

Expected: Ruff reports formatted files or no changes needed.

- [ ] **Step 2: Run focused ETF and regression tests**

Run: `uv run pytest test/paper_trading/storage/test_market_data.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_position_valuation_service.py -v`

Expected: PASS.

- [ ] **Step 3: Run lint and type checks for the touched surface**

Run: `uv run ruff check paper_trading/storage/market_data.py paper_trading/storage/repository.py paper_trading/services/position_valuation_service.py test/paper_trading/fakes.py test/paper_trading/storage/test_market_data.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_position_valuation_service.py`

Run: `uv run mypy`

Expected: both commands exit zero.

- [ ] **Step 4: Inspect final changes for accidental fallback or scope expansion**

Run: `git diff --check`

Run: `git diff -- paper_trading/storage/market_data.py paper_trading/storage/repository.py paper_trading/services/position_valuation_service.py test/paper_trading`

Expected: no whitespace errors; ETF paths use only `load_history_data_etf(..., AdjustType.QFQ, ...)`; no eligibility, fee, order-rule, or DAG changes are present.


Only run this step if Task 4 required a corrective code or test change not included in Tasks 1-3. Do not create an empty commit.
