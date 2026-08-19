# ETF Quant Pipeline Handoff

## Purpose

The first-stage ETF quant data pipeline downloads and stores the raw inputs needed to estimate ETF daily net subscription/redemption pressure, then rebuilds a derived net-flow layer from those persisted raw tables. It is designed as an auditable handoff surface for the Wangwang ETF analysis work: users can see which facts are raw provider data, which fields are calculated, and which focused checks prove the pipeline remains safe.

## Run Surface

The manager-level entry point is `DownloadManager.download_etf_quant_data(etf_code, start_date, end_date)` in `download/download_manager.py`. It runs three stages in order:

1. Download raw ETF share/size rows into `etf_share_size`.
2. Download raw turnover rows for the configured core indexes into `index_daily_turnover`.
3. Rebuild derived ETF net-flow rows into `etf_net_flow` after the raw prerequisites are available.

`DownloadManager.rebuild_etf_net_flow(etf_code, start_date, end_date)` can also rebuild the derived layer from already-persisted raw data without downloading provider data again.

## Layer 1: Raw ETF Share/Size

The raw ETF share/size layer uses Tushare `etf_share_size` data through the downloader and manager path, then stores it in the `etf_share_size` business table. The table is keyed by bare ETF code and trade date, preserving provider facts such as close, NAV, total share, total size, and exchange metadata.

This layer remains separate from ETF daily行情 because share/size data has different source semantics, update cadence, and unit risks. Storage preserves raw Tushare units; derived calculations handle unit normalization explicitly instead of mutating the raw layer.

## Layer 2: Raw Index Turnover

The raw index turnover layer downloads close and turnover for the configured core index set and stores those rows in `index_daily_turnover`. Rows are keyed by index `ts_code` and trade date.

ETF-to-index mapping is resolved separately from raw downloads. Raw ETF share/size rows can still be saved for ETFs without a supported index mapping, while the derived net-flow rebuild skips unsupported mappings with diagnostics instead of inventing a denominator.

## Layer 3: Derived ETF Net Flow

The derived layer writes `etf_net_flow`. It is reproducible from persisted raw ETF share/size, ETF daily行情, ETF-to-index mapping, and raw index turnover.

For each requested date, the rebuild service loads the current share/size row plus the previous effective share row before the requested start date when available. It then calculates:

- `净份额变动 = 当日总份额 - 上一有效总份额`.
- `估算成交均价` from ETF行情 amount and volume after converting amount from 千元 and volume from 手; close price is used only as the explicit fallback when amount/volume cannot support the estimate.
- `净申赎金额 = 净份额变动 × 份额单位转换 × 估算成交均价`.
- `净申赎金额占指数成交额 = 净申赎金额 / 指数成交额` after converting index turnover into the same currency unit.

Derived rows persist idempotently by ETF code and date. Missing prior share data, missing mapping, missing ETF行情 support, missing index turnover, and zero index turnover produce skip/null diagnostics rather than fallback zeros.

## Unit Conversion Risks

The pipeline deliberately keeps raw provider units visible because the derived metrics are sensitive to unit mismatches:

- ETF share-size `总份额` is stored in the provider raw unit and converted only when calculating `净申赎金额`.
- ETF行情 `成交额` is stored in 千元 and `成交量` is stored in 手, so traded-price estimates must convert both sides before deriving 元/份.
- Index `成交额` is stored in the provider raw unit documented by the model comments, and the flow-over-turnover ratio must compare yuan to yuan.
- Gross申购 and gross赎回 are not derivable from the net share delta alone; the first-stage pipeline estimates net flow only.

## Out of Scope

The first-stage handoff does not include:

- Gross申购/赎回 split.
- Fund holder-disclosure parsing or 汇金/证金/险资/国资 holder classification.
- ETF or index financing/margin aggregation.
- Dashboards, API presentation, or UI rendering.
- DAG schedule, retry, dependency, task-boundary, or SLA changes.
- Live-provider verification in tests.

## Focused Verification

Use these focused checks when touching the ETF quant pipeline or its handoff documentation:

```bash
uv run pytest test/download/test_etf_net_flow.py test/download/test_download_manager.py -k 'etf_net_flow or download_etf_quant_data or rebuild_etf_net_flow' -v
uv run pytest test/tools/test_db_common.py test/tools/test_db_scripts.py -k 'etf_quant or business_tables_include_etf_quant_pipeline_tables or clean_full_import or clean_full_matching_export' -v
uv run ruff check test/tools/test_db_common.py test/tools/test_db_scripts.py
```

Use `tools/run_tests.sh` for PostgreSQL-dependent coverage or full-suite validation. The focused commands above are offline checks for the calculation, orchestration seam, and business-table export/import/clean coverage relevant to this first-stage pipeline.
