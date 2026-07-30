# Resilient A-Share EOD Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make A-share daily-history processing business-date correct and warning-tolerant while queueing explicit-date paper orders and safely batch-matching symbols with exact-date BFQ bars.

**Architecture:** The daily-history DAG derives a Shanghai business date from Airflow logical time and returns typed partition outcomes instead of formatted strings. A persistent diagnostic record captures per-symbol provider evidence; the aggregate writes a compatible Redis success/warning result and invokes batch matching for the same date. Paper-trading orders queue until that batch run, whose repository-level serialization and row locking prevent duplicate fills while missing exact-date bars leave only affected orders accepted.

**Tech Stack:** Python 3.11+, Apache Airflow 2.9, SQLAlchemy, PostgreSQL/TimescaleDB, FastAPI, Pydantic, Redis, pytest, Ruff, mypy, uv.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Use `logical_date.in_timezone(LOCAL_TZ).date()` as the only A-share business-date source in the weekday daily-history workflow; do not use wall-clock `datetime.now()` for download, summary, or matching dates.
- Skip the entire A-share workflow on a closed XSHG business date; do not emit a successful summary or run matching.
- Keep `result=success` in warning-only Redis payloads and add explicit warning metadata rather than changing existing consumers to a new result value.
- Missing exact-date daily data leaves an order `ACCEPTED`; no stale price may be used as an execution price.
- Do not infer confirmed full-day suspension from TuShare `suspend_d`; automatic suspension rejection is out of scope.
- Preserve market-specific calendar behavior; do not use XSHG for Hong Kong Connect settlement date calculation.
- Add any new business table to `tools/db_common.sh` export/import lists.
- Do not create git commits unless the user explicitly requests them.

---

## File Map

| Area | Files | Responsibility after this work |
| --- | --- | --- |
| Daily-history orchestration | `dags/download_stock_history_daily.py`, `stock/market.py`, `download/download_manager.py` | Derive logical business date, gate closed dates, classify per-symbol provider outcomes, aggregate warning summaries, and invoke matching. |
| Daily-bar diagnostics | `storage/model/paper_trading.py`, `storage/model/__init__.py`, `paper_trading/storage/models.py`, `storage/storage_db.py`, `paper_trading/storage/repository.py`, `tools/db_common.sh` | Persist, query, and export business-date/symbol/adjustment diagnostic evidence. |
| Order queueing | `paper_trading/schemas/orders.py`, `paper_trading/services/order_service.py`, `paper_trading/storage/repository.py`, `paper_trading/api/routers/orders.py` | Require explicit eligible trade date, replay idempotency keys, reserve assets, and remove immediate matching. |
| Batch matching | `storage/model/paper_trading.py`, `storage/storage_db.py`, `paper_trading/storage/repository.py`, `paper_trading/services/matching_service.py`, `paper_trading/api/routers/matching.py`, `paper_trading/schemas/matching.py` | Serialize duplicate matching requests, lock accepted orders, retain missing-data orders, and expose warning outcomes. |
| Snapshot outcomes | `storage/model/paper_trading.py`, `storage/storage_db.py`, `paper_trading/storage/repository.py`, `paper_trading/services/snapshot_service.py`, `paper_trading/services/matching_service.py` | Persist an explicit valuation-gap outcome when exact-date position valuation is unavailable. |
| Tests | `test/dags/test_partition_dag_sources.py`, `test/download/test_download_manager.py`, `test/paper_trading/api/test_orders_api.py`, `test/paper_trading/api/test_matching_api.py`, `test/paper_trading/services/test_matching_service.py`, `test/paper_trading/services/test_snapshot_service.py`, `test/paper_trading/storage/test_market_data.py`, `test/paper_trading/storage/test_repository.py`, `test/storage/test_storage_db.py` | Cover public workflow/API behavior and focused persistence contracts. |

## Shared Interfaces

Implement these names before dependent tasks refer to them:

