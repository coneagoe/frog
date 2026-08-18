# ETF Index Mapping Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement GitHub issue #68 seam-only: centralized ETF-to-index resolution plus deterministic diagnostics for future derived ETF flow preparation, while raw ETF share/size storage remains independent.

**Architecture:** Add immutable metadata to the existing core index catalogue and create a focused `download/etf_index_mapping.py` resolver for ETF code normalization, pinned ETF-to-index mapping, and diagnostic results. Expose a narrow derived-flow preparation helper without calculating or persisting derived rows, and prove raw share/size storage still accepts unmapped ETFs.

**Tech Stack:** Python 3.11+, `StrEnum`, `dataclass`, `MappingProxyType`, pandas, SQLAlchemy, pytest, Ruff, mypy.

## Global Constraints

- Use `uv run` for Python commands in this repo.
- Do not edit DAG schedules, dependencies, retries, task boundaries, or SLA.
- Mock external providers; do not call live Tushare in tests.
- Scope is seam-only: no persisted derived ETF flow table, no new Tushare provider calls, no holder-disclosure parsing, no financing aggregation, no UI output, no DAG schedule changes.
- Raw `StorageDB.save_etf_share_size()` eligibility remains independent of ETF-to-index mapping.
- `CORE_INDEX_TS_CODES` remains the source used by raw index turnover downloads.
- Unsupported or missing mappings must not silently fall back to a broad default index.
- Resolver output must be deterministic and side-effect free.
- Finite business status values must use enums, not raw strings.

---

## File Structure

- Modify: `download/core_indexes.py`
  - Add immutable display-name metadata for existing `CoreIndexGroup` values.
  - Keep `CORE_INDEX_TS_CODES` unchanged as the raw index turnover source.
- Create: `download/etf_index_mapping.py`
  - Own ETF code normalization, pinned ETF-to-index mapping, diagnostic statuses, typed result, resolver, and preparation context helper.
- Modify: `download/download_manager.py`
  - Import and expose a module-level `prepare_etf_flow_index_context(etf_code: str)` helper that delegates to the resolver.
  - Do not wire the helper into raw `download_etf_share_size()`.
- Modify: `test/download/test_core_indexes.py`
  - Cover display metadata completeness and no change to pinned turnover mapping.
- Create: `test/download/test_etf_index_mapping.py`
  - Cover normalization, mapped ETFs, unsupported ETFs, missing mappings, invalid codes, immutability, and preparation diagnostics.
- Modify: `test/download/test_download_manager.py`
  - Cover the manager-level seam and raw share/size independence.
- Modify: `test/storage/test_storage_db.py`
  - Add a raw-storage independence test for an unmapped but valid ETF code inside `TestETFShareSizeStorage`.

---

### Task 1: Core Index Catalogue Metadata

**Files:**
- Modify: `download/core_indexes.py`
- Modify: `test/download/test_core_indexes.py`

**Interfaces:**
- Consumes: `CoreIndexGroup`, `CORE_INDEX_TS_CODES`.
- Produces: `CORE_INDEX_DISPLAY_NAMES: MappingProxyType[CoreIndexGroup, str]`.

- [ ] **Step 1: Write the failing tests**

Append to `test/download/test_core_indexes.py`:

