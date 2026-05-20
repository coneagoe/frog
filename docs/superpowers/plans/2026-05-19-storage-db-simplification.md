# Storage DB Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the repeated save/query logic inside `storage/storage_db.py` without changing `StorageDb`'s public API or storage behavior.

**Architecture:** Keep `StorageDb` as the single entry point, but extract a small set of private helpers inside `storage_db.py` for DataFrame normalization, history-table routing, generic `to_sql` writes, and range-query SQL construction. Public `save_*` / `load_*` methods remain thin business-oriented wrappers so callers and tests keep seeing the same behavior.

**Tech Stack:** Python 3.11+, Poetry, pytest, pandas, SQLAlchemy, psycopg2, sqlite-backed storage tests

---

## File map

- `storage/storage_db.py` — add the private helpers and refactor repeated `save_*` and `load_*` call sites to use them.
- `test/storage/test_storage_db.py` — add focused regression tests for DataFrame normalization, history-table routing, and range-query SQL/params while keeping nearby existing storage tests as behavior locks.
- `docs/superpowers/specs/2026-05-19-storage-db-simplification-design.md` — reference only; do not modify during implementation unless the user explicitly re-opens the design.

### Task 1: Lock the write-path normalization behavior with focused regression tests

**Files:**
- Modify: `test/storage/test_storage_db.py`
- Modify: `storage/storage_db.py`

- [ ] **Step 1: Write the failing tests for normalized save behavior**

Append these tests to `test/storage/test_storage_db.py` inside `TestStorageDb`:

```python
    def test_save_history_data_fund_normalizes_code_and_trade_date(self, storage_db):
        raw_df = pd.DataFrame(
            {
                "ts_code": ["510300.SH"],
                "trade_date": ["20240315"],
                "open": [3.12],
                "high": [3.20],
                "low": [3.08],
                "close": [3.18],
                "pre_close": [3.10],
                "change": [0.08],
                "pct_chg": [2.58],
                "vol": [123456],
                "amount": [9876543],
            }
        )
        captured: dict[str, object] = {}

        def fake_to_sql(self, table_name, engine, **kwargs):
            captured["df"] = self.copy()
            captured["table_name"] = table_name
            captured["engine"] = engine
            captured["kwargs"] = kwargs

        with patch("pandas.DataFrame.to_sql", new=fake_to_sql):
            assert storage_db.save_history_data_fund(raw_df) is True

        written_df = captured["df"]
        assert captured["table_name"] == "history_data_daily_fund"
        assert captured["engine"] == storage_db.engine
        assert captured["kwargs"] == {
            "if_exists": "append",
            "index": False,
            "method": "multi",
        }
        assert written_df[COL_ETF_ID].tolist() == ["510300"]
        assert written_df[COL_DATE].tolist() == ["2024-03-15"]

    def test_save_stk_holdernumber_normalizes_multiple_date_columns(self, storage_db):
        raw_df = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "ann_date": ["20240315"],
                "end_date": ["20231231"],
                "holder_num": [12345],
            }
        )
        captured: dict[str, object] = {}

        def fake_to_sql(self, table_name, engine, **kwargs):
            captured["df"] = self.copy()
            captured["table_name"] = table_name
            captured["kwargs"] = kwargs

        with patch("pandas.DataFrame.to_sql", new=fake_to_sql):
            assert storage_db.save_stk_holdernumber(raw_df) is True

        written_df = captured["df"]
        assert captured["table_name"] == tb_name_stk_holdernumber
        assert captured["kwargs"] == {
            "if_exists": "append",
            "index": False,
            "method": "multi",
        }
        assert written_df[COL_STOCK_ID].tolist() == ["000001"]
        assert written_df[COL_ANN_DATE].tolist() == ["2024-03-15"]
        assert written_df[COL_END_DATE].tolist() == ["2023-12-31"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
poetry run pytest test/storage/test_storage_db.py -k "history_data_fund_normalizes_code_and_trade_date or stk_holdernumber_normalizes_multiple_date_columns" -v
```

Expected: FAIL because the current implementation normalizes each save method inline, but there is no shared helper yet and the new tests are not present on the branch.

- [ ] **Step 3: Implement the minimal shared save helpers**

In `storage/storage_db.py`, add these private helpers above the first `save_*` method:

```python
    def _require_engine(self):
        if self.engine is None:
            raise ConnectionError("SQLAlchemy引擎未初始化")
        return self.engine

    def _normalize_code_column(self, df: pd.DataFrame, code_column: Optional[str]) -> pd.DataFrame:
        if code_column and code_column in df.columns:
            df[code_column] = df[code_column].astype(str).str.split(".").str[0]
        return df

    def _normalize_date_columns(
        self,
        df: pd.DataFrame,
        date_columns: dict[str, str],
    ) -> pd.DataFrame:
        for column, output in date_columns.items():
            converted = pd.to_datetime(df[column], format="%Y%m%d", errors="coerce")
            if output == "date":
                df[column] = converted.dt.date
            else:
                df[column] = converted.dt.strftime("%Y-%m-%d")
        return df

    def _prepare_dataframe_for_save(
        self,
        df: pd.DataFrame,
        *,
        column_map: dict[str, str],
        code_column: Optional[str] = None,
        date_columns: Optional[dict[str, str]] = None,
        optional_columns: Optional[list[str]] = None,
        output_columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        prepared = df.rename(columns=column_map).copy()
        for column in optional_columns or []:
            if column not in prepared.columns:
                prepared[column] = pd.NA
        prepared = self._normalize_code_column(prepared, code_column)
        ordered_columns = output_columns or list(column_map.values())
        prepared = prepared[ordered_columns]
        if date_columns:
            prepared = self._normalize_date_columns(prepared, date_columns)
        return prepared

    def _write_dataframe(
        self,
        df: pd.DataFrame,
        table_name: str,
        *,
        if_exists: str,
        method: Optional[str] = None,
    ) -> None:
        engine = self._require_engine()
        kwargs: dict[str, object] = {"if_exists": if_exists, "index": False}
        if method is not None:
            kwargs["method"] = method
        df.to_sql(table_name, engine, **kwargs)
```

Then refactor `save_history_data_fund()` and `save_stk_holdernumber()` to call `_prepare_dataframe_for_save()` and `_write_dataframe()` instead of duplicating the whole transformation chain.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
poetry run pytest test/storage/test_storage_db.py -k "history_data_fund_normalizes_code_and_trade_date or stk_holdernumber_normalizes_multiple_date_columns" -v
```

Expected: PASS with both tests green.

- [ ] **Step 5: Commit the save-helper extraction**

Run:

```bash
git add test/storage/test_storage_db.py storage/storage_db.py
git commit -m "refactor: share storage dataframe save helpers"
```

### Task 2: Unify history table routing and shared date-range query building

**Files:**
- Modify: `test/storage/test_storage_db.py`
- Modify: `storage/storage_db.py`

- [ ] **Step 1: Write the failing tests for shared table routing and range-query params**

Add these tests to `test/storage/test_storage_db.py` inside `TestStorageDb`:

```python
    def test_load_history_data_fund_builds_expected_sql_and_params(self, storage_db):
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = pd.DataFrame()

            storage_db.load_history_data_fund(
                "510300",
                start_date="2024-01-01",
                end_date="2024-03-31",
            )

        sql = mock_read_sql.call_args.args[0]
        assert f'FROM {tb_name_history_data_daily_fund}' in sql
        assert f'"{COL_ETF_ID}" = %s' in sql
        assert f'"{COL_DATE}" >= %s' in sql
        assert f'"{COL_DATE}" <= %s' in sql
        assert 'ORDER BY "date" ASC' in sql
        assert mock_read_sql.call_args.kwargs["params"] == (
            "510300",
            "2024-01-01",
            "2024-03-31",
        )

    def test_load_etf_daily_builds_expected_sql_and_params(self, storage_db):
        with patch("storage.storage_db.pd.read_sql") as mock_read_sql:
            mock_read_sql.return_value = pd.DataFrame()

            storage_db.load_etf_daily(
                "510300",
                start_date="2024-01-01",
                end_date="2024-03-31",
            )

        sql = mock_read_sql.call_args.args[0]
        assert f"FROM {tb_name_etf_daily}" in sql
        assert f'"{COL_ETF_ID}" = %s' in sql
        assert f'"{COL_DATE}" >= %s' in sql
        assert f'"{COL_DATE}" <= %s' in sql
        assert f'ORDER BY "{COL_DATE}"' in sql
        assert mock_read_sql.call_args.kwargs["params"] == (
            "510300",
            "2024-01-01",
            "2024-03-31",
        )
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
poetry run pytest test/storage/test_storage_db.py -k "load_history_data_fund_builds_expected_sql_and_params or load_etf_daily_builds_expected_sql_and_params" -v
```

Expected: FAIL because the new tests are not yet present and the current query construction is still duplicated.

- [ ] **Step 3: Refactor to shared history-table and range-query helpers**

Add these helpers to `storage/storage_db.py`:

```python
    def _get_history_table_name(
        self,
        security_type: SecurityType,
        period: PeriodType,
        adjust: AdjustType,
    ) -> str:
        return get_table_name(security_type, period, adjust)

    def _build_code_date_range_query(
        self,
        *,
        table_name: str,
        code_column: str,
        code_value: str,
        date_column: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        order: str = "ASC",
    ) -> tuple[str, tuple[Any, ...]]:
        sql = [
            f"SELECT * FROM {table_name}",
            f'WHERE "{code_column}" = %s',
        ]
        params: list[Any] = [code_value]
        if start_date:
            sql.append(f'AND "{date_column}" >= %s')
            params.append(start_date)
        if end_date:
            sql.append(f'AND "{date_column}" <= %s')
            params.append(end_date)
        sql.append(f'ORDER BY "{date_column}" {order}')
        return "\n".join(sql), tuple(params)
