# A-Stock Basic Field Length Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist complete A-share controller names up to 100 characters and reject any other bounded string overflow with a precise diagnostic before database insertion.

**Architecture:** Keep A-share-basic persistence in `StorageDb`. The model defines fresh-install limits, `StorageDb` performs an idempotent upgrade for existing `a_stock_basic` tables during metadata initialization, and `save_a_stock_basic` reuses the shared DataFrame preparation/write helpers before validating bounded strings. No downloaded data is truncated.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy, PostgreSQL/TimescaleDB, pytest, unittest.mock.

## Global Constraints

- Use `uv run` for Python commands.
- Preserve existing `a_stock_basic` rows and schema except widening `实控人姓名` from `VARCHAR(40)` to `VARCHAR(100)`.
- Do not truncate provider data.
- Preserve `save_a_stock_basic(df) -> bool` and its `False`-on-save-failure contract.
- Do not change the weekly DAG, task boundary, retry policy, or download-manager flow.
- Do not commit unless the user explicitly requests a commit.

---

## File Structure

- Modify `storage/model/a_stock_basic.py`: define the fresh-schema 100-character controller-name limit.
- Modify `storage/storage_db.py`: run the legacy-schema widening check at initialization; prepare an independent DataFrame copy; validate bounded strings; then write via the shared helper.
- Modify `test/storage/test_storage_db.py`: add a legacy SQLite schema fixture and focused model/migration/persistence regression tests.

### Task 1: Model And Legacy Schema Upgrade

**Files:**
- Modify: `storage/model/a_stock_basic.py:55`
- Modify: `storage/storage_db.py:405-411`
- Modify: `storage/storage_db.py:2272-2290`
- Test: `test/storage/test_storage_db.py:71-83`
- Test: `test/storage/test_storage_db.py:325-362`

**Interfaces:**
- Consumes: `tb_name_a_stock_basic` and `COL_ACT_NAME` from `storage.model.a_stock_basic` / `common.const`.
- Produces: `StorageDb.ensure_a_stock_basic_schema() -> None`, called exactly once per process after `Base.metadata.create_all(self.engine)`.

- [ ] **Step 1: Add a failing legacy-schema regression test**

Unit-test the PostgreSQL migration decision without running PostgreSQL-only `ALTER COLUMN ... TYPE` against SQLite. Mock `inspect(self.engine)` to report an existing `a_stock_basic` table whose `实控人姓名` type has `length == 40`; mock `self.engine.begin()` and capture `conn.execute`. Call `ensure_a_stock_basic_schema()` and assert it executes the widening DDL once. Reconfigure the inspection result to length 100, call again, and assert it executes no DDL.

```python
def test_ensure_a_stock_basic_schema_widens_controller_name(storage, monkeypatch):
    inspector = Mock()
    inspector.has_table.return_value = True
    inspector.get_columns.return_value = [{"name": COL_ACT_NAME, "type": String(40)}]
    monkeypatch.setattr("storage.storage_db.inspect", Mock(return_value=inspector))

    storage.ensure_a_stock_basic_schema()

    executed_sql = str(storage.engine.begin.return_value.__enter__.return_value.execute.call_args.args[0])
    assert 'ALTER COLUMN "实控人姓名" TYPE VARCHAR(100)' in executed_sql

    inspector.get_columns.return_value = [{"name": COL_ACT_NAME, "type": String(100)}]
    storage.ensure_a_stock_basic_schema()
```

- [ ] **Step 2: Run the new test and verify it fails**

Run: `uv run pytest test/storage/test_storage_db.py -k ensure_a_stock_basic_schema -v`

Expected: FAIL because `StorageDb.ensure_a_stock_basic_schema` does not exist.

- [ ] **Step 3: Define the fresh-schema width and idempotent upgrade**

Change the model declaration to:

```python
实控人姓名 = Column(COL_ACT_NAME, String(100), nullable=True, comment="实控人姓名")
```

Implement the following method near other schema-initialization methods, guarding for a fresh database whose table does not yet exist:

```python
def ensure_a_stock_basic_schema(self) -> None:
    assert self.engine is not None
    if not inspect(self.engine).has_table(tb_name_a_stock_basic):
        return

    columns = {
        column["name"]: column for column in inspect(self.engine).get_columns(tb_name_a_stock_basic)
    }
    controller_name = columns[COL_ACT_NAME]
    if getattr(controller_name["type"], "length", None) is not None and controller_name["type"].length < 100:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f'ALTER TABLE {tb_name_a_stock_basic} '
                    f'ALTER COLUMN "{COL_ACT_NAME}" TYPE VARCHAR(100)'
                )
            )
```

Call `self.ensure_a_stock_basic_schema()` immediately after `Base.metadata.create_all(self.engine)` in `StorageDb.__init__`. For SQLite test compatibility, use SQLAlchemy column-type alteration only if the test engine supports it, or set up the regression test with an engine/dialect that supports the repository’s production PostgreSQL statement. Keep production behavior limited to PostgreSQL/TimescaleDB.

- [ ] **Step 4: Run the schema-upgrade test**

Run: `uv run pytest test/storage/test_storage_db.py -k ensure_a_stock_basic_schema -v`