```python
@dataclass(frozen=True)
class ProviderOutcome:
    provider: str
    status: Literal["downloaded", "empty", "error"]
    detail: str | None = None

@dataclass(frozen=True)
class StockHistoryOutcome:
    stock_id: str
    adjust: AdjustType
    status: Literal["downloaded", "missing_market_data", "provider_error"]
    provider_outcomes: tuple[ProviderOutcome, ...]

@dataclass(frozen=True)
class PartitionHistoryOutcome:
    partition_id: int
    adjust: AdjustType
    business_date: date
    total: int
    downloaded_ids: tuple[str, ...]
    missing_market_data_ids: tuple[str, ...]
    provider_error_ids: tuple[str, ...]
```

The diagnostics persistence contract is:

```python
def upsert_daily_bar_diagnostic(
    *,
    business_date: date,
    stock_id: str,
    adjust: str,
    classification: str,
    provider_outcomes: list[dict[str, str | None]],
    resolved: bool,
) -> DailyBarDiagnostic: ...
```

The repository contracts required by matching are:

```python
def get_order_by_idempotency_key(self, idempotency_key: str) -> PaperOrder | None: ...

def get_orders_for_matching_locked(
    self, trade_date: date, account_id: int | None = None
) -> list[PaperOrder]: ...

def acquire_matching_run(
    self, trade_date: date, account_id: int | None = None
) -> PaperMatchingRun: ...
```

`acquire_matching_run` returns an existing queued/running run for the same scope or creates one atomically. Its caller executes only when it owns the run; a caller receiving a queued/running run returns that run without processing orders.

### Task 1: Implement business-date daily-history execution (#5)

**Files:**
- Modify: `dags/download_stock_history_daily.py:46-203`
- Modify: `stock/market.py:11-92`
- Test: `test/dags/test_partition_dag_sources.py`
- Test: `test/stock/test_market.py`

**Consumes:** `LOCAL_TZ`, Airflow task context, existing XSHG trading-calendar utilities, existing `DownloadManager.download_stock_history`.

**Produces:** `get_business_date(context) -> date`, `ensure_a_share_trade_date(context) -> date`, and partition calls that receive one explicit `business_date` rather than selecting `datetime.now()`.

- [ ] **Step 1: Add failing business-date helper tests**

Add tests that construct a logical datetime at `2026-07-28T08:00:00+00:00`, assert the helper returns `date(2026, 7, 28)` in `LOCAL_TZ`, and assert a delayed execution does not affect it:

```python
def test_business_date_uses_logical_date_in_local_timezone():
    context = {"logical_date": pendulum.datetime(2026, 7, 28, 8, tz="UTC")}
    assert get_business_date(context) == date(2026, 7, 28)


def test_partition_uses_business_date_not_wall_clock(monkeypatch):
    monkeypatch.setattr(dag_module, "get_business_date", lambda context: date(2026, 7, 28))
    # Assert DownloadManager receives end_date="2026-07-28".
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `uv run pytest test/dags/test_partition_dag_sources.py test/stock/test_market.py -q`

Expected: failure because the business-date helper and logical-date wiring do not exist.

- [ ] **Step 3: Implement business-date and closed-date gating**

Add a small DAG-local helper that reads `context["logical_date"]`, converts it with `in_timezone(LOCAL_TZ)`, and returns `.date()`. Add a date-parameterized XSHG calendar predicate in `stock.market` rather than calling `is_a_market_open_today()`. At the top of each partition and aggregate/matching callable, call the gate and raise `AirflowSkipException` for a closed business date.

```python
def get_business_date(context: dict[str, Any]) -> date:
    return context["logical_date"].in_timezone(LOCAL_TZ).date()


def ensure_a_share_trade_date(context: dict[str, Any]) -> date:
    business_date = get_business_date(context)
    if not is_a_share_trade_date(business_date):
        raise AirflowSkipException(f"A股{business_date.isoformat()}休市，跳过任务")
    return business_date