```python
def test_core_index_display_names_cover_pinned_groups():
    from download.core_indexes import CORE_INDEX_DISPLAY_NAMES

    assert CORE_INDEX_DISPLAY_NAMES == {
        CoreIndexGroup.CSI_300: "沪深300",
        CoreIndexGroup.SSE_50: "上证50",
        CoreIndexGroup.SSE_180: "上证180",
        CoreIndexGroup.CSI_500: "中证500",
        CoreIndexGroup.CSI_800: "中证800",
        CoreIndexGroup.CSI_1000: "中证1000",
        CoreIndexGroup.CHINEXT: "创业板指",
        CoreIndexGroup.STAR_50: "科创50",
        CoreIndexGroup.SZSE_100: "深证100",
    }


def test_core_index_display_names_match_turnover_mapping_keys():
    from download.core_indexes import CORE_INDEX_DISPLAY_NAMES

    assert set(CORE_INDEX_DISPLAY_NAMES) == set(CORE_INDEX_TS_CODES)
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run:

```bash
uv run pytest test/download/test_core_indexes.py -v
```

Expected: fails because `CORE_INDEX_DISPLAY_NAMES` does not exist.

- [ ] **Step 3: Add immutable display metadata**

In `download/core_indexes.py`, add after `CORE_INDEX_TS_CODES`:

```python
CORE_INDEX_DISPLAY_NAMES = MappingProxyType(
    {
        CoreIndexGroup.CSI_300: "沪深300",
        CoreIndexGroup.SSE_50: "上证50",
        CoreIndexGroup.SSE_180: "上证180",
        CoreIndexGroup.CSI_500: "中证500",
        CoreIndexGroup.CSI_800: "中证800",
        CoreIndexGroup.CSI_1000: "中证1000",
        CoreIndexGroup.CHINEXT: "创业板指",
        CoreIndexGroup.STAR_50: "科创50",
        CoreIndexGroup.SZSE_100: "深证100",
    }
)
```

- [ ] **Step 4: Verify the catalogue tests pass**

Run:

```bash
uv run pytest test/download/test_core_indexes.py -v
```

Expected: pass.

- [ ] **Step 5: Commit the task**

```bash
git add download/core_indexes.py test/download/test_core_indexes.py
git commit -m "feat: add core index diagnostic metadata"
```

---

### Task 2: ETF Resolver and Diagnostics

**Files:**
- Create: `download/etf_index_mapping.py`
- Create: `test/download/test_etf_index_mapping.py`

**Interfaces:**
- Consumes: `CoreIndexGroup`, `CORE_INDEX_TS_CODES`, `CORE_INDEX_DISPLAY_NAMES`.
- Produces: `ETFIndexMappingStatus`, `ETFIndexResolution`, `ETF_CORE_INDEX_GROUPS`, `UNSUPPORTED_ETF_CODES`, `normalize_etf_code(etf_code: str) -> str | None`, `resolve_etf_index(etf_code: str) -> ETFIndexResolution`.

- [ ] **Step 1: Write the failing resolver tests**

Create `test/download/test_etf_index_mapping.py`:

```python
import pytest

from download.core_indexes import CORE_INDEX_TS_CODES, CoreIndexGroup
from download.etf_index_mapping import (
    ETF_CORE_INDEX_GROUPS,
    UNSUPPORTED_ETF_CODES,
    ETFIndexMappingStatus,
    normalize_etf_code,
    resolve_etf_index,
)


def test_normalize_etf_code_accepts_bare_and_suffixed_provider_codes():
    assert normalize_etf_code("510300") == "510300"
    assert normalize_etf_code("510300.SH") == "510300"
    assert normalize_etf_code("159915.SZ") == "159915"
    assert normalize_etf_code(" 588000.SH ") == "588000"


def test_normalize_etf_code_rejects_invalid_values():
    assert normalize_etf_code("") is None
    assert normalize_etf_code("51030") is None
    assert normalize_etf_code("5103000") is None
    assert normalize_etf_code("ABCDEF") is None
    assert normalize_etf_code("510300.HK") is None
    assert normalize_etf_code("510300.SH.EXTRA") is None


