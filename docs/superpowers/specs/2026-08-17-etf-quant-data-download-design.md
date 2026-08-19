# ETF Quant Data Download Design

## Purpose

Implement the first-stage ETF quantitative data download pipeline for the Wangwang ETF analysis work. The scope is raw ETF share/size data, index turnover data, and derived daily net subscription/redemption metrics. The implementation should stay separate from holder-disclosure parsing, insurance/state-holder classification, and margin-financing aggregation.

## Existing Context

- `download/dl/downloader_tushare.py` already owns Tushare client creation, date normalization, retry wrappers, ETF daily行情 downloads, and ETF basic downloads.
- `download/dl/downloader.py` exposes provider functions through the `Downloader` facade.
- `download/download_manager.py` coordinates downloader calls with storage writes and already has ETF basic and ETF daily entry points.
- `storage/model/etf_daily.py` stores ETF OHLCV行情 only; it should not be extended with share/size fields because the data type and update cadence are different.
- Existing tests mock Tushare clients and should remain offline-only.

## Recommended Approach

Add a new, separate ETF share/size download path rather than mixing share fields into `etf_daily`.

This keeps raw market行情, ETF份额规模, and derived申赎 indicators auditable as separate layers:

1. Raw ETF行情: existing `etf_daily`.
2. Raw ETF份额规模: new table sourced from Tushare `etf_share_size`.
3. Raw指数成交额: new `index_daily_turnover` table sourced from Tushare index APIs.
4. Derived ETF申赎: calculated from raw share/size + ETF行情 + index turnover.

## Data Sources

### ETF Share/Size

Use Tushare `etf_share_size` as the primary source.

Expected raw fields:

- `ts_code`
- `trade_date`
- `close`
- `nav`
- `total_share`
- `total_size`

The downloader must pass an explicit `fields` list so `close`, `nav`, `total_share`, and `total_size` are present even when Tushare defaults change. Store raw Tushare units in model comments and normalize calculation units only in the derived-flow transformer.

The downloader should accept `ts_code` or bare ETF code, `trade_date`, `start_date`, and `end_date`. Bare codes should reuse the existing ETF suffix logic where practical.

### Index Turnover

Use Tushare `index_daily` for index close and turnover amount. The first implementation should support the core index set needed by the ETF groups:

- 沪深300
- 上证50
- 上证180
- 中证500
- 中证800
- 中证1000
- 创业板指
- 科创50
- 深证100

Index code mapping should live in one explicit module/constant so future groups can be added without scattering hardcoded strings.

The first implementation must pin both the Tushare index `ts_code` and local group key. ETF groups without a known index mapping should still download raw ETF share/size data, but derived-flow generation should skip them with a diagnostic reason.

## Storage Design

### Raw ETF Share/Size Table

Add `storage/model/etf_share_size.py` with table name `etf_share_size`.

Primary key:

- `基金代码`
- `日期`

Recommended columns:

- `基金代码`: bare six-digit ETF code
- `日期`: trade date
- `收盘价`: provider close price
- `单位净值`: NAV
- `总份额`: ETF total share
- `总规模`: ETF total size
- `交易所`: provider exchange identifier, when available

Unit comments must capture Tushare raw units, especially `总份额` and `总规模`, because derived申赎 calculations depend on unit conversion.

### Raw Index Turnover Table

Add `storage/model/index_daily_turnover.py` with table name `index_daily_turnover`. The table should store:

- `指数代码`
- `日期`
- `收盘点位`
- `成交额`

`成交额` should keep the provider raw unit in storage and expose a named conversion helper for derived calculations.

Primary key:

- `指数代码`
- `日期`

### Derived ETF Flow Table

Add a derived table only after raw tables are in place. It should store calculated metrics rather than provider facts:

- `基金代码`
- `日期`
- `总份额`
- `净份额变动`
- `估算成交均价`
- `净申赎金额`
- `指数代码`
- `指数成交额`
- `净申赎金额占指数成交额`

The derived table should be reproducible from raw tables and safe to rebuild for a date range.