```

Pass `business_date.isoformat()` as both partition end date and downstream aggregate/matching date. Do not alter HFQ/BFQ start dates.

- [ ] **Step 4: Add closed-date and delayed-run workflow assertions**

Add one test that fakes a closed calendar date and expects `AirflowSkipException`; add one source/behavior assertion that verifies `datetime.now()` is absent from daily-history business-date selection.

- [ ] **Step 5: Run focused verification**

Run: `uv run pytest test/dags/test_partition_dag_sources.py test/stock/test_market.py -q`

Expected: PASS.

- [ ] **Step 6: Run formatting and type checks for changed modules**

Run: `uv run ruff format dags/download_stock_history_daily.py stock/market.py test/dags/test_partition_dag_sources.py test/stock/test_market.py && uv run ruff check dags/download_stock_history_daily.py stock/market.py test/dags/test_partition_dag_sources.py test/stock/test_market.py`

Expected: formatter completes and Ruff reports no violations.

### Task 2: Persist daily-bar provider diagnostics (#6)

**Files:**
- Modify: `storage/model/paper_trading.py:18-28,218-245`
- Modify: `storage/model/__init__.py:40-62`
- Modify: `paper_trading/storage/models.py:1-49`
- Modify: `storage/storage_db.py:367-412,2364-2394`
- Modify: `paper_trading/storage/repository.py:1-40,384-531`
- Modify: `tools/db_common.sh:36-45`
- Create: `paper_trading/domain/market_data_diagnostics.py`
- Test: `test/paper_trading/storage/test_models.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/storage/test_storage_db.py`

**Consumes:** existing SQLAlchemy `Base`, paper-trading storage bootstrap, `AdjustType` names, and shared storage exports.

**Produces:** `DailyBarDiagnostic`, `ProviderOutcome`, `StockHistoryOutcome`, repository upsert/list methods, and an existing-database schema upgrade.

- [ ] **Step 1: Write model and repository contract tests**

Add tests proving a diagnostic is unique per business date, stock ID, and adjustment; a second observation updates classification/provider evidence and resolution state rather than adding a duplicate; and a fresh storage bootstrap creates the table.

```python
def test_upsert_daily_bar_diagnostic_reuses_business_date_symbol_adjustment(session):
    first = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28), stock_id="300996", adjust="bfq",
        classification="missing_market_data", provider_outcomes=[{"provider": "tushare", "status": "empty", "detail": None}],
        resolved=False,
    )
    second = repo.upsert_daily_bar_diagnostic(
        business_date=date(2026, 7, 28), stock_id="300996", adjust="bfq",
        classification="downloaded", provider_outcomes=[{"provider": "tushare", "status": "downloaded", "detail": None}],
        resolved=True,
    )
    assert second.id == first.id
    assert second.resolved is True
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q`

Expected: failure because the diagnostic model and repository methods do not exist.

- [ ] **Step 3: Add immutable outcome value objects**

Create `paper_trading/domain/market_data_diagnostics.py` with the shared dataclasses from the plan header. Validate that provider status is one of `downloaded`, `empty`, or `error`; normalize absent details to `None`. Keep them storage-agnostic so DAG and matching code can use them without importing SQLAlchemy models.

- [ ] **Step 4: Add diagnostic persistence and upgrade support**

Add `DailyBarDiagnostic` with columns for business date, normalized stock ID, adjustment, classification, JSON provider outcomes, first/last observed timestamps, resolved flag, and a unique constraint over `(business_date, stock_id, adjust)`. Export it through both model export modules. Add `ensure_paper_trading_schema()` migration logic that creates missing tables/indexes safely for an existing database. Add the table name to `tools/db_common.sh`.

Implement `upsert_daily_bar_diagnostic()` in the repository using the unique business key: update the existing row’s classification, provider evidence, last-observed timestamp, and resolution state; otherwise insert a new row.

- [ ] **Step 5: Add schema-upgrade and export-list tests**

Test that `ensure_paper_trading_schema()` creates the diagnostic table from an existing schema and that the database table list includes it. Test all-empty, mixed empty/error, and resolved fallback records through repository reads.

- [ ] **Step 6: Run focused verification**

Run: `uv run pytest test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q`

Expected: PASS.

- [ ] **Step 7: Run formatting and lint verification**

Run: `uv run ruff format storage/model/paper_trading.py storage/model/__init__.py paper_trading/storage/models.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/domain/market_data_diagnostics.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py && uv run ruff check storage/model/paper_trading.py storage/model/__init__.py paper_trading/storage/models.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/domain/market_data_diagnostics.py test/paper_trading/storage/test_models.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py`

Expected: formatter completes and Ruff reports no violations.

### Task 3: Queue explicit-date paper-trading orders (#7)

**Files:**
- Modify: `paper_trading/schemas/orders.py:9-17`
- Modify: `paper_trading/storage/repository.py:278-374`
- Modify: `paper_trading/services/order_service.py:42-218`
- Modify: `paper_trading/api/routers/orders.py:32-60`
- Test: `test/paper_trading/api/test_orders_api.py`
- Test: `test/paper_trading/services/test_order_service.py`
- Test: `test/paper_trading/storage/test_repository.py`

**Consumes:** existing accepted-order reservation behavior and market calendar provider.

**Produces:** explicit-date validation, idempotent order replay, and order creation with no immediate matching side effect.

- [ ] **Step 1: Write failing API tests for queueing and idempotency**

Add tests that submit a valid explicit trade date, assert the response is `accepted`, assert no trade and no matching run exist, then repeat with the same idempotency key and assert the original order ID and reservation count are returned.

```python
def test_create_order_queues_without_matching(client, session):
    response = client.post("/paper/accounts/1/orders", json=valid_order_payload(trade_date="2026-07-28"))
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert trade_count(session) == 0
    assert matching_run_count(session) == 0