def test_resolve_core_etf_examples_to_pinned_indexes():
    cases = {
        "510300.SH": (CoreIndexGroup.CSI_300, "000300.SH", "沪深300"),
        "510310": (CoreIndexGroup.CSI_300, "000300.SH", "沪深300"),
        "159919.SZ": (CoreIndexGroup.CSI_300, "000300.SH", "沪深300"),
        "510050.SH": (CoreIndexGroup.SSE_50, "000016.SH", "上证50"),
        "510180.SH": (CoreIndexGroup.SSE_180, "000010.SH", "上证180"),
        "510500.SH": (CoreIndexGroup.CSI_500, "000905.SH", "中证500"),
        "515800.SH": (CoreIndexGroup.CSI_800, "000906.SH", "中证800"),
        "512100.SH": (CoreIndexGroup.CSI_1000, "000852.SH", "中证1000"),
        "159845.SZ": (CoreIndexGroup.CSI_1000, "000852.SH", "中证1000"),
        "159915.SZ": (CoreIndexGroup.CHINEXT, "399006.SZ", "创业板指"),
        "588000.SH": (CoreIndexGroup.STAR_50, "000688.SH", "科创50"),
        "588080.SH": (CoreIndexGroup.STAR_50, "000688.SH", "科创50"),
        "159901.SZ": (CoreIndexGroup.SZSE_100, "399330.SZ", "深证100"),
    }

    for etf_code, (group, ts_code, display_name) in cases.items():
        result = resolve_etf_index(etf_code)

        assert result.status == ETFIndexMappingStatus.MAPPED
        assert result.normalized_etf_code == etf_code.split(".")[0]
        assert result.core_index_group == group
        assert result.index_ts_code == ts_code
        assert result.index_display_name == display_name
        assert result.diagnostic_reason == "mapped_to_supported_core_index"


def test_resolve_invalid_code_returns_invalid_diagnostic_without_index():
    result = resolve_etf_index("not-an-etf")

    assert result.status == ETFIndexMappingStatus.INVALID_CODE
    assert result.normalized_etf_code is None
    assert result.core_index_group is None
    assert result.index_ts_code is None
    assert result.index_display_name is None
    assert result.diagnostic_reason == "invalid_etf_code"


def test_resolve_known_unsupported_etf_returns_unsupported_diagnostic():
    result = resolve_etf_index("510880.SH")

    assert result.status == ETFIndexMappingStatus.UNSUPPORTED_ETF
    assert result.normalized_etf_code == "510880"
    assert result.core_index_group is None
    assert result.index_ts_code is None
    assert result.index_display_name is None
    assert result.diagnostic_reason == "unsupported_etf_without_trusted_core_index_mapping"


def test_resolve_valid_but_absent_etf_returns_missing_mapping_diagnostic():
    result = resolve_etf_index("560000.SH")

    assert result.status == ETFIndexMappingStatus.MISSING_MAPPING
    assert result.normalized_etf_code == "560000"
    assert result.core_index_group is None
    assert result.index_ts_code is None
    assert result.index_display_name is None
    assert result.diagnostic_reason == "missing_etf_index_mapping"


def test_etf_core_index_groups_are_immutable():
    with pytest.raises(TypeError):
        ETF_CORE_INDEX_GROUPS["560000"] = CoreIndexGroup.CSI_300  # type: ignore[index]


def test_unsupported_etf_codes_do_not_overlap_mapped_codes():
    assert set(UNSUPPORTED_ETF_CODES).isdisjoint(ETF_CORE_INDEX_GROUPS)


def test_all_mapped_etfs_point_to_supported_core_indexes():
    assert set(ETF_CORE_INDEX_GROUPS.values()).issubset(set(CORE_INDEX_TS_CODES))
```

- [ ] **Step 2: Run the resolver tests and confirm failure**

Run:

```bash
uv run pytest test/download/test_etf_index_mapping.py -v
```

Expected: fails because `download.etf_index_mapping` does not exist.

- [ ] **Step 3: Implement the resolver**

Create `download/etf_index_mapping.py`:

```python
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from download.core_indexes import CORE_INDEX_DISPLAY_NAMES, CORE_INDEX_TS_CODES, CoreIndexGroup


class ETFIndexMappingStatus(StrEnum):
    MAPPED = "mapped"
    UNSUPPORTED_ETF = "unsupported_etf"
    MISSING_MAPPING = "missing_mapping"
    INVALID_CODE = "invalid_code"


@dataclass(frozen=True)
class ETFIndexResolution:
    etf_code: str
    normalized_etf_code: str | None
    status: ETFIndexMappingStatus
    core_index_group: CoreIndexGroup | None
    index_ts_code: str | None
    index_display_name: str | None
    diagnostic_reason: str


