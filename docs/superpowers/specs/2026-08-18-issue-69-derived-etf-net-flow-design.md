# Issue 69 Derived ETF Net-Flow Calculation Design

## Purpose

Implement reproducible derived ETF net subscription/redemption metrics for a requested date range. The calculation rebuilds daily net share change, estimated net subscription/redemption amount, and flow-over-index-turnover ratio from existing raw layers: ETF share/size, ETF行情, ETF-to-index mapping diagnostics, and raw index turnover.

## Scope

This issue covers the derived calculation and persistence layer only. Raw ETF share/size download, raw index turnover download, and ETF-to-index mapping diagnostics already exist from issues #66, #67, and #68. The change should not add live provider calls, holder-disclosure parsing, financing aggregation, dashboards, or DAG schedule changes.

## Existing Context

- `storage/model/etf_share_size.py` stores raw Tushare `etf_share_size` rows keyed by ETF code and date.
- `storage/model/index_daily_turnover.py` stores raw index close and turnover rows keyed by index `ts_code` and date. Its `成交额` comment documents Tushare index turnover in 千元.
- `download/etf_index_mapping.py` centralizes ETF-to-index resolution and returns typed diagnostics for mapped, unsupported, missing, and invalid ETF codes.
- `download/download_manager.py` exposes a thin `prepare_etf_flow_index_context()` seam and keeps raw downloads independent from mapping success.
- `storage/model/etf_daily.py` stores ETF行情. Existing unit conventions use `成交额` in 千元 and `成交量` in 手 for daily market data.

## Recommended Approach

Add a focused derived-flow service and table. Keep pure unit conversion and row calculation helpers separate from persistence so the acceptance criteria can be proven with offline calculation tests. `DownloadManager` should only orchestrate the rebuild and delegate calculations to the service and writes to `StorageDb`.

This approach preserves the raw-data layer, keeps diagnostics auditable, and avoids embedding ETF business logic in storage or downloader code.

## Components

### Derived storage model

Create `storage/model/etf_net_flow.py` with table name `etf_net_flow`.

Primary key:

- `基金代码`
- `日期`

Columns:

- `基金代码`: bare six-digit ETF code.
- `日期`: derived row date.
- `总份额`: raw current total share from `etf_share_size`.
- `上一有效总份额`: previous effective raw total share used for the delta.
- `净份额变动`: current raw total share minus previous effective raw total share.
- `估算成交均价`: ETF per-share price in yuan.
- `净申赎金额`: estimated net subscription/redemption amount in yuan.
- `指数代码`: mapped index `ts_code`.
- `指数成交额`: raw index turnover amount from `index_daily_turnover`.
- `净申赎金额占指数成交额`: nullable ratio using yuan-vs-yuan units.

The table should be exported from `storage/model/__init__.py` and `storage/__init__.py`, and added to `tools/db_common.sh` so backup/import/clean workflows include the derived layer.

### Calculation helpers

Add pure helpers in a focused module such as `download/etf_net_flow.py`:

- `calculate_net_share_change(current_total_share, previous_total_share)` returns current minus previous and returns a diagnostic when prior share data is missing.
- `estimate_etf_traded_price(amount, volume, close)` converts ETF行情 `成交额` 千元 and `成交量` 手 into a per-share price using `amount * 1000 / (volume * 100)`. If amount or volume support is missing, fall back to close when close exists.
- `calculate_net_flow_amount(net_share_change, estimated_price)` converts raw Tushare share-size units to shares before multiplying by price. The service should use a named conversion constant so the unit assumption is explicit and test-covered.
- `calculate_flow_turnover_ratio(net_flow_amount, index_turnover)` converts index turnover from 千元 to yuan before division. Missing or zero turnover returns a null ratio diagnostic rather than zero.

### Rebuild service

Add a service-level rebuild function that accepts ETF code plus `start_date` and `end_date` and returns a typed result with saved row count and diagnostics. The service should:

1. Normalize the ETF code through the existing mapping helper.
2. Skip the rebuild with a diagnostic if the ETF has no supported index mapping.
3. Load ETF share/size rows for the requested range plus the prior effective share row before `start_date` when it exists.
4. Load ETF行情 rows for the requested range.
5. Load index turnover rows for the mapped index and requested range.
6. Calculate one derived row per requested share/size date when all required inputs are available.
7. Persist derived rows idempotently by ETF code and date using conflict-update behavior.