def test_create_order_idempotency_replays_original_order(client, session):
    payload = valid_order_payload(idempotency_key="order-20260728-1")
    first = client.post("/paper/accounts/1/orders", json=payload)
    second = client.post("/paper/accounts/1/orders", json=payload)
    assert second.json()["id"] == first.json()["id"]
    assert cash_freeze_count(session) == 1
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `uv run pytest test/paper_trading/api/test_orders_api.py test/paper_trading/services/test_order_service.py test/paper_trading/storage/test_repository.py -q`

Expected: queueing test fails because the router immediately matches; replay test fails with an integrity error or duplicate path.

- [ ] **Step 3: Implement request and service validation**

Require non-null `trade_date` in the schema and retain service-layer market-calendar validation. In `OrderService.place_order()`, look up a nonblank idempotency key before account mutation or reservation creation. If an existing order has the same immutable request attributes, return it; if attributes differ, raise a domain validation error that maps to a client error.

```python
existing = self.repo.get_order_by_idempotency_key(idempotency_key)
if existing is not None:
    if self._matches_order_request(existing, account_id, symbol, side, quantity, limit_price, trade_date, market):
        return existing
    raise PaperTradingError("idempotency key already belongs to a different order")
```

Keep the existing database unique constraint as a race backstop and catch/re-fetch on a concurrent insert collision.

- [ ] **Step 4: Remove immediate matching from the order endpoint**

Delete the `MatchingService.run()` branch from the create-order router. Keep the transaction commit and response model unchanged so clients receive the reserved `ACCEPTED` order.

- [ ] **Step 5: Add historical retry-date and invalid-date tests**

Use the fake market calendar to assert a closed trade date is rejected; assert an eligible unresolved historical retry date is accepted; assert a past date without retry eligibility is rejected according to the new service policy.

- [ ] **Step 6: Run focused verification**

Run: `uv run pytest test/paper_trading/api/test_orders_api.py test/paper_trading/services/test_order_service.py test/paper_trading/storage/test_repository.py -q`

Expected: PASS.

- [ ] **Step 7: Run formatting, lint, and targeted typing**

Run: `uv run ruff format paper_trading/schemas/orders.py paper_trading/storage/repository.py paper_trading/services/order_service.py paper_trading/api/routers/orders.py test/paper_trading/api/test_orders_api.py test/paper_trading/services/test_order_service.py test/paper_trading/storage/test_repository.py && uv run ruff check paper_trading/schemas/orders.py paper_trading/storage/repository.py paper_trading/services/order_service.py paper_trading/api/routers/orders.py test/paper_trading/api/test_orders_api.py test/paper_trading/services/test_order_service.py test/paper_trading/storage/test_repository.py && uv run mypy paper_trading`