```

Then refactor these call sites to use them:

```python
    def save_history_data_stock(
        self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType
    ) -> bool:
        table_name = self._get_history_table_name(SecurityType.STOCK, period, adjust)
        self._write_dataframe(df, table_name, if_exists="append", method="multi")
        return True

    def save_history_data_etf(
        self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType
    ) -> bool:
        try:
            table_name = self._get_history_table_name(SecurityType.ETF, period, adjust)
            self._write_dataframe(df, table_name, if_exists="append", method="multi")
            logger.info(f"ETF历史数据保存成功: {table_name}, 数据条数: {len(df)}")
            return True
        except Exception as e:
            logger.error(f"保存ETF历史数据失败: {str(e)}")
            return False

    def save_history_data_hk_stock(
        self, df: pd.DataFrame, period: PeriodType, adjust: AdjustType
    ) -> bool:
        try:
            table_name = self._get_history_table_name(
                SecurityType.HK_GGT_STOCK, period, adjust
            )
            self._write_dataframe(df, table_name, if_exists="append", method="multi")
            logger.info(f"港股历史数据保存成功: {table_name}, 数据条数: {len(df)}")
            return True
        except Exception as e:
            logger.error(f"保存港股历史数据失败: {str(e)}")
            return False

    def load_history_data_fund(
        self,
        fund_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        sql, sql_params = self._build_code_date_range_query(
            table_name=tb_name_history_data_daily_fund,
            code_column=COL_ETF_ID,
            code_value=fund_id,
            date_column=COL_DATE,
            start_date=start_date,
            end_date=end_date,
            order="ASC",
        )
        df = pd.read_sql(sql, self.engine, params=sql_params)
        logger.info(f"基金日线行情数据加载成功: {fund_id}, 数据条数: {len(df)}")
        return df

    def load_etf_daily(
        self,
        etf_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        sql, sql_params = self._build_code_date_range_query(
            table_name=tb_name_etf_daily,
            code_column=COL_ETF_ID,
            code_value=etf_id,
            date_column=COL_DATE,
            start_date=start_date,
            end_date=end_date,
            order="ASC",
        )
        df = pd.read_sql(sql, self.engine, params=sql_params)
        logger.info(f"ETF日线数据加载成功，数据条数: {len(df)}")
        return df
```

Keep the existing `try/except` blocks and current log/error-return behavior around these refactors.

- [ ] **Step 4: Run the focused table-routing and range-query tests**

Run:

```bash
poetry run pytest test/storage/test_storage_db.py -k "load_history_data_fund_builds_expected_sql_and_params or load_etf_daily_builds_expected_sql_and_params or save_history_data_stock_1d_success or save_history_data_stock_1w_success" -v
```

Expected: PASS with the existing stock-history tests and the two new query tests green together.

- [ ] **Step 5: Commit the routing/query refactor**

Run:

```bash
git add test/storage/test_storage_db.py storage/storage_db.py
git commit -m "refactor: share storage routing and range queries"
```

### Final verification and commit

**Files:**
- Modify: `test/storage/test_storage_db.py`
- Modify: `storage/storage_db.py`

- [ ] **Step 1: Run the full storage-db focused test file**

Run:

```bash
poetry run pytest test/storage/test_storage_db.py -v
```

Expected: PASS for the full `storage_db` test file, including the new save/query regression tests and the existing storage behavior locks.

- [ ] **Step 2: Run touched-file quality checks**

Run:

```bash
poetry run pre-commit run --files storage/storage_db.py test/storage/test_storage_db.py
```

Expected: PASS for formatting, lint, and any configured checks against the touched files.

- [ ] **Step 3: Commit the scoped simplification**

Run:

```bash
git add test/storage/test_storage_db.py storage/storage_db.py docs/superpowers/plans/2026-05-19-storage-db-simplification.md
git commit -m "refactor: simplify storage db save and query helpers"
```

Expected: A single commit containing the save/query helper extraction, regression tests, and the updated implementation plan.
