# Issues 8 and 9 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining daily-history warning-summary and paper-trading matching failure-semantics acceptance gaps for issues #8 and #9.

**Architecture:** The existing daily-history DAG aggregation and matching-run serialization remain unchanged. Focused DAG tests lock down the Redis summary and fatal gating contract. `MatchingService` will centralize missing-exact-date diagnostics, classify only `KeyError` bar lookups as warning outcomes, and make all order-processing failures participate in final run failure status and contextual error details.

**Tech Stack:** Python 3.11+, Apache Airflow, SQLAlchemy, Redis, pytest, Ruff, uv.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Keep `result=success` for complete and warning-only Redis summaries.
- Preserve the existing Redis fields: business `date`, `status`, sorted `missing_symbols`, and a deterministic maximum of 20 `provider_evidence` items.
- Treat only an absent exact-date daily bar (`KeyError`) as recoverable matching warning; leave the order `ACCEPTED` and persist its BFQ diagnostic.
- Treat unexpected market-data, fill, settlement, trade, cash, position, persistence, and snapshot errors as fatal matching failures.
- Preserve the existing active-run uniqueness and accepted-order locking behavior; do not alter DAG schedules, dependencies, or task boundaries.
- Do not create git commits unless the user explicitly requests them.

---

## File Map

| File | Responsibility after this work |
| --- | --- |
| `dags/download_stock_history_daily.py` | Continue aggregating daily partition results into the warning-compatible Redis summary and gate matching after fatal aggregates. No functional change is expected. |
| `test/dags/test_partition_dag_sources.py` | Assert complete-success, warning-success, and fatal workflow contracts. |
| `paper_trading/services/matching_service.py` | Centralize missing-bar diagnostics, distinguish warning vs fatal per-order outcomes, and derive the matching-run status and error details. |
| `test/paper_trading/services/test_matching_service.py` | Exercise missing-bar diagnostics through both batch and single-order paths, plus fatal order-processing status behavior. |

## Shared Interfaces

`MatchingService.run()` remains the batch entry point:

```python
def run(self, trade_date: date, account_id: int | None = None) -> PaperMatchingRun: ...
```

It must retain the existing matching-run count fields and set statuses with this precedence:

```python
if order_failures or snapshot_errors:
    status = MatchingRunStatus.FAILED.value
elif warning_count:
    status = MatchingRunStatus.COMPLETED_WITH_WARNINGS.value
else:
    status = MatchingRunStatus.COMPLETED.value
```

`MatchingService.match_order()` keeps its public string result contract and adds a warning result for a missing exact-date daily bar:

```python
def match_order(self, order: PaperOrder) -> str:
    # "filled", "skipped", "rejected", "warning", or "failed"
    ...
```

Both entry points use one private helper for the recoverable missing-bar case:

```python
def _record_missing_exact_date_diagnostic(self, order: PaperOrder, error: KeyError) -> None: ...
```

The helper calls the existing repository interface exactly once per missing lookup:

```python
repo.upsert_daily_bar_diagnostic(
    order.trade_date,
    order.symbol,
    "bfq",
    "missing_exact_date",
    [{"provider": "market_data", "status": "empty", "detail": str(error)}],
    False,
)
```

### Task 1: Lock Down Daily-History Result Contracts (#8)

**Files:**
- Modify: `test/dags/test_partition_dag_sources.py:81-199`
- Verify: `dags/download_stock_history_daily.py:200-258`

**Consumes:** `save_download_result_to_redis()`, `run_paper_trading_matching_for_active_accounts()`, Airflow task context, and the Redis client seam already monkeypatched by DAG tests.

**Produces:** Regression evidence that complete and warning-only runs remain successful, while fatal aggregate results skip paper-trading matching.

- [ ] **Step 1: Add a complete-success Redis summary test**

Add a test beside `test_warning_aggregate_writes_structured_bounded_payload` with empty HFQ and BFQ outcomes. Decode the Redis value and assert there are no warning fields with warning values:

```python
def test_complete_aggregate_writes_success_payload(monkeypatch):
    business_date = date(2026, 7, 28)
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: business_date)
    redis_client = MagicMock()
    monkeypatch.setattr(dag_module, "get_redis_client", lambda: redis_client)
    ti = MagicMock()
    ti.xcom_pull.side_effect = [
        {"adjust": "hfq", "outcomes": []},
        {"adjust": "bfq", "outcomes": []},
    ]

    dag_module.save_download_result_to_redis(partition_count=1, ti=ti)

    payload = json.loads(redis_client.set.call_args.args[1])
    assert payload == {
        "date": "2026-07-28",
        "result": "success",
        "status": "success",
        "missing_symbols": [],
        "provider_evidence": [],
    }
```