Expected: formatter completes, Ruff reports no violations, and mypy reports no new errors in `paper_trading`.

### Task 4: Publish warning-tolerant daily-history summaries (#8)

**Files:**
- Modify: `download/download_manager.py:205-365`
- Modify: `dags/download_stock_history_daily.py:46-192`
- Modify: `paper_trading/storage/repository.py`
- Test: `test/download/test_download_manager.py`
- Test: `test/dags/test_partition_dag_sources.py`

**Consumes:** Task 1 business-date helpers and Task 2 outcome dataclasses/diagnostic repository API.

**Produces:** structured partition XCom payloads, persisted provider diagnostics, and compatible Redis `success`/`warning` aggregation.

- [ ] **Step 1: Write failing outcome-classification tests**

Add a manager-level test with providers returning empty frames and errors, asserting a `StockHistoryOutcome` contains provider evidence and is classified as `missing_market_data` for all-empty or `provider_error` for any error with no successful fallback. Add a DAG aggregate test with serialized partition outcomes that asserts warning payload fields.

```python
def test_all_empty_providers_create_missing_market_data_outcome(monkeypatch):
    outcome = manager.download_stock_history_outcome("300996", PeriodType.DAILY, "20260728", "20260728", AdjustType.BFQ)
    assert outcome.status == "missing_market_data"
    assert {item.status for item in outcome.provider_outcomes} == {"empty"}


def test_warning_aggregate_keeps_success_result(redis_client):
    summary = save_download_result_to_redis(partition_count=1, ti=fake_ti_with_warning_outcome)
    assert redis_client.get_json(REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY)["result"] == "success"
    assert redis_client.get_json(REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY)["status"] == "warning"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest test/download/test_download_manager.py test/dags/test_partition_dag_sources.py -q`

Expected: failure because the manager returns `bool` only and the aggregate parses formatted strings.

- [ ] **Step 3: Implement a non-breaking outcome API**

Keep `download_stock_history()` as the legacy boolean wrapper for existing callers. Add `download_stock_history_outcome()` that reuses provider fallback internals while collecting each provider outcome. A successful fallback returns `downloaded`; all-empty returns `missing_market_data`; a no-success mix containing an error returns `provider_error`; persistence failure raises rather than becoming a warning.

In each DAG partition, call the outcome API for every symbol, persist non-downloaded diagnostics through the Task 2 repository API, and return a JSON-serializable `PartitionHistoryOutcome` dictionary. Do not raise for warning classifications; raise for fatal exceptions.

- [ ] **Step 4: Implement aggregate warning payload**

Aggregate structured XCom dictionaries for both adjustments. Write a payload with this stable shape:

```python
{
    "date": business_date.isoformat(),
    "result": "success",
    "status": "warning" if warning_symbols else "success",
    "missing_symbols": sorted(warning_symbols),
    "provider_evidence": bounded_evidence,
}
```

Use the Task 1 business date. Bound evidence to a documented deterministic maximum, such as the first 20 sorted symbol/adjustment records, so Redis remains small. Preserve a `fail` result only for a fatal aggregate/persistence condition.

- [ ] **Step 5: Add full behavioral coverage**

Test successful fallback yields no warning, all-empty yields warning, mixed provider error yields warning with evidence, and diagnostic persistence failure fails the partition/aggregate rather than emitting `success`.

- [ ] **Step 6: Run focused verification**

Run: `uv run pytest test/download/test_download_manager.py test/dags/test_partition_dag_sources.py -q`

Expected: PASS.

- [ ] **Step 7: Run formatting and lint verification**

Run: `uv run ruff format download/download_manager.py dags/download_stock_history_daily.py test/download/test_download_manager.py test/dags/test_partition_dag_sources.py && uv run ruff check download/download_manager.py dags/download_stock_history_daily.py test/download/test_download_manager.py test/dags/test_partition_dag_sources.py`

