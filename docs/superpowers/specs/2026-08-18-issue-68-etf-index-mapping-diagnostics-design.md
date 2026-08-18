# Issue 68 ETF Index Mapping Diagnostics Design

## Purpose

Implement the ETF-to-index mapping diagnostics seam required by GitHub issue #68. The change makes it explicit which ETFs can produce derived ETF flow or turnover ratios and which ETFs only remain eligible for raw share/size storage because no trusted supported index mapping exists.

## Scope

This issue covers the mapping and diagnostic seam only. It does not add a persisted derived ETF flow table, new Tushare provider calls, holder-disclosure parsing, financing aggregation, UI output, or DAG schedule changes.

## Existing Context

- `download/core_indexes.py` already defines the pinned broad-market index groups and Tushare `ts_code` values used by the raw index turnover layer.
- `DownloadManager.download_core_index_daily_turnover()` already downloads turnover for those pinned index identifiers.
- `StorageDB.save_etf_share_size()` persists raw ETF share/size rows independently of index mapping, and that behavior must remain valid for unmapped ETFs.
- The broader ETF quant design requires derived-flow calculation to skip missing ETF-to-index mappings with diagnostic reasons rather than writing fallback ratios.

## Recommended Approach

Add a small centralized resolver module that owns ETF-to-index mapping decisions and diagnostic output. Keep raw storage unchanged, and make derived-flow preparation call the resolver before joining ETF share/size rows to index turnover rows.

This keeps mapping behavior auditable and avoids scattering hardcoded ETF/index strings through manager or storage code.

## Components

### Core index catalogue

Extend `download/core_indexes.py` or a tightly adjacent module with metadata for the pinned core index set:

- Stable `CoreIndexGroup` value.
- Tushare index `ts_code` already used by `CORE_INDEX_TS_CODES`.
- Optional display name for diagnostics and tests.

The existing `CORE_INDEX_TS_CODES` mapping remains the source used by raw index turnover downloads.

### ETF index resolver

Add a focused resolver, for example `download/etf_index_mapping.py`, with:

- A centralized pinned ETF/group mapping for the core ETF families that should be allowed to produce derived ratios.
- A `resolve_etf_index(etf_code: str)` helper returning a typed result with status, optional `CoreIndexGroup`, optional index `ts_code`, and diagnostic reason.
- Normalization for ETF codes with or without exchange suffixes, so callers can pass raw provider codes safely.

Recommended diagnostic statuses:

- `mapped`: ETF resolved to a supported pinned index.
- `unsupported_etf`: ETF is known or valid raw ETF data, but no trusted supported index mapping is pinned.
- `missing_mapping`: ETF code is absent from the resolver mapping.
- `invalid_code`: ETF code cannot be normalized into the expected six-digit ETF identifier.

### Derived-flow preparation seam

Add a narrow preparation helper, for example `prepare_etf_flow_index_context(etf_code: str)`, that delegates to the resolver and returns either:

- The mapped index identifier needed to query or join `index_daily_turnover`.
- A diagnostic object explaining why derived-flow ratio calculation must be skipped.

This helper should not calculate flow amounts or persist derived rows. It creates the stable seam future derived-flow code will use.

## Data Flow

1. Raw ETF share/size download and storage continue to accept any provider-supported ETF row.
2. Derived-flow preparation normalizes the ETF code and calls the centralized resolver.
3. Mapped ETFs proceed with the pinned index `ts_code` already used by raw index turnover storage.
4. Unmapped, unsupported, or invalid ETFs return a diagnostic reason and are skipped by derived ratio calculation.

## Error Handling

- Raw share/size storage must not fail only because an ETF is unmapped.
- Resolver output should be deterministic and side-effect free.
- Diagnostics should be explicit enough for logs, tests, and future API/CLI output without requiring callers to parse free-form exception text.
- Unsupported or missing mappings should not silently fall back to a broad default index.

## Testing

Add offline tests covering:

- Core ETF examples resolve to pinned index identifiers used by `CORE_INDEX_TS_CODES`.
- ETF code normalization handles bare and suffixed provider codes.
- Unsupported or non-core ETFs return a diagnostic status and do not produce an index `ts_code`.
- Missing mappings are distinguishable from invalid ETF codes.
- Raw `save_etf_share_size()` eligibility remains independent of resolver success.
- Derived-flow preparation returns diagnostic output for missing or unsupported mappings.

Recommended focused command:

```bash
uv run pytest test/download/test_core_indexes.py test/download/test_etf_index_mapping.py test/storage/test_storage_db.py -k 'core_index or etf_index_mapping or etf_share_size' -v
```

## Definition of Done

- Mapping behavior is centralized in one resolver/catalogue path.
- Core ETF groups resolve to pinned index identifiers used by the raw index turnover layer.
- Raw ETF share/size storage remains valid for unmapped ETFs.
- Derived-flow preparation returns clear diagnostic output instead of producing an incorrect ratio.
- Tests cover successful mapping, unsupported/non-core ETFs, missing/invalid mapping diagnostics, and raw-storage independence.