- [ ] **Step 2: Run the complete-summary test to establish its baseline**

Run: `uv run pytest test/dags/test_partition_dag_sources.py::test_complete_aggregate_writes_success_payload -q`

Expected: PASS. The production contract already exists; this step establishes its focused regression baseline before changing service code elsewhere.

- [ ] **Step 3: Strengthen the existing warning-summary assertions**

In `test_warning_aggregate_writes_structured_bounded_payload`, retain the existing assertions and add exact ordering checks. Reverse the input outcomes before returning them from `ti.xcom_pull` and assert provider evidence starts at stock ID `300000` and ends at `300019`. This proves aggregation is deterministic before its 20-item bound is applied.

```python
assert [item["stock_id"] for item in payload["provider_evidence"]] == [
    f"300{i:03d}" for i in range(20)
]
```

- [ ] **Step 4: Run all daily-history contract tests**

Run: `uv run pytest test/dags/test_partition_dag_sources.py -q`

Expected: PASS, including existing warning-continuation, fatal-skip, and diagnostic-persistence rollback tests.

- [ ] **Step 5: Format and lint the DAG test module**

Run: `uv run ruff format test/dags/test_partition_dag_sources.py && uv run ruff check test/dags/test_partition_dag_sources.py`

Expected: Ruff completes with no violations.

### Task 2: Separate Recoverable Missing Bars From Fatal Matching Failures (#9)

**Files:**
- Modify: `paper_trading/services/matching_service.py:35-128`
- Modify: `test/paper_trading/services/test_matching_service.py:423-545`

**Consumes:** `PaperTradingRepository.upsert_daily_bar_diagnostic()`, `PaperTradingRepository.update_matching_run_counts()`, `MatchingRunStatus`, `OrderStatus`, and `DailyBar` fakes used by matching-service tests.

**Produces:** Batch matching that records only missing exact-date data as a warning and reports any order-processing exception as a fatal matching run; single-order matching produces the same durable missing-bar diagnostic.

- [ ] **Step 1: Add a failing batch fatal-order test**

Add a test that creates one accepted order, replaces `_fill_order` with a function that raises `RuntimeError("cash ledger unavailable")`, runs matching, and asserts the run failed with contextual details while the order remains accepted:

```python
def test_matching_order_processing_failure_marks_run_failed(tmp_path, monkeypatch):
    engine, session, repo, order_service, matching_service, trade_date = _services(tmp_path)
    account = repo.create_account("fatal-order", Decimal("100000.00"))
    order = order_service.place_order(account.id, "000001.SZ", OrderSide.BUY, 100, Decimal("10.00"), trade_date)
    monkeypatch.setattr(
        matching_service,
        "_fill_order",
        lambda current_order: (_ for _ in ()).throw(RuntimeError("cash ledger unavailable")),
    )

    run = matching_service.run(trade_date, account.id)

    assert run.failed_count == 1
    assert run.status == MatchingRunStatus.FAILED.value
    assert f"order={order.id}" in run.error_details
    assert "cash ledger unavailable" in run.error_details
    assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
    engine.dispose()
```

- [ ] **Step 2: Add a failing single-order missing-bar test**

Use a `MarketDataProvider` fake whose `get_daily_bar()` raises `KeyError`. Call `match_order()` and assert the new warning outcome, the order stays accepted, and the repository contains an unresolved `missing_exact_date` BFQ diagnostic for that business date and canonical symbol:

```python
assert matching_service.match_order(order) == "warning"
assert repo.get_order(order.id).status == OrderStatus.ACCEPTED.value
diagnostic = next(item for item in repo.list_daily_bar_diagnostics() if item.stock_id == "000001")
assert diagnostic.classification == "missing_exact_date"
assert diagnostic.resolved is False
```