Expected: formatter completes and Ruff reports no violations.

### Task 5: Safely batch-match queued paper orders (#9)

**Files:**
- Modify: `storage/model/paper_trading.py:218-232`
- Modify: `storage/storage_db.py:2364-2394`
- Modify: `paper_trading/storage/repository.py:315-374,496-531`
- Modify: `paper_trading/services/matching_service.py:35-119`
- Modify: `paper_trading/api/routers/matching.py:15-39`
- Modify: `paper_trading/schemas/matching.py:6-23`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/api/test_matching_api.py`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/storage/test_storage_db.py`

**Consumes:** Task 2 diagnostic repository API and Task 3 queued accepted orders.

**Produces:** serialized matching runs, locked accepted-order processing, missing-data warning counts, and safe same-date retries.

- [ ] **Step 1: Write failing mixed-data and same-date retry tests**

Create two accepted orders for one trade date. Make one exact-date bar available and the other raise `KeyError`. Assert one fills, the missing-data order remains accepted, a diagnostic is persisted, and a later run fills only the previously accepted order after its bar becomes available.

```python
def test_batch_matching_keeps_missing_bar_order_accepted_and_fills_other_order(service, repo, market_data):
    market_data.add_bar("000001", date(2026, 7, 28), low="9", high="11", close="10")
    run = service.run(date(2026, 7, 28))
    assert run.filled_count == 1
    assert run.warning_count == 1
    assert repo.get_order(missing_order.id).status == "accepted"
```

- [ ] **Step 2: Write failing duplicate-run serialization tests**

Use two sessions or a repository test double that calls `acquire_matching_run()` twice for the same `(trade_date, account_id)`. Assert the second caller receives the active run without owning it, and only one execution creates a trade/cash event.

- [ ] **Step 3: Run focused tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q`

Expected: failure because missing bars increment generic failed count without a diagnostic and duplicate runs can process the same accepted order.

- [ ] **Step 4: Add matching-run ownership and order locking**

Add a nullable run ownership/queue state only if required by the chosen persistence shape. In the repository, atomically acquire or return an active run for `(trade_date, account_id)` and lock accepted orders with SQLAlchemy `with_for_update(skip_locked=True)` within the matching transaction.

```python
def get_orders_for_matching_locked(self, trade_date: date, account_id: int | None = None) -> list[PaperOrder]:
    query = self.session.query(PaperOrder).filter(
        PaperOrder.trade_date == trade_date,
        PaperOrder.status == OrderStatus.ACCEPTED.value,
    )
    if account_id is not None:
        query = query.filter(PaperOrder.account_id == account_id)
    return query.with_for_update(skip_locked=True).order_by(PaperOrder.id).all()
```

Add safe existing-database schema migration for any new unique index/columns. Preserve prior completed runs as audit history while preventing parallel active ownership for the same scope.

- [ ] **Step 5: Classify missing bars as warnings**

In `MatchingService.run()`, catch exact-date market-data absence separately from fill errors. Persist Task 2 diagnostic evidence for the symbol/date/BFQ context, increment `warning_count`, and leave the order accepted. Continue matching other orders. Retain fatal errors separately and keep existing price-range skip semantics.

Extend matching response/schema/run persistence with `warning_count` and a completed-with-warning representation that remains distinguishable from fatal run failure.

- [ ] **Step 6: Add rerun and terminal-order tests**

Assert rerunning after an initial mixed-data run does not create a second trade for the already filled order; it retries only the still accepted order. Assert rejected/filled orders remain excluded. Assert the API returns the active/queued run rather than launching a parallel execution.

- [ ] **Step 7: Run focused verification**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py -q`

Expected: PASS.

- [ ] **Step 8: Run formatting, lint, and targeted typing**

Run: `uv run ruff format storage/model/paper_trading.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/services/matching_service.py paper_trading/api/routers/matching.py paper_trading/schemas/matching.py test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py && uv run ruff check storage/model/paper_trading.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/services/matching_service.py paper_trading/api/routers/matching.py paper_trading/schemas/matching.py test/paper_trading/services/test_matching_service.py test/paper_trading/api/test_matching_api.py test/paper_trading/storage/test_repository.py test/storage/test_storage_db.py && uv run mypy paper_trading`