ETF_CORE_INDEX_GROUPS = MappingProxyType(
    {
        "510300": CoreIndexGroup.CSI_300,
        "510310": CoreIndexGroup.CSI_300,
        "159919": CoreIndexGroup.CSI_300,
        "510050": CoreIndexGroup.SSE_50,
        "510180": CoreIndexGroup.SSE_180,
        "510500": CoreIndexGroup.CSI_500,
        "515800": CoreIndexGroup.CSI_800,
        "512100": CoreIndexGroup.CSI_1000,
        "159845": CoreIndexGroup.CSI_1000,
        "159915": CoreIndexGroup.CHINEXT,
        "588000": CoreIndexGroup.STAR_50,
        "588080": CoreIndexGroup.STAR_50,
        "159901": CoreIndexGroup.SZSE_100,
    }
)

UNSUPPORTED_ETF_CODES = frozenset({"510880"})


def normalize_etf_code(etf_code: str) -> str | None:
    candidate = str(etf_code).strip()
    if not candidate:
        return None

    parts = candidate.split(".")
    if len(parts) == 1:
        bare_code = parts[0]
    elif len(parts) == 2 and parts[1] in {"SH", "SZ"}:
        bare_code = parts[0]
    else:
        return None

    if len(bare_code) != 6 or not bare_code.isdigit():
        return None
    return bare_code


def resolve_etf_index(etf_code: str) -> ETFIndexResolution:
    normalized_code = normalize_etf_code(etf_code)
    if normalized_code is None:
        return ETFIndexResolution(
            etf_code=etf_code,
            normalized_etf_code=None,
            status=ETFIndexMappingStatus.INVALID_CODE,
            core_index_group=None,
            index_ts_code=None,
            index_display_name=None,
            diagnostic_reason="invalid_etf_code",
        )

    if normalized_code in UNSUPPORTED_ETF_CODES:
        return ETFIndexResolution(
            etf_code=etf_code,
            normalized_etf_code=normalized_code,
            status=ETFIndexMappingStatus.UNSUPPORTED_ETF,
            core_index_group=None,
            index_ts_code=None,
            index_display_name=None,
            diagnostic_reason="unsupported_etf_without_trusted_core_index_mapping",
        )

    group = ETF_CORE_INDEX_GROUPS.get(normalized_code)
    if group is None:
        return ETFIndexResolution(
            etf_code=etf_code,
            normalized_etf_code=normalized_code,
            status=ETFIndexMappingStatus.MISSING_MAPPING,
            core_index_group=None,
            index_ts_code=None,
            index_display_name=None,
            diagnostic_reason="missing_etf_index_mapping",
        )

    return ETFIndexResolution(
        etf_code=etf_code,
        normalized_etf_code=normalized_code,
        status=ETFIndexMappingStatus.MAPPED,
        core_index_group=group,
        index_ts_code=CORE_INDEX_TS_CODES[group],
        index_display_name=CORE_INDEX_DISPLAY_NAMES[group],
        diagnostic_reason="mapped_to_supported_core_index",
    )
```

- [ ] **Step 4: Verify the resolver tests pass**

Run:

```bash
uv run pytest test/download/test_etf_index_mapping.py -v
```

Expected: pass.

- [ ] **Step 5: Commit the task**

```bash
git add download/etf_index_mapping.py test/download/test_etf_index_mapping.py
git commit -m "feat: add ETF index mapping diagnostics resolver"
```

---

### Task 3: Derived-Flow Preparation Seam

**Files:**
- Modify: `download/etf_index_mapping.py`
- Modify: `download/download_manager.py`
- Modify: `test/download/test_etf_index_mapping.py`
- Modify: `test/download/test_download_manager.py`

**Interfaces:**
- Consumes: `resolve_etf_index(etf_code: str) -> ETFIndexResolution`.
- Produces: `ETFFlowIndexContext` and `prepare_etf_flow_index_context(etf_code: str) -> ETFFlowIndexContext` in `download.etf_index_mapping` plus a module-level helper with the same signature in `download.download_manager`.

- [ ] **Step 1: Write the failing seam tests**

Append to `test/download/test_etf_index_mapping.py`:

```python
from download.etf_index_mapping import prepare_etf_flow_index_context


