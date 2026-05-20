# Top10 Floatholders Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the `top10_floatholders` pipeline with the current TuShare schema by restoring `hold_ratio` in the downloader field list and adding `hold_float_ratio`, `hold_change`, and `holder_type` through download, storage, and tests.

**Architecture:** Keep the repository's existing explicit-contract pattern: `download/dl/downloader_tushare.py` owns the TuShare `fields` list, `storage/storage_db.py` owns the English-to-Chinese column mapping, and `storage/model/top10_floatholders.py` owns the ORM schema. Implement the change in two slices: first lock the downloader contract with tests, then extend constants, model, and save-path coverage without adding migration logic.

**Tech Stack:** Python 3.11+, Poetry, pandas, SQLAlchemy, pytest, pre-commit

---

## File map

- `download/dl/downloader_tushare.py` — source-of-truth TuShare field list for `top10_floatholders`; the current worktree already swapped `hold_ratio` out for `hold_float_ratio`, so the final implementation must end with **both** plus the other missing fields.
- `test/download/dl/test_downloader_tushare.py` — downloader contract tests; extend mock payloads and assert the full requested field list.
- `common/const.py` — human-readable Chinese column names for the three new stored fields.
- `storage/storage_db.py` — `COL_MAP_TOP10_FLOATHOLDERS` and `save_top10_floatholders()` ingestion path; once mapping is extended, the existing whitelist-based save logic can carry the new fields automatically.
- `storage/model/top10_floatholders.py` — ORM table definition for `top10_floatholders`; add three nullable non-primary-key columns.
- `test/storage/model/test_top10_floatholders.py` — schema-level assertions for the table columns.
- `test/storage/test_storage_db.py` — save-path regression tests; update raw DataFrame fixtures and persisted-column assertions for the new fields.

### Task 1: Lock the downloader field contract

**Files:**
- Modify: `test/download/dl/test_downloader_tushare.py`
- Modify: `download/dl/downloader_tushare.py`

- [ ] **Step 1: Write the failing downloader contract test**

Add a dedicated assertion for the exact field list and extend the success payload to include every field the downloader should request:

```python
def test_download_top10_floatholders_success(downloader_ts_module, monkeypatch):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")

    expected_fields = [
        "ts_code",
        "ann_date",
        "end_date",
        "holder_name",
        "hold_amount",
        "hold_ratio",
        "hold_float_ratio",
        "hold_change",
        "holder_type",
    ]
    assert module.top10_floatholders_fields == expected_fields

    mock_data = pd.DataFrame(
        {
            "ts_code": ["600600.SH"] * 2,
            "ann_date": ["20240315", "20231201"],
            "end_date": ["20231231", "20230930"],
            "holder_name": ["股东A", "股东B"],
            "hold_amount": [12345.6, 9999.0],
            "hold_ratio": [3.21, 2.10],
            "hold_float_ratio": [4.56, 3.20],
            "hold_change": [100.0, -50.0],
            "holder_type": ["机构", "个人"],
        }
    )
```

- [ ] **Step 2: Run the downloader tests to verify they fail**

Run:

```bash
poetry run pytest test/download/dl/test_downloader_tushare.py -k top10_floatholders -v
```

Expected: FAIL because `top10_floatholders_fields` does not yet equal the full 9-field list (`hold_ratio`, `hold_change`, and `holder_type` are missing in the current worktree state).

- [ ] **Step 3: Update the TuShare field list minimally**

In `download/dl/downloader_tushare.py`, make the final list explicit and ordered:

```python
top10_floatholders_fields = [
    "ts_code",
    "ann_date",
    "end_date",
    "holder_name",
    "hold_amount",
    "hold_ratio",
    "hold_float_ratio",
    "hold_change",
    "holder_type",
]
```

Do not add fallback logic or dynamic field assembly; keep the module-level list as the contract.

- [ ] **Step 4: Re-run the downloader tests**

Run:

```bash
poetry run pytest test/download/dl/test_downloader_tushare.py -k top10_floatholders -v
```

Expected: PASS for the `top10_floatholders` downloader tests.

- [ ] **Step 5: Commit the downloader contract slice**

Run:

```bash
git add test/download/dl/test_downloader_tushare.py download/dl/downloader_tushare.py
git commit -m "fix: complete top10 floatholders downloader fields" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Extend stored fields through constants, schema, and save-path tests

**Files:**
- Modify: `common/const.py`
- Modify: `storage/storage_db.py`
- Modify: `storage/model/top10_floatholders.py`
- Modify: `test/storage/model/test_top10_floatholders.py`
- Modify: `test/storage/test_storage_db.py`

- [ ] **Step 1: Write the failing storage/model tests**

First extend the model column assertion so the schema contract includes the new columns:

```python
for expected in [
    "股票代码",
    "公告日期",
    "截止日期",
    "股东名称",
    "持有数量（万股）",
    "占总流通股本持股比例",
    "占流通股本比例",
    "持股变动",
    "股东类型",
]:
    assert expected in columns, f"列 '{expected}' 不存在"