Derived-flow calculation should live in a focused service/transformer, not inside `DownloadManager`. `DownloadManager` should orchestrate downloads and call storage/service methods only.

All three new tables must be wired into `storage/model/__init__.py` and `tools/db_common.sh` so metadata creation, export/import, and clean workflows stay complete.

## Data Flow

1. Download ETF share/size for a single trade date or date range.
2. Normalize `ts_code` to bare ETF code and convert dates to repository date conventions.
3. Upsert raw share/size rows into `etf_share_size` using PostgreSQL/SQLite `ON CONFLICT DO UPDATE` on the table primary key.
4. Download index close/turnover for the configured index set and date range.
5. Upsert raw index rows into the index turnover table with the same primary-key conflict policy.
6. Build derived ETF flow rows by joining:
   - current and previous ETF share/size rows
   - ETF daily行情 for price/amount support
   - ETF-to-index mapping from `etf_basic` or explicit group mapping
   - index turnover rows
7. Upsert derived flow rows for the requested date range.

For date-range rebuilds, the service must load at least one prior effective share/size row before `start_date` so the first requested date can calculate `净份额变动` when prior data exists.

## Calculations

- `净份额变动 = 当日总份额 - 上一有效交易日总份额`
- `估算成交均价 = ETF日行情成交额 / ETF日行情成交量` after converting existing `etf_daily` units from `成交额(千元)` and `成交量(手)` into a per-share price; otherwise use ETF close price.
- `净申赎金额 = 净份额变动 × 估算成交均价` after converting ETF share-size units to shares.
- `净申赎金额占指数成交额 = 净申赎金额 / 指数成交额` after converting index amount into the same currency unit as `净申赎金额`.

Units must be made explicit in model comments and storage helpers. If Tushare returns share or amount in units that differ from existing repository constants, normalization should happen at the storage boundary or in a named transformer, not inline in manager code.

## Error Handling

- Missing `TUSHARE_TOKEN` should continue to raise the existing `ConnectionError` style.
- Invalid dates should reuse `convert_date` and raise `ValueError`.
- Empty provider results should return an empty DataFrame with stable columns.
- Derived calculations should skip rows with missing prior share data and record/report a diagnostic reason rather than writing fallback zeros.
- Derived calculations should skip rows with missing ETF-to-index mapping, missing ETF行情 price support, or missing index turnover, except where the close-price fallback is explicitly valid.
- Division by zero or missing index turnover should produce null `净申赎金额占指数成交额`, not zero.

## Testing

Add offline tests with mocked Tushare clients:

- Downloader test for `etf_share_size` parameter normalization and field selection.
- Downloader test for empty share/size result shape.
- Downloader test for index turnover parameter normalization.
- Storage/model test for primary keys and upsert behavior.
- Manager test proving share/size and index data are saved through the expected storage methods.
- Derived-flow unit test covering normal calculation, unit conversion, date-range lookback, missing previous share row, missing index mapping, missing ETF行情, zero index turnover, and ETF close fallback.
- DB script tests proving `etf_share_size`, `index_daily_turnover`, and the derived ETF flow table are included in business table export/import/clean coverage.

Recommended focused commands:

```bash
uv run pytest test/download/dl/test_downloader_tushare.py
uv run pytest test/download/test_download_manager.py
uv run pytest test/tools/test_db_scripts.py test/tools/test_db_common.py
```

Use `tools/run_tests.sh` only if PostgreSQL integration coverage is added or changed.

## Out of Scope

- Parsing基金年报/半年报持有人.
- Classifying汇金/证金/险资/国资主体.
- Gross申购量 and gross赎回量 split.
- ETF or index融资融券 aggregation.
- UI/dashboard rendering.

## Definition of Done

- Raw ETF share/size download is exposed through downloader and manager layers.
- Raw index turnover download is exposed through downloader and manager layers.
- Storage models and save/upsert methods preserve primary-key uniqueness.
- Derived net subscription/redemption metrics can be rebuilt for a date range.
- All new tests are offline and pass with `uv run`.
- Documentation notes the new pipeline and its scope limits.
