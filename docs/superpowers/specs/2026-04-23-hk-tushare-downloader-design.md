# HK Tushare Downloader Replacement Design

## Problem

The current HK stock history downloader path uses
`download_history_data_stock_hk_ak`, and `Downloader.dl_history_data_stock_hk`
is bound directly to that AkShare implementation.

The requested change is to replace that active HK downloader with a Tushare
implementation while keeping the current upper-layer download flow usable.

The user explicitly wants compatibility with the current function signature and
returned columns, but also wants the AkShare implementation retained as a
fallback rather than deleted.

## Decision

Adopt a dual-implementation design:

- add a new Tushare-backed HK history downloader
- switch `Downloader.dl_history_data_stock_hk` to the Tushare version
- keep `download_history_data_stock_hk_ak` available for direct fallback use

This keeps the replacement localized to the downloader binding while preserving
an easy rollback path.

## Design

### Scope

This change covers only the HK history downloader implementation and its direct
tests.

It should:

- preserve the current `dl_history_data_stock_hk` call signature
- preserve the returned DataFrame schema expected by
  `save_history_data_hk_stock`
- keep `download_manager.py` and multiprocessing callers unchanged
- retain the AkShare HK downloader function in the codebase
- make the active `Downloader` binding use Tushare by default

It should not:

- redesign the broader downloader provider architecture
- change storage table names or HK storage write behavior
- change the upper-layer download workflow in `download_manager.py`
- remove the AkShare implementation

### Main workflow

The active HK history download flow should behave like this:

1. caller invokes `Downloader.dl_history_data_stock_hk(stock_id, start_date,
   end_date, period, adjust)`
2. `Downloader` routes the call to a new Tushare-backed function in
   `download/dl/downloader_tushare.py`
3. the function validates the 5-digit HK stock code and normalizes dates to
   `YYYYMMDD`
4. the function converts the code into Tushare HK format such as `00700.HK`
5. the function requests HK history data from Tushare using the matching HK
   interface
6. the returned data is mapped into the repository's existing HK history column
   names and data types
7. the DataFrame is returned to existing storage code unchanged at the API
   boundary

### File responsibilities

#### `download/dl/downloader_tushare.py`

Add a new HK history downloader function with the same public signature as the
existing AkShare function.

This function should:

- require a configured `TUSHARE_TOKEN` through the existing decorator flow
- normalize supported date input formats using the existing date conversion
  helper
- convert 5-digit HK symbols to Tushare HK codes
- fetch HK daily history data from Tushare
- map returned fields into the repository column names used by HK storage
- add the plain 5-digit stock code column expected by current consumers
- convert the date column to pandas datetime
- fill numeric nulls with `0` to match the existing HK downloader behavior

The function keeps `adjust` in the signature for compatibility, even though the
Tushare HK data path does not mirror AkShare's adjust behavior one-to-one. The
implementation should keep behavior explicit and safe rather than pretending to
support unsupported adjustment semantics.

#### `download/dl/downloader.py`

Update the `Downloader` binding so `dl_history_data_stock_hk` points to the new
Tushare function.

The AkShare function should remain imported or otherwise remain directly
available so the codebase still has a fallback implementation.

#### Tests

Extend downloader tests in two places:

- `test/download/dl/test_downloader_tushare.py` for Tushare HK unit coverage
- `test/download/dl/test_downloader.py` for the active `Downloader` routing

### Data mapping

The returned DataFrame must stay compatible with the existing HK storage model.
At minimum, the Tushare implementation must return these current columns when
available from Tushare or derive them safely when needed:

- `日期`
- `股票代码`
- `开盘`
- `收盘`
- `最高`
- `最低`
- `成交量`
- `成交额`
- `涨跌幅(%)`
- `换手率(%)`

If Tushare omits fields that the current HK table allows as nullable, the
implementation may leave them absent only if current save behavior tolerates
that. Otherwise it should supply explicit values rather than silently changing
write behavior.

### Error handling

Errors should remain explicit:

- missing token raises the existing `ConnectionError`
- invalid stock IDs fail validation clearly
- unsupported or empty responses should not masquerade as success
- if Tushare returns no rows for the requested range, the function should return
  an empty DataFrame rather than inventing values

No broad error swallowing should be added.

### Testing and validation expectations

The implementation should be verified by targeted tests that confirm:

1. missing token still raises the expected error
2. HK stock code and date normalization are correct
3. Tushare response fields are mapped to the existing HK schema
4. `Downloader.dl_history_data_stock_hk` now routes to Tushare
5. the legacy AkShare HK downloader remains callable

## Non-goals

- a generalized provider-selection framework for all downloaders
- intraday HK Tushare downloading
- changing HK storage schema
- removing AkShare fallback code