def test_prepare_etf_flow_index_context_returns_mapped_index_identifier():
    context = prepare_etf_flow_index_context("510300.SH")

    assert context.should_calculate is True
    assert context.etf_code == "510300.SH"
    assert context.normalized_etf_code == "510300"
    assert context.index_ts_code == "000300.SH"
    assert context.diagnostic.status == ETFIndexMappingStatus.MAPPED
    assert context.diagnostic.diagnostic_reason == "mapped_to_supported_core_index"


def test_prepare_etf_flow_index_context_returns_diagnostic_for_missing_mapping():
    context = prepare_etf_flow_index_context("560000.SH")

    assert context.should_calculate is False
    assert context.etf_code == "560000.SH"
    assert context.normalized_etf_code == "560000"
    assert context.index_ts_code is None
    assert context.diagnostic.status == ETFIndexMappingStatus.MISSING_MAPPING
    assert context.diagnostic.diagnostic_reason == "missing_etf_index_mapping"


def test_prepare_etf_flow_index_context_returns_diagnostic_for_unsupported_mapping():
    context = prepare_etf_flow_index_context("510880.SH")

    assert context.should_calculate is False
    assert context.normalized_etf_code == "510880"
    assert context.index_ts_code is None
    assert context.diagnostic.status == ETFIndexMappingStatus.UNSUPPORTED_ETF
    assert context.diagnostic.diagnostic_reason == "unsupported_etf_without_trusted_core_index_mapping"


def test_prepare_etf_flow_index_context_returns_diagnostic_for_invalid_code():
    context = prepare_etf_flow_index_context("bad-code")

    assert context.should_calculate is False
    assert context.normalized_etf_code is None
    assert context.index_ts_code is None
    assert context.diagnostic.status == ETFIndexMappingStatus.INVALID_CODE
    assert context.diagnostic.diagnostic_reason == "invalid_etf_code"
```

Append inside `TestDownloadManager` in `test/download/test_download_manager.py`:

```python
    def test_prepare_etf_flow_index_context_exposes_manager_seam_for_mapped_etf(self):
        from download.download_manager import prepare_etf_flow_index_context
        from download.etf_index_mapping import ETFIndexMappingStatus

        context = prepare_etf_flow_index_context("159915.SZ")

        assert context.should_calculate is True
        assert context.normalized_etf_code == "159915"
        assert context.index_ts_code == "399006.SZ"
        assert context.diagnostic.status == ETFIndexMappingStatus.MAPPED

    def test_prepare_etf_flow_index_context_exposes_manager_seam_for_missing_mapping(self):
        from download.download_manager import prepare_etf_flow_index_context
        from download.etf_index_mapping import ETFIndexMappingStatus

        context = prepare_etf_flow_index_context("560000.SH")

        assert context.should_calculate is False
        assert context.normalized_etf_code == "560000"
        assert context.index_ts_code is None
        assert context.diagnostic.status == ETFIndexMappingStatus.MISSING_MAPPING
```

- [ ] **Step 2: Run the seam tests and confirm failure**

Run:

```bash
uv run pytest test/download/test_etf_index_mapping.py test/download/test_download_manager.py -k 'flow_index_context or manager_seam' -v
```

Expected: fails because `prepare_etf_flow_index_context` and `ETFFlowIndexContext` do not exist.

- [ ] **Step 3: Implement the preparation context**

In `download/etf_index_mapping.py`, add below `ETFIndexResolution` or below `resolve_etf_index()`:

```python
@dataclass(frozen=True)
class ETFFlowIndexContext:
    etf_code: str
    normalized_etf_code: str | None
    should_calculate: bool
    index_ts_code: str | None
    diagnostic: ETFIndexResolution