Expected: formatter completes, Ruff reports no violations, and mypy reports no new `paper_trading` errors.

### Task 6: Run EOD matching after warning-level downloads (#10)

**Files:**
- Modify: `dags/download_stock_history_daily.py:168-256`
- Modify: `tools/paper_trading_cli.py:241-270` if the client response needs warning-run fields
- Test: `test/dags/test_partition_dag_sources.py`
- Test: `test/tools/test_paper_trading_cli.py`

**Consumes:** Task 1 business date, Task 4 warning aggregate, and Task 5 serialized batch matching.

**Produces:** daily-history DAG wiring that runs matching after complete/warning summary using one business date and skips matching on closed/fatal runs.

- [ ] **Step 1: Write failing end-to-end DAG callable tests**

Mock `run_paper_trading_matching` and pass a logical-date context plus warning aggregate state. Assert its `trade_date` equals the business date; assert a closed-date context raises `AirflowSkipException`; assert a fatal aggregate state prevents invocation.

```python
def test_warning_summary_runs_matching_with_same_business_date(monkeypatch):
    monkeypatch.setattr(dag_module, "get_business_date", lambda context: date(2026, 7, 28))
    run_matching = Mock(return_value={"id": 7, "warning_count": 1})
    monkeypatch.setattr(dag_module, "run_paper_trading_matching", run_matching)
    dag_module.run_paper_trading_matching_for_active_accounts(**logical_context)
    assert run_matching.call_args.kwargs["trade_date"] == "2026-07-28"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest test/dags/test_partition_dag_sources.py test/tools/test_paper_trading_cli.py -q`

Expected: failure because matching uses wall-clock date and the current dependency chain requires all partition tasks to succeed.

- [ ] **Step 3: Update DAG trigger rules and date propagation**

Configure the aggregate task to run after all partition terminals while treating warning outcomes as successful. Keep fatal task failures fatal. Make the matching task depend on an aggregate success/warning summary and pass the Task 1 business date explicitly to the CLI helper. Do not invoke matching on a skipped closed date.

Ensure the CLI client returns existing matching warning data without changing its request API.

- [ ] **Step 4: Add available-symbol/pending-symbol workflow test**

At the workflow seam, simulate a warning summary and matching response where one order fills and one remains accepted. Assert the DAG reports the matching run ID and warning count without converting the workflow to failed.

- [ ] **Step 5: Run focused verification**

Run: `uv run pytest test/dags/test_partition_dag_sources.py test/tools/test_paper_trading_cli.py -q`

Expected: PASS.

- [ ] **Step 6: Run formatting and lint verification**

Run: `uv run ruff format dags/download_stock_history_daily.py tools/paper_trading_cli.py test/dags/test_partition_dag_sources.py test/tools/test_paper_trading_cli.py && uv run ruff check dags/download_stock_history_daily.py tools/paper_trading_cli.py test/dags/test_partition_dag_sources.py test/tools/test_paper_trading_cli.py`

Expected: formatter completes and Ruff reports no violations.

### Task 7: Make partial-data snapshots observable (#11)

**Files:**
- Modify: `storage/model/paper_trading.py`
- Modify: `storage/storage_db.py:2364-2394`
- Modify: `paper_trading/storage/repository.py`
- Modify: `paper_trading/services/snapshot_service.py:14-67`
- Modify: `paper_trading/services/matching_service.py:57-73`
- Test: `test/paper_trading/services/test_snapshot_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/storage/test_storage_db.py`

**Consumes:** Task 5 matching warning outcomes and Task 6 EOD workflow behavior.

**Produces:** a durable explicit valuation-gap outcome for accounts that cannot be exactly valued on a business date, without stale execution pricing or duplicate fills on retry.

- [ ] **Step 1: Write failing valuation-gap tests**

