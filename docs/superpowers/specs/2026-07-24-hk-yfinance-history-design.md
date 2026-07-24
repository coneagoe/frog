# HK stock yfinance history provider design

**Date:** 2026-07-24

## Goal

Add yfinance as the preferred source for Hong Kong stock daily unadjusted (BFQ) history. This avoids TuShare's `hk_daily` request-frequency limit while retaining TuShare and AkShare as fallbacks.

## Scope

- Support Hong Kong stocks only.
- Support `PeriodType.DAILY` and `AdjustType.BFQ` only.
- Use raw Yahoo Finance OHLCV values, not adjusted prices.
- Make yfinance the first default HK history provider.

Out of scope: A-share history, non-daily bars, adjusted HK history, schema changes, and changes to the download manager fallback algorithm.

## Architecture

Create `download/dl/downloader_yfinance.py` with a dedicated HK history function matching `StockHistoryDownloader`:

```python
download_history_data_stock_hk_yf(stock_id, start_date, end_date, period, adjust)
```

The function is the sole yfinance boundary. It validates supported parameters, fetches and normalizes provider output, and returns the project-standard HK history DataFrame.

Register the function in `HK_STOCK_HISTORY_PROVIDER_DOWNLOADERS` in `download/dl/downloader.py`. No new `Downloader` method is required because `dl_history_data_stock_hk_by_provider` already dispatches through the registry.

Register `yfinance` in `download/provider_order.py`, changing the default order to:

```text
yfinance,tushare,akshare
```

`DownloadManager._download_hk_stock_history_with_fallback` remains unchanged: it validates each provider result and automatically tries the next provider after a yfinance failure.

## yfinance request and normalization

1. Validate that the requested period is daily and the adjustment mode is BFQ. Raise `ValueError` otherwise.
2. Validate the input as a five-digit numeric HK stock ID. Convert it to Yahoo's canonical ticker by stripping leading zeroes and appending `.HK`; for example, `03738` becomes `3738.HK`.
3. Call `yfinance.Ticker(symbol).history()` with:
   - `interval="1d"`
   - `auto_adjust=False`
   - `actions=False`
   - `back_adjust=False`
   - `repair=False`
   - `raise_errors=True`
4. Convert the requested inclusive end date to yfinance's exclusive end boundary by adding one calendar day.
5. Require the returned `Open`, `High`, `Low`, `Close`, and `Volume` columns. Ignore `Adj Close`; it is Yahoo's corporate-action-adjusted close and is not BFQ data.
6. Normalize the exchange-local date index and OHLCV columns to the existing HK storage contract, add the original five-digit `stock_id`, and create amount values only if the established HK normalization contract requires them.

## Failure behavior

- A yfinance exception, `None`/empty result, or missing required OHLCV column is a provider failure.
- Invalid HK IDs and unsupported period/adjustment values produce explicit `ValueError`s at the provider boundary.
- The download manager logs failures and falls back to TuShare, then AkShare. It never persists incomplete provider output.

## Tests

All yfinance interactions are mocked; tests make no network calls.

- New downloader tests verify ticker conversion, inclusive-to-exclusive date conversion, explicit history arguments, raw OHLCV normalization, and preservation of the original stock ID.
- Cover empty results, provider exceptions, missing columns, invalid IDs, non-daily periods, and non-BFQ adjustments.
- Extend provider dispatch tests to confirm `yfinance` is registered as an HK provider.
- Update provider-order tests to expect the yfinance-first default and accept it as a configured provider.
- Retain existing manager fallback tests; add or adjust a focused assertion only if needed to demonstrate yfinance failure proceeds to the existing fallback chain.

## Verification

Run the focused downloader, provider-order, and download-manager test modules with `uv run pytest`. Run Ruff checks for changed Python files if implementation changes them.