def prepare_etf_flow_index_context(etf_code: str) -> ETFFlowIndexContext:
    diagnostic = resolve_etf_index(etf_code)
    return ETFFlowIndexContext(
        etf_code=etf_code,
        normalized_etf_code=diagnostic.normalized_etf_code,
        should_calculate=diagnostic.status == ETFIndexMappingStatus.MAPPED,
        index_ts_code=diagnostic.index_ts_code,
        diagnostic=diagnostic,
    )
```

In `download/download_manager.py`, add imports near the existing imports:

```python
from download.etf_index_mapping import ETFFlowIndexContext
from download.etf_index_mapping import prepare_etf_flow_index_context as _prepare_etf_flow_index_context
```

Add a module-level helper before `DownloadManager`:

```python
def prepare_etf_flow_index_context(etf_code: str) -> ETFFlowIndexContext:
    return _prepare_etf_flow_index_context(etf_code)
```

- [ ] **Step 4: Verify the seam tests pass**

Run:

```bash
uv run pytest test/download/test_etf_index_mapping.py test/download/test_download_manager.py -k 'flow_index_context or manager_seam' -v
```

Expected: pass.

- [ ] **Step 5: Commit the task**

```bash
git add download/etf_index_mapping.py download/download_manager.py test/download/test_etf_index_mapping.py test/download/test_download_manager.py
git commit -m "feat: add ETF flow index preparation seam"
```

---

### Task 4: Raw Share/Size Independence

**Files:**
- Modify: `test/download/test_download_manager.py`
- Modify: `test/storage/test_storage_db.py`

**Interfaces:**
- Consumes: `DownloadManager.download_etf_share_size(...) -> bool`.
- Consumes: `StorageDB.save_etf_share_size(df: pd.DataFrame) -> bool`.
- Consumes: `resolve_etf_index(etf_code: str) -> ETFIndexResolution`.
- Produces: tests proving raw share/size storage does not depend on resolver success.

- [ ] **Step 1: Add the manager independence test**

Append inside `TestDownloadManager` in `test/download/test_download_manager.py`:

```python
    def test_download_etf_share_size_saves_unmapped_etf_without_resolver_dependency(self, monkeypatch):
        from download.etf_index_mapping import ETFIndexMappingStatus, resolve_etf_index

        manager, storage, downloader = _make_manager(monkeypatch)
        df = pd.DataFrame(
            [
                {
                    "基金代码": "560000",
                    "日期": "2024-01-05",
                    "收盘": 1.5,
                    "单位净值": 1.48,
                    "总份额": 10.0,
                    "总规模": 14.8,
                }
            ]
        )
        downloader.dl_etf_share_size.return_value = df
        storage.save_etf_share_size.return_value = True

        diagnostic = resolve_etf_index("560000.SH")
        result = manager.download_etf_share_size(ts_code="560000.SH", start_date="20240101", end_date="20240105")

        assert diagnostic.status == ETFIndexMappingStatus.MISSING_MAPPING
        assert result is True
        downloader.dl_etf_share_size.assert_called_once_with(
            ts_code="560000.SH",
            trade_date="",
            start_date="20240101",
            end_date="20240105",
        )
        storage.save_etf_share_size.assert_called_once_with(df)
```

- [ ] **Step 2: Add the storage independence test**

Append inside `TestETFShareSizeStorage` in `test/storage/test_storage_db.py`:

```python
    def test_save_etf_share_size_accepts_unmapped_valid_etf_code(self, sqlite_storage):
        from download.etf_index_mapping import ETFIndexMappingStatus, resolve_etf_index

        db, engine = sqlite_storage
        df = pd.DataFrame(
            {
                "ts_code": ["560000.SH"],
                "trade_date": ["20240105"],
                "close": [1.5],
                "nav": [1.48],
                "total_share": [10.0],
                "total_size": [14.8],
            }
        )

        diagnostic = resolve_etf_index("560000.SH")
        assert diagnostic.status == ETFIndexMappingStatus.MISSING_MAPPING
        assert db.save_etf_share_size(df) is True

        saved = pd.read_sql(
            f'SELECT * FROM {tb_name_etf_share_size} WHERE "{COL_ETF_ID}" = "560000"',
            engine,
        )
        assert len(saved) == 1
        assert saved.iloc[0][COL_CLOSE] == 1.5
        assert saved.iloc[0][COL_NAV] == 1.48
        assert saved.iloc[0][COL_ETF_TOTAL_SHARE] == 10.0
        assert saved.iloc[0][COL_ETF_TOTAL_SIZE] == 14.8