```

Then update the raw DataFrame factory and persisted-column assertions in `test/storage/test_storage_db.py`:

```python
from common.const import (
    COL_FLOAT_HOLDER_HOLD_AMOUNT,
    COL_FLOAT_HOLDER_HOLD_CHANGE,
    COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
    COL_FLOAT_HOLDER_TYPE,
)

def _make_raw_df(self):
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "600000.SH"],
            "ann_date": ["20240315", "20240316"],
            "end_date": ["20231231", "20231231"],
            "holder_name": ["股东A", "股东B"],
            "hold_amount": [12000.5, 9800.0],
            "hold_ratio": [2.13, 1.27],
            "hold_float_ratio": [3.45, 2.01],
            "hold_change": [150.0, -80.0],
            "holder_type": ["机构", "个人"],
        }
    )

assert COL_FLOAT_HOLDER_NAME in saved.columns
assert COL_FLOAT_HOLDER_HOLD_AMOUNT in saved.columns
assert COL_FLOAT_HOLDER_HOLD_RATIO in saved.columns
assert COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO in saved.columns
assert COL_FLOAT_HOLDER_HOLD_CHANGE in saved.columns
assert COL_FLOAT_HOLDER_TYPE in saved.columns
```

Also update the idempotency fixtures in the same file so every top10-floatholders test DataFrame carries the three new fields.

- [ ] **Step 2: Run the storage-focused tests to verify they fail**

Run:

```bash
poetry run pytest test/storage/model/test_top10_floatholders.py test/storage/test_storage_db.py -k top10_floatholders -v
```

Expected: FAIL with missing-column assertions and/or missing constant/import errors, because the code has not defined or stored the new fields yet.

- [ ] **Step 3: Implement the storage-side field support**

In `common/const.py`, define the new column names:

```python
COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO = "占流通股本比例"
COL_FLOAT_HOLDER_HOLD_CHANGE = "持股变动"
COL_FLOAT_HOLDER_TYPE = "股东类型"
```

In `storage/storage_db.py`, import those constants and extend the mapping:

```python
from common.const import (
    COL_FLOAT_HOLDER_HOLD_CHANGE,
    COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    COL_FLOAT_HOLDER_TYPE,
)

COL_MAP_TOP10_FLOATHOLDERS = {
    "ts_code": COL_STOCK_ID,
    "ann_date": COL_ANN_DATE,
    "end_date": COL_END_DATE,
    "holder_name": COL_FLOAT_HOLDER_NAME,
    "hold_amount": COL_FLOAT_HOLDER_HOLD_AMOUNT,
    "hold_ratio": COL_FLOAT_HOLDER_HOLD_RATIO,
    "hold_float_ratio": COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    "hold_change": COL_FLOAT_HOLDER_HOLD_CHANGE,
    "holder_type": COL_FLOAT_HOLDER_TYPE,
}
```

In `storage/model/top10_floatholders.py`, import the three constants and add nullable columns:

```python
from common.const import (
    COL_FLOAT_HOLDER_HOLD_CHANGE,
    COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    COL_FLOAT_HOLDER_TYPE,
)

占流通股本比例 = Column(
    COL_FLOAT_HOLDER_HOLD_FLOAT_RATIO,
    Float,
    nullable=True,
    comment="占流通股本比例",
)
持股变动 = Column(
    COL_FLOAT_HOLDER_HOLD_CHANGE,
    Float,
    nullable=True,
    comment="持股变动",
)
股东类型 = Column(
    COL_FLOAT_HOLDER_TYPE,
    String(50),
    nullable=True,
    comment="股东类型",
)
```

Do not change `save_top10_floatholders()` control flow; the existing `df.rename(...)` plus whitelist projection should absorb the new fields once the mapping exists.

- [ ] **Step 4: Re-run the storage-focused tests**

Run:

```bash
poetry run pytest test/storage/model/test_top10_floatholders.py test/storage/test_storage_db.py -k top10_floatholders -v
```

Expected: PASS for the model and storage tests covering `top10_floatholders`.

- [ ] **Step 5: Run the final focused verification and commit**

Run:

```bash
poetry run pytest \
  test/download/dl/test_downloader_tushare.py \
  test/storage/model/test_top10_floatholders.py \
  test/storage/test_storage_db.py \
  -k top10_floatholders -v

poetry run pre-commit run --files \
  common/const.py \
  download/dl/downloader_tushare.py \
  storage/storage_db.py \
  storage/model/top10_floatholders.py \
  test/download/dl/test_downloader_tushare.py \
  test/storage/model/test_top10_floatholders.py \
  test/storage/test_storage_db.py

git add \
  common/const.py \
  download/dl/downloader_tushare.py \
  storage/storage_db.py \
  storage/model/top10_floatholders.py \
  test/download/dl/test_downloader_tushare.py \
  test/storage/model/test_top10_floatholders.py \
  test/storage/test_storage_db.py
git commit -m "fix: store missing top10 floatholders fields" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

Expected: all targeted `top10_floatholders` tests pass, touched-file hooks pass, and the final commit captures the storage/schema slice.