### Storage APIs

Add narrow storage methods rather than broad SQL in the service:

- `load_etf_share_size(etf_id, start_date=None, end_date=None, include_prior_effective=False)`.
- `load_index_daily_turnover(ts_code, start_date=None, end_date=None)`.
- `save_etf_net_flow(df)` with PostgreSQL and SQLite conflict-update behavior.

Reuse existing `load_etf_daily()` for ETF行情 if its returned columns and date filtering are sufficient; otherwise add only the smallest read helper needed by the service.

### Manager entry point

Expose a focused `DownloadManager.rebuild_etf_net_flow(etf_code, start_date, end_date)` method. It should not download raw inputs automatically in this issue; callers are responsible for rebuilding raw ETF share/size and index turnover first. This keeps issue #69 deterministic and reproducible from persisted raw data.

## Data Flow

1. Caller requests a rebuild for one ETF and date range.
2. Service resolves ETF-to-index context through the issue #68 resolver.
3. Service loads raw ETF share/size including the prior effective share row when available.
4. Service loads ETF行情 and raw index turnover for the requested range.
5. Service calculates net share change against the previous effective row, estimated per-share price, net flow amount, and ratio.
6. Storage upserts derived rows into `etf_net_flow`.
7. Service returns counts and diagnostics for skipped rows.

## Error Handling and Diagnostics

The service should skip rows or null ratios with explicit diagnostics instead of writing fallback zeros:

- Missing prior share data: skip the affected date because net share change is not reproducible.
- Missing ETF-to-index mapping: skip the rebuild or affected ETF with resolver diagnostic.
- Missing ETF行情 support: skip the affected date unless close-price fallback is available.
- Missing index turnover: calculate flow amount but set ratio null and record `missing_index_turnover`.
- Zero index turnover: calculate flow amount but set ratio null and record `zero_index_turnover`.
- Invalid dates or unsupported database dialects should keep existing clear failure behavior.

Diagnostics may be returned in the service result without being persisted in the derived table. Persisting diagnostics is out of scope unless tests reveal it is needed for idempotence or traceability.

## Testing

Add offline tests for:

- Normal pure calculation using current and previous share rows, ETF行情 amount/volume units, share-size unit conversion, and index turnover conversion.
- Date-range lookback loading the prior effective share row before the requested start date.
- Missing prior share diagnostics.
- Missing mapping diagnostics through the issue #68 resolver.
- Missing ETF行情 support diagnostics.
- Missing index turnover returning a null ratio and diagnostic.
- Zero index turnover returning a null ratio and diagnostic.
- Close-price fallback when amount/volume cannot produce a traded price but close exists.
- Idempotent `save_etf_net_flow()` conflict-update behavior.
- DB script coverage for `etf_net_flow`.

Recommended focused verification:

```bash
uv run pytest test/download/test_etf_net_flow.py test/download/test_download_manager.py -k 'etf_net_flow or rebuild_etf_net_flow' -v
uv run pytest test/storage/model/test_etf_net_flow.py test/storage/test_storage_db.py test/tools/test_db_common.py -k 'etf_net_flow or business_tables_include_etf_net_flow' -v
```

Use `tools/run_tests.sh` only if PostgreSQL integration behavior is changed beyond existing SQLite-compatible conflict-update coverage.

## Out of Scope

- Downloading or refreshing raw provider data automatically during a derived rebuild.
- Gross subscription and gross redemption split.
- Holder-disclosure parsing or ownership classification.
- Financing, margin, or securities-lending aggregation.
- UI/API/dashboard output.
- DAG schedule or task boundary changes.

## Definition of Done

- Derived rows can be rebuilt reproducibly for a requested ETF/date range from persisted raw tables.
- First requested date uses the previous effective share row when prior data exists.
- ETF行情 and index turnover units are converted through named helpers and covered by tests.
- Missing data and zero turnover produce skip/null diagnostics, not fallback zeros.
- Derived rows persist idempotently by ETF code and date.
- Focused offline tests pass with `uv run`.