```

- [ ] **Step 3: Run the independence tests**

Run:

```bash
uv run pytest test/download/test_download_manager.py -k 'unmapped_etf_without_resolver_dependency' -v
uv run pytest test/storage/test_storage_db.py -k 'save_etf_share_size_accepts_unmapped_valid_etf_code' -v
```

Expected: both pass.

- [ ] **Step 4: Confirm raw implementation stayed independent**

Run:

```bash
git diff -- download/download_manager.py storage/storage_db.py storage/model/etf_share_size.py
```

Expected: `download_etf_share_size()` still delegates directly to downloader and `get_storage().save_etf_share_size(df)`; `storage/storage_db.py` and `storage/model/etf_share_size.py` have no functional changes from this issue.

- [ ] **Step 5: Commit the task**

```bash
git add test/download/test_download_manager.py test/storage/test_storage_db.py
git commit -m "test: preserve raw ETF share size independence"
```

---

### Task 5: Final Verification and Issue Review

**Files:**
- Inspect: all changed source and test files.
- Modify only if verification finds a concrete issue.

**Interfaces:**
- Consumes: all outputs from Tasks 1-4.
- Produces: verified issue #68 implementation ready for final handoff.

- [ ] **Step 1: Run the focused issue suite**

Run:

```bash
uv run pytest test/download/test_core_indexes.py test/download/test_etf_index_mapping.py test/download/test_download_manager.py test/storage/test_storage_db.py -k 'core_index or etf_index_mapping or flow_index_context or manager_seam or etf_share_size' -v
```

Expected: pass.

- [ ] **Step 2: Run formatting and lint checks on touched Python files**

Run:

```bash
uv run ruff format download/core_indexes.py download/etf_index_mapping.py download/download_manager.py test/download/test_core_indexes.py test/download/test_etf_index_mapping.py test/download/test_download_manager.py test/storage/test_storage_db.py
uv run ruff check download/core_indexes.py download/etf_index_mapping.py download/download_manager.py test/download/test_core_indexes.py test/download/test_etf_index_mapping.py test/download/test_download_manager.py test/storage/test_storage_db.py
```

Expected: both pass.

- [ ] **Step 3: Run a type check if touched files are in mypy scope**

Run:

```bash
uv run mypy
```

Expected: pass or fail only on pre-existing unrelated errors. If failures touch `download/core_indexes.py`, `download/etf_index_mapping.py`, or `download/download_manager.py`, fix them before continuing.

- [ ] **Step 4: Review the implementation against the acceptance criteria**

Confirm all statements are true:

```text
Core ETF groups resolve to pinned index identifiers used by CORE_INDEX_TS_CODES.
Raw share/size storage remains eligible when an ETF cannot be mapped.
Derived-flow preparation returns diagnostic reasons for unmapped or unsupported ETFs.
Mapping behavior is centralized in download/etf_index_mapping.py and core index metadata.
Tests cover successful core mapping, unsupported/non-core ETFs, and diagnostic output.
```

- [ ] **Step 5: Run simplify review before declaring completion**

Invoke the `simplify` skill and apply only targeted simplifications that preserve behavior and issue scope.

- [ ] **Step 6: Commit final verification fixes if any were made**

If files changed during final verification:

```bash
git add <changed-files>
git commit -m "fix: harden ETF index mapping diagnostics"
```

If no files changed, do not create an empty commit.
