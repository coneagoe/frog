# Issue 66 Raw ETF Share/Size Download Design

## Purpose

Implement the raw ETF share/size download path requested by GitHub issue #66. The feature should let callers download ETF share/size rows for a trade date or date range, normalize provider identifiers into repository ETF conventions, and persist rows idempotently without duplicating `(ETF code, date)` records.

## Scope

This issue covers only the raw ETF share/size layer. It does not add index turnover downloads, derived ETF subscription/redemption calculations, dashboard output, or holder-disclosure parsing.

## Data Source

Use the Tushare `etf_share_size` provider endpoint through `download/dl/downloader_tushare.py`.

The downloader must pass an explicit field list:

- `ts_code`
- `trade_date`
- `close`
- `nav`
- `total_share`
- `total_size`

The downloader should accept optional ETF identifier and date filters:

- `ts_code`: either bare six-digit ETF code or provider-style code with `.SH` / `.SZ`
- `trade_date`: single date filter
- `start_date` and `end_date`: date-range filter

Dates should reuse the existing `convert_date` behavior and accepted formats. Bare ETF codes should normalize through the same market suffix convention used by current ETF downloads.

## Normalization

Provider rows should be normalized before persistence:

- `ts_code` becomes bare six-digit `基金代码` by removing the provider exchange suffix.
- `trade_date` becomes repository `日期` with the same string/date convention used by nearby ETF storage paths.
- Numeric provider fields remain provider-unit raw facts; no derived unit conversion happens in this layer.

Empty provider responses must return a stable empty DataFrame with the normalized output columns rather than provider-dependent columns.

## Storage Model

Add `storage/model/etf_share_size.py` with table name `etf_share_size`.

Primary key:

- `基金代码`
- `日期`

Columns:

- `基金代码`: bare six-digit ETF code
- `日期`: trade date
- `收盘价`: provider close price
- `单位净值`: provider NAV
- `总份额`: provider `total_share`, stored in raw Tushare units and documented in the SQLAlchemy column comment
- `总规模`: provider `total_size`, stored in raw Tushare units and documented in the SQLAlchemy column comment

The model must be imported from `storage/model/__init__.py` so metadata creation includes the table.

## Persistence

Add a storage save method that upserts `etf_share_size` rows using the table primary key. The method should support both PostgreSQL and SQLite dialects with conflict-update behavior so rerunning the same date range refreshes changed values instead of inserting duplicates.

The storage layer should reject or fail clearly on missing required columns rather than silently writing incomplete rows.

## Download Manager

Expose a focused `DownloadManager` entry point that calls the downloader and persists the normalized DataFrame through storage. Empty normalized results should be treated as successful no-op downloads.

## Database Scripts

Add `etf_share_size` to the business table list in `tools/db_common.sh` so export, import, and clean workflows include the new raw table.

## Testing

Add offline tests for:

- Tushare provider parameters and explicit field list.
- Bare ETF code normalization and provider-style code passthrough.
- Empty provider response returning a stable normalized shape.
- Storage model primary key definition and raw-unit comments.
- Idempotent PostgreSQL/SQLite-compatible upsert behavior.
- DownloadManager save/no-op behavior.
- `tools/db_common.sh` coverage for `etf_share_size`.

Focused verification should start with:

```bash
uv run pytest test/download/dl/test_downloader_tushare.py test/download/test_download_manager.py test/tools/test_db_common.py
```

Use `tools/run_tests.sh` if PostgreSQL integration coverage is added or changed.

## Out of Scope

- Index turnover raw table.
- Derived ETF net subscription/redemption calculations.
- ETF share adjustment or comparable historical share reconstruction.
- Dashboard/API/UI rendering.
- Holder-disclosure parsing or state-holder classification.

## Definition of Done

- Raw ETF share/size downloader is exposed through the downloader facade.
- Provider output is normalized to bare ETF code/date conventions.
- Empty responses return a stable normalized DataFrame shape.
- Raw table model includes documented provider units.
- Rows persist idempotently by ETF code and date with conflict update.
- The table participates in DB export/import/clean workflows.
- Offline tests cover the issue acceptance criteria and pass with `uv run`.