Expected: PASS, including the no-op second invocation when the reported length is already 100.

### Task 2: Pre-Write Length Validation And Persistence Coverage

**Files:**
- Modify: `storage/storage_db.py:1471-1501`
- Test: `test/storage/test_storage_db.py:981-1063`

**Interfaces:**
- Consumes: `StorageDb._prepare_dataframe_for_save`, `StorageDb._write_dataframe`, `COL_MAP_STOCK_BASIC`, and the `a_stock_basic` field limits.
- Produces: `StorageDb.save_a_stock_basic(df: pd.DataFrame) -> bool`; returns `False` before `to_sql` for a bounded-string violation and logs the stock code, column, actual length, and allowed length.

- [ ] **Step 1: Add failing write and overflow tests**

Create a one-row provider-format DataFrame containing every field in `COL_MAP_STOCK_BASIC`. Patch `DataFrame.to_sql`, call `save_a_stock_basic`, and assert the call targets `tb_name_a_stock_basic` with `if_exists="append"`, `index=False`, and `method="multi"`. Assert the write frame has stock code `000001` and `date` objects for `上市日期` and `退市日期`.

Create a second frame where `act_name` exceeds 100 characters. Patch `DataFrame.to_sql` and `storage.storage_db.logger`, then assert the method returns `False`, no SQL write occurs, and the error includes `000001`, `实控人姓名`, `101`, and `100`.

```python
assert storage_db.save_a_stock_basic(overflow_df) is False
mock_to_sql.assert_not_called()
error = mock_logger.error.call_args.args[0]
assert "000001" in error
assert COL_ACT_NAME in error
assert "101" in error
assert "100" in error
```

- [ ] **Step 2: Run the new persistence tests and verify they fail**

Run: `uv run pytest test/storage/test_storage_db.py -k a_stock_basic -v`

Expected: FAIL because no A-share-basic test helpers or pre-write validator exist.

- [ ] **Step 3: Reuse shared preparation and add a bounded-string validator**

Replace in-place operations in `save_a_stock_basic` with the repository helper so the selected columns are an independent copy:

```python
prepared = self._prepare_dataframe_for_save(
    df,
    column_map=COL_MAP_STOCK_BASIC,
    code_column=COL_STOCK_ID,
    date_columns={COL_IPO_DATE: "date", COL_DELISTING_DATE: "date"},
)
```

Add a private validator that checks each non-null `str` value against the explicit limits used by the `a_stock_basic` model. At minimum include every bounded string column: `股票代码: 6`, `股票名称: 40`, `地域: 20`, `所属行业: 40`, `股票全称: 100`, `英文全称: 100`, `拼音缩写: 20`, `市场类型: 20`, `交易所: 10`, `交易货币: 10`, `上市状态: 2`, `是否沪深港通: 2`, `实控人姓名: 100`, and `实控人企业性质: 20`.

For the first violation, log and return `False` before `_write_dataframe`:

```python
logger.error(
    "A股基础信息字段超长: 股票代码=%s, 字段=%s, 长度=%s, 上限=%s",
    stock_id,
    column,
    len(value),
    limit,
)
```

After validation, preserve the append/multi semantics through:

```python
self._write_dataframe(prepared, tb_name_a_stock_basic, if_exists="append", method="multi")
```

- [ ] **Step 4: Run focused persistence tests**

Run: `uv run pytest test/storage/test_storage_db.py -k a_stock_basic -v`

Expected: PASS. The valid case writes normalized data, and the overflow case skips `to_sql` with the diagnostic fields.

### Task 3: Regression Verification

**Files:**
- Modify: none
- Test: `test/storage/test_storage_db.py`

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: evidence that storage tests pass without pandas `SettingWithCopyWarning` from the A-share-basic path.

- [ ] **Step 1: Run the focused storage module**

Run: `uv run pytest test/storage/test_storage_db.py`

Expected: PASS.

- [ ] **Step 2: Verify the live PostgreSQL schema after the storage initialization path runs**

Run the project’s A-share storage initialization in the local service environment, then query the table definition:

```bash
docker compose exec -T db psql -U quant -d quant -P pager=off -c \
  "SELECT character_maximum_length FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'a_stock_basic' AND column_name = '实控人姓名';"
```

Expected: the query reports `100`. This is the production-dialect confirmation that complements the unit-level DDL decision test.

- [ ] **Step 3: Run formatting and static checks for edited modules**

Run: `uv run ruff format --check storage/model/a_stock_basic.py storage/storage_db.py test/storage/test_storage_db.py && uv run ruff check storage/model/a_stock_basic.py storage/storage_db.py test/storage/test_storage_db.py`

Expected: both commands exit 0.

- [ ] **Step 4: Inspect the resulting diff**

Run: `git diff -- storage/model/a_stock_basic.py storage/storage_db.py test/storage/test_storage_db.py docs/superpowers/specs/2026-07-28-a-stock-basic-field-length-design.md docs/superpowers/plans/2026-07-28-a-stock-basic-field-length.md`

Expected: only the approved A-share-basic schema widening, pre-write validation, tests, and supporting design/plan documents are present.

- [ ] **Step 5: Leave changes uncommitted**

Do not run `git add` or `git commit`; the user has not requested a commit.
