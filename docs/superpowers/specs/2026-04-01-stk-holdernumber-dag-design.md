# Design: Weekly A-Stock Shareholder Count (stk_holdernumber) DAG

**Date:** 2026-04-01

## Problem Statement

We need to download shareholder count (股东人数) data for all A-stocks weekly using the existing TuShare `stk_holdernumber` API. Data includes both the announcement date (公告日期) and the reporting-period end date (截止日期). Downloads must be incremental per-stock and the DAG must run in parallel partitions.

## Data Source

TuShare `stk_holdernumber` fields:
| TuShare field | 含义 | DB column |
|---|---|---|
| `ts_code` | 股票代码（含交易所后缀） | `股票代码` |
| `ann_date` | 公告日期（YYYYMMDD） | `公告日期` |
| `end_date` | 截止日期/报告期（YYYYMMDD） | `截止日期` |
| `holder_num` | 股东人数（户） | `股东人数` |

## Architecture

### Files Changed

| File | Type | Change |
|---|---|---|
| `common/const.py` | modify | Add `COL_ANN_DATE`, `COL_END_DATE`, `COL_HOLDER_NUM` |
| `storage/model/stk_holdernumber.py` | **new** | SQLAlchemy model |
| `storage/model/__init__.py` | modify | Export new model + table name |
| `storage/__init__.py` | modify | Export `tb_name_stk_holdernumber` |
| `storage/storage_db.py` | modify | Add column map + `save_stk_holdernumber()` + `get_last_stk_holdernumber_ann_date()` |
| `download/download_manager.py` | modify | Add `download_stk_holdernumber_a_stock(stock_id, ...)` |
| `dags/download_stk_holdernumber_weekly.py` | **new** | DAG with 4 partitions |

### Storage Model

Table name: `stk_holdernumber`

Primary key: `(股票代码, 公告日期)` — each stock can only announce once per date.

```python
class StkHoldernumber(Base):
    __tablename__ = "stk_holdernumber"

    股票代码 = Column(COL_STOCK_ID, String(6), primary_key=True, nullable=False)
    公告日期 = Column(COL_ANN_DATE, Date, primary_key=True, nullable=False)
    截止日期 = Column(COL_END_DATE, Date, nullable=True)
    股东人数 = Column(COL_HOLDER_NUM, Integer, nullable=True)
```

### Date Conversion

`save_stk_holdernumber()` converts both dates from TuShare's `YYYYMMDD` to `YYYY-MM-DD`:

```python
for col in [COL_ANN_DATE, COL_END_DATE]:
    df[col] = pd.to_datetime(df[col], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
```

### ts_code Construction

Stock IDs are stored without exchange suffix. When calling TuShare, the suffix is inferred by prefix:
- `6xxxxx` → `.SH` (上交所)
- `0xxxxx` / `3xxxxx` → `.SZ` (深交所)
- `8xxxxx` / `4xxxxx` → `.BJ` (北交所)

### Incremental Logic (Per-stock)

```
get_last_stk_holdernumber_ann_date(stock_id) → last_date
if last_date:
    start_date = last_date + 1 day
else:
    start_date = "2020-01-01"
end_date = today
```

`get_last_stk_holdernumber_ann_date(stock_id)` queries:
```sql
SELECT 公告日期 FROM stk_holdernumber
WHERE 股票代码 = %s ORDER BY 公告日期 DESC LIMIT 1
```

### DAG Design

- **File:** `dags/download_stk_holdernumber_weekly.py`
- **Schedule:** `0 21 * * 0` (Sunday 21:00 CST)
- **Max partitions:** 4 (configurable via `get_partition_count()`, capped at 4)
- **Stock source:** `get_storage().load_general_info_stock()`
- **Pattern:** Same as `download_stock_history_qfq_weekend.py` — no reset task, 4 partition tasks in parallel

Each partition task:
1. Calls `get_partitioned_ids(stock_ids, partition_id, partition_count)`
2. Iterates stocks in its partition
3. Calls `manager.download_stk_holdernumber_a_stock(stock_id)`
4. Accumulates failed IDs and raises on any failure

## Error Handling

- Per-stock download failures: accumulated in `failed_ids`, raise at end of partition
- Empty DataFrame: logged and skipped (not a failure)
- TuShare API errors: retried up to 3 times with exponential backoff (handled by existing downloader decorator)

## Testing

- Unit test `save_stk_holdernumber()` with mock DataFrame containing YYYYMMDD strings → verify YYYY-MM-DD stored
- Unit test `get_last_stk_holdernumber_ann_date()` with and without existing records
- Unit test `download_stk_holdernumber_a_stock()` with mocked downloader + storage
- DAG structure test: verify 4 partition tasks created, correct schedule