- [ ] **Step 3: Run the two tests to verify they fail**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py::test_matching_order_processing_failure_marks_run_failed test/paper_trading/services/test_matching_service.py::test_match_order_missing_exact_date_records_warning_diagnostic -q`

Expected: the fatal-order test fails because `run()` currently ignores `failed_count` while deriving status; the single-order test fails because `match_order()` currently returns `"failed"` without a diagnostic.

- [ ] **Step 4: Add a missing-bar diagnostic helper**

In `MatchingService`, extract the existing `KeyError` diagnostic upsert from `run()` into `_record_missing_exact_date_diagnostic(order, error)`. Preserve the existing provider evidence exactly and use `order.trade_date`, the unnormalized `order.symbol`, `"bfq"`, `"missing_exact_date"`, and `resolved=False`.

```python
def _record_missing_exact_date_diagnostic(self, order: PaperOrder, error: KeyError) -> None:
    self.repo.upsert_daily_bar_diagnostic(
        order.trade_date,
        order.symbol,
        "bfq",
        "missing_exact_date",
        [{"provider": "market_data", "status": "empty", "detail": str(error)}],
        False,
    )
```

Call this helper from both `run()` and `match_order()` on `KeyError`. In `match_order()`, return `"warning"` after recording it. Retain `"failed"` for non-`KeyError` lookup exceptions and fill failures.

- [ ] **Step 5: Record fatal order failures and apply status precedence**

In `run()`, accumulate `order_errors: list[str]`. Replace the broad order-loop `except` body with one that increments `failed` and appends an `order=<id>, account=<account_id>, trade_date=<trade_date>: <exception>` message. Keep processing independent remaining orders.

Derive the final status and details using both order and snapshot errors:

```python
error_messages = [*order_errors, *snapshot_errors]
status = (
    MatchingRunStatus.FAILED.value
    if error_messages
    else MatchingRunStatus.COMPLETED_WITH_WARNINGS.value
    if warning_count
    else MatchingRunStatus.COMPLETED.value
)
error_details = "; ".join(error_messages) if error_messages else None
```

Pass `error_details` to `update_matching_run_counts()` and retain all current counts and snapshot behavior.

- [ ] **Step 6: Run new and adjacent matching-service tests**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py::test_matching_order_processing_failure_marks_run_failed test/paper_trading/services/test_matching_service.py::test_match_order_missing_exact_date_records_warning_diagnostic test/paper_trading/services/test_matching_service.py::test_matching_mixed_exact_date_data_keeps_missing_order_accepted test/paper_trading/services/test_matching_service.py::test_matching_same_date_retry_fills_only_previously_accepted_order test/paper_trading/services/test_matching_service.py::test_matching_fill_resolves_historical_retry_diagnostic test/paper_trading/services/test_matching_service.py::test_snapshot_market_data_failure_marks_run_failed_and_preserves_fill -q`

Expected: PASS. This verifies warning diagnostics, fatal status precedence, retries, resolution, and existing snapshot failure handling.

- [ ] **Step 7: Run the complete matching-service test module**

Run: `uv run pytest test/paper_trading/services/test_matching_service.py -q`

Expected: PASS.

- [ ] **Step 8: Format and lint matching changes**

Run: `uv run ruff format paper_trading/services/matching_service.py test/paper_trading/services/test_matching_service.py && uv run ruff check paper_trading/services/matching_service.py test/paper_trading/services/test_matching_service.py`

Expected: Ruff completes with no violations.

### Task 3: Verify Issue-Level Integration

**Files:**
- Verify: `test/dags/test_partition_dag_sources.py`
- Verify: `test/paper_trading/services/test_matching_service.py`
- Verify: `test/paper_trading/api/test_matching_api.py`
- Verify: `test/paper_trading/storage/test_repository.py`

**Consumes:** Completed Tasks 1 and 2.

**Produces:** Evidence that both issue contracts hold across the DAG, service, API, and durable diagnostic seams.

- [ ] **Step 1: Run the issue-focused test suite**

Run:

```bash
uv run pytest \
  test/dags/test_partition_dag_sources.py \
  test/paper_trading/services/test_matching_service.py \
  test/paper_trading/api/test_matching_api.py \
  test/paper_trading/storage/test_repository.py -q
```

Expected: PASS.

- [ ] **Step 2: Inspect the final patch for formatting and scope**

Run: `git diff --check && git diff -- dags/download_stock_history_daily.py paper_trading/services/matching_service.py test/dags/test_partition_dag_sources.py test/paper_trading/services/test_matching_service.py`

Expected: no whitespace errors; the production diff is limited to matching outcome classification and the test diff covers the three `#8` contracts and two `#9` gaps.

- [ ] **Step 3: Run targeted static checks**

Run: `uv run ruff check dags/download_stock_history_daily.py paper_trading/services/matching_service.py test/dags/test_partition_dag_sources.py test/paper_trading/services/test_matching_service.py`

Expected: Ruff reports no violations.