Add a test for an account with an active position whose exact-date bar is absent. Assert snapshot generation records a valuation-gap outcome for the same date, does not fabricate a snapshot close from a prior day, and does not change trades/cash/positions. Add a mixed-account matching test where one accounts snapshot is complete and another records a gap.

```python
def test_missing_exact_date_position_bar_records_valuation_gap(snapshot_service, repo):
    outcome = snapshot_service.generate_snapshot_or_gap(account_id=1, trade_date=date(2026, 7, 28))
    assert outcome.status == "valuation_gap"
    assert repo.list_snapshots(account_id=1) == []
    assert repo.get_valuation_gap(account_id=1, trade_date=date(2026, 7, 28)).missing_symbols == ["300996"]
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py test/storage/test_storage_db.py -q`

Expected: failure because missing bars raise and only matching-run error details exist.

- [ ] **Step 3: Add durable valuation-gap persistence**

Add a `PaperValuationGap` model keyed by account and business date with missing symbols, details, timestamps, and resolved status. Export it, add safe schema bootstrap/migration, repository upsert/read methods, and include it in database export/import lists.

- [ ] **Step 4: Implement explicit snapshot-or-gap service behavior**

Keep exact-date bar lookup. Add `generate_snapshot_or_gap(account_id, trade_date)` that gathers missing symbols; if none are missing, delegates to normal snapshot persistence; if any are missing, persists/updates a valuation gap and returns a typed outcome. It never reads a prior bar for execution or valuation substitution.

Update `MatchingService.run()` to invoke this outcome method for every account with same-date activity and every account with active positions required by the chosen repository query. Record gap outcomes as warnings, not global fatal failures; preserve true persistence/unexpected failures as fatal.

- [ ] **Step 5: Add retry and no-duplicate tests**

Assert a rerun after missing data is restored replaces/resolves the valuation gap and creates one snapshot. Assert existing filled orders are not filled again, cash/position totals do not change on the snapshot retry, and no stale close appears in the snapshot.

- [ ] **Step 6: Run focused verification**

Run: `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py test/storage/test_storage_db.py -q`

Expected: PASS.

- [ ] **Step 7: Run formatting, lint, and targeted typing**

Run: `uv run ruff format storage/model/paper_trading.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/services/snapshot_service.py paper_trading/services/matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py test/storage/test_storage_db.py && uv run ruff check storage/model/paper_trading.py storage/storage_db.py paper_trading/storage/repository.py paper_trading/services/snapshot_service.py paper_trading/services/matching_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py test/storage/test_storage_db.py && uv run mypy paper_trading`

Expected: formatter completes, Ruff reports no violations, and mypy reports no new `paper_trading` errors.

## Final Verification

- [ ] Run the full relevant test matrix:

```bash
uv run pytest \
  test/dags/test_partition_dag_sources.py \
  test/stock/test_market.py \
  test/download/test_download_manager.py \
  test/paper_trading/api/test_orders_api.py \
  test/paper_trading/api/test_matching_api.py \
  test/paper_trading/services/test_order_service.py \
  test/paper_trading/services/test_matching_service.py \
  test/paper_trading/services/test_snapshot_service.py \
  test/paper_trading/storage/test_models.py \
  test/paper_trading/storage/test_repository.py \
  test/storage/test_storage_db.py -q
```

Expected: PASS.

- [ ] Run repository quality checks proportionate to the cross-cutting schema/API/DAG change:

```bash
uv run ruff format --check . && uv run ruff check . && uv run mypy
```

Expected: all commands exit zero.

## Plan Self-Review

- Spec coverage: Tasks 1–7 cover #5 through #11 respectively, including business date, diagnostics, warning Redis summaries, explicit queued orders, idempotency, safe matching, DAG integration, and valuation gaps. Confirmed suspension rejection is explicitly deferred.
- No placeholders: all implementation and verification steps specify files, interfaces, assertions, and commands.
- Interface consistency: Tasks 4–7 consume the typed outcomes and repository methods introduced by Tasks 1–3; exact-date BFQ bars and accepted-order retry semantics remain consistent throughout.
