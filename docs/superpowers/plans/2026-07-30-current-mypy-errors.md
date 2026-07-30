# Current mypy errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the currently reported `uv run pre-commit run mypy --all-files` errors pass without changing runtime behavior or widening cleanup scope.

**Architecture:** Keep legacy SQLAlchemy models intact and cast only their query results at repository return boundaries. Bring paper-trading test doubles into structural `MarketDataProvider` conformance, then apply narrow type annotations at download, Airflow, and test boundaries.

**Tech Stack:** Python 3.12, mypy pre-commit, SQLAlchemy legacy ORM, pandas, Airflow, pytest, uv.

## Global Constraints

- Use `uv run` for Python commands.
- Retain `explicit_package_bases = true` in `pyproject.toml`.
- Do not change runtime behavior, DAG schedule, dependencies, retries, task boundaries, or SLAs.
- Do not add broad mypy ignores, global disables, or a SQLAlchemy `Mapped[...]` migration.
- Verify the current all-files pre-commit mypy scope only.

---

## File Structure

- `test/paper_trading/fakes.py` and local service/API tests: market-data test doubles.
- `paper_trading/storage/repository.py`: ORM query return narrowing.
- `download/download_manager.py`, `download/dl/downloader_yfinance.py`: provider typing boundaries.
- `dags/download_stock_history_daily.py`: Airflow context boundary.
- Four test modules: isolated annotation and intentional-invalid-input repairs.

### Task 1: Implement Market-Data Protocol Methods

**Files:**
- Modify: `test/paper_trading/fakes.py:62-113`
- Modify: `test/paper_trading/services/test_trade_validity_service.py:18-57`
- Modify: `test/paper_trading/services/test_matching_service.py:91-488`
- Modify: `test/paper_trading/api/test_matching_api.py:38-71`
- Test: `test/paper_trading/services/test_trade_validity_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_order_service.py`
- Test: `test/paper_trading/services/test_order_delete_service.py`
- Test: `test/paper_trading/api/test_matching_api.py`

**Interfaces:**
- Consumes: `MarketDataProvider.get_latest_daily_close(symbol: str, trade_date: date, market: str | None = None) -> Decimal | None` from `paper_trading/storage/market_data.py:37`.
- Produces: provider doubles valid for all existing service constructors.

- [ ] **Step 1: Add failing direct behavior coverage**

Add tests proving `StaticMarketData` returns its configured bar close and `FailingMarketData` returns `None`:

```python
assert provider.get_latest_daily_close("000001.SZ", date(2026, 7, 30)) == Decimal("12.34")
assert FailingMarketData().get_latest_daily_close("000001.SZ", date(2026, 7, 30)) is None
```

Run `uv run pytest test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_matching_service.py -q`.
Expected: failure because the methods do not exist.

- [ ] **Step 2: Add the shared fake implementation**

In `FakeMarketDataProvider`, implement the required signature:

```python
def get_latest_daily_close(self, symbol: str, trade_date: date, market: str | None = None) -> Decimal | None:
    bar = self._bars.get((symbol, trade_date))
    return None if bar is None else bar.close
```

Inherited `MarketAwareProvider`, `CatchCallsProvider`, both existing `MarketCaptureProvider` classes, and `UnavailableMarketData` must use this implementation unchanged.

- [ ] **Step 3: Implement standalone fake methods**

Add the same signature to `StaticMarketData`, `FailingMarketData`, `MutableMarketData`, both `MixedMarketData` declarations, `CapturingMarketData`, `RetryMarketData`, `ExactDateMarketData`, and API-local `MarketData`.

Use `return self.bar.close if self.bar is not None else None` for `StaticMarketData`; all other listed standalone fakes return `None`. Do not change their `get_daily_bar` behaviors.

- [ ] **Step 4: Type the matching-service empty fixture**

Replace the untyped empty mapping at `test_matching_service.py:433` with:

```python
missing_bar: dict[str, object] = {}
```

- [ ] **Step 5: Verify protocol work**

Run:

```bash
uv run pytest test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_matching_api.py
uv run pre-commit run mypy --files test/paper_trading/fakes.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_matching_api.py
```

Expected: tests pass and no missing-`get_latest_daily_close` diagnostics remain.

### Task 2: Narrow Production Type Boundaries

**Files:**
- Modify: `paper_trading/storage/repository.py:94-108,409-414,466-489`
- Modify: `download/download_manager.py:270-287`
- Modify: `download/dl/downloader_yfinance.py:1-96`
- Modify: `dags/download_stock_history_daily.py:1-249`
- Test: `test/paper_trading/storage/test_repository.py`
- Test: `test/download/dl/test_downloader_yfinance.py`

**Interfaces:**
- Consumes: `ProviderStatus = Literal["downloaded", "empty", "error"]`, legacy SQLAlchemy results, and Airflow `dict[str, Any]` context.
- Produces: existing declared return types without external behavior changes.

- [ ] **Step 1: Verify current runtime coverage**

Run `uv run pytest test/paper_trading/storage/test_repository.py test/download/dl/test_downloader_yfinance.py -q`.
Expected: pass before type-only changes.

- [ ] **Step 2: Cast four ORM query return boundaries**

Use the existing `cast` import at the return sites in `upsert_daily_bar_diagnostic`, `get_order_by_idempotency_key`, `upsert_valuation_gap`, and `get_valuation_gap`:

```python
return cast(DailyBarDiagnostic, diagnostic)
return cast(PaperOrder | None, query.one_or_none())
return cast(PaperValuationGap, gap)
return cast(PaperValuationGap | None, query.one_or_none())
```

Keep all queries, mutations, and flushes unchanged.

- [ ] **Step 3: Narrow download values**

Import `ProviderStatus` and annotate the fallback outcome value:

```python
status: ProviderStatus = "empty" if isinstance(df, pd.DataFrame) and df.empty else "error"
```

In `downloader_yfinance.py`, import `cast` and use:

```python
return cast(pd.DataFrame, normalized.reset_index(drop=True))
```

- [ ] **Step 4: Narrow dynamic Airflow values**

In `get_business_date`, return:

```python
return cast(date, context["data_interval_end"].in_timezone(LOCAL_TZ).date())
```

In matching orchestration, bind once before accessing XCom:

```python
ti: Any = context.get("ti")
aggregate_summary = ti.xcom_pull(task_ids="save_download_result_to_redis") if ti is not None else None
```

Do not change XCom IDs or orchestration flow.

- [ ] **Step 5: Verify production boundaries**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/download/dl/test_downloader_yfinance.py test/dags/test_partition_dag_sources.py
uv run pre-commit run mypy --files paper_trading/storage/repository.py download/download_manager.py download/dl/downloader_yfinance.py dags/download_stock_history_daily.py
```

Expected: tests pass and these files produce no hook errors.

### Task 3: Repair Test-Only Types

**Files:**
- Modify: `test/tools/test_test_proxy.py:25-43,89-117`
- Modify: `test/utility/test_proxy.py:285-314`
- Modify: `test/paper_trading/storage/test_repository.py:92-98`
- Modify: `test/dags/test_partition_dag_sources.py:70-107`
- Test: same files.

**Interfaces:**
- Consumes: the existing test values and `ProviderOutcome` runtime validation.
- Produces: static validity without reducing test behavior.

- [ ] **Step 1: Verify current tests**

Run `uv run pytest test/tools/test_test_proxy.py test/utility/test_proxy.py test/paper_trading/storage/test_repository.py test/dags/test_partition_dag_sources.py -q`.
Expected: pass before type-only changes.

- [ ] **Step 2: Type test collection captures**

Type both proxy `calls` lists as `list[tuple[str, dict[str, object]]]`; if a dynamic callback does not fit, use `list[tuple[object, object]]` only for that capture. Type `deleted` as `list[str]`.

- [ ] **Step 3: Preserve the invalid status runtime test**

Import `Any` and `cast`, then retain the invalid input while keeping the constructor's production contract:

```python
ProviderOutcome(provider="tushare", status=cast(Any, "partial"))
```

Do not add `"partial"` to `ProviderStatus`.

- [ ] **Step 4: Give the DAG fixture a concrete shape**

Declare test-local `DownloadOutcome(TypedDict)` with `stock_id: str`, `business_date: str`, `adjust: str`, `classification: str`, `provider_outcomes: list[dict[str, object]]`, and `resolved: bool`. Annotate the existing `outcomes` list as `list[DownloadOutcome]`, keeping every fixture value unchanged.

- [ ] **Step 5: Verify test-only repairs**

Run:

```bash
uv run pytest test/tools/test_test_proxy.py test/utility/test_proxy.py test/paper_trading/storage/test_repository.py test/dags/test_partition_dag_sources.py
uv run pre-commit run mypy --files test/tools/test_test_proxy.py test/utility/test_proxy.py test/paper_trading/storage/test_repository.py test/dags/test_partition_dag_sources.py
```

Expected: all tests pass and these files emit no mypy errors.

### Task 4: Integrate and Validate

**Files:**
- Verify: `pyproject.toml` and every file changed in Tasks 1-3.

**Interfaces:**
- Consumes: all preceding changes.
- Produces: clean current mypy hook result.

- [ ] **Step 1: Check scope and whitespace**

Run `git diff --check` and `git diff -- pyproject.toml paper_trading download dags test`.
Expected: no whitespace errors, no broad ignores, and no SQLAlchemy model migration.

- [ ] **Step 2: Run the full configured hook**

Run `uv run pre-commit run mypy --all-files`.
Expected: exit code 0 and no mypy errors.

- [ ] **Step 3: Run focused regressions**

Run:

```bash
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/services/test_trade_validity_service.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_order_delete_service.py test/paper_trading/api/test_matching_api.py test/download/dl/test_downloader_yfinance.py test/tools/test_test_proxy.py test/utility/test_proxy.py test/dags/test_partition_dag_sources.py
```

Expected: pass.

- [ ] **Step 4: Inspect final status**

Run `git status --short` and retain all pre-existing user changes.
