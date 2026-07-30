# A-Stock Basic Field Length Design

## Goal

Allow A-share basic-information refreshes to persist complete controller names that
exceed the current 40-character limit, while providing actionable diagnostics for
any remaining field-length violations.

## Scope

- Change `a_stock_basic.实控人姓名` from `varchar(40)` to `varchar(100)` in the
  SQLAlchemy model.
- Upgrade existing databases idempotently during storage initialization using the
  repository's inspected `ALTER TABLE` convention.
- Validate all bounded string fields before `DataFrame.to_sql` writes the batch.
- Make the selected A-share-basic DataFrame an explicit copy before date conversion.
- Add focused storage tests for the schema upgrade, valid writes, and an over-limit
  value diagnostic.

## Data Flow

`DownloadManager.download_a_stock_basic` obtains TuShare `stock_basic` data and
passes it to `StorageDb.save_a_stock_basic`. The storage method maps provider fields,
normalizes stock codes and dates, validates configured string limits, and appends the
prepared frame to `a_stock_basic`.

The effective limits remain aligned with the database model. `实控人姓名` permits up
to 100 characters. Other bounded columns retain their existing limits.

## Schema Upgrade

Storage initialization will inspect `a_stock_basic` when it exists. If
`实控人姓名` has a length below 100, it will run an idempotent:

```sql
ALTER TABLE a_stock_basic ALTER COLUMN "实控人姓名" TYPE VARCHAR(100)
```

Fresh databases receive the same limit from the model definition. The upgrade only
widens the column and does not alter rows or other table definitions.

## Validation And Errors

Before writing, the prepared DataFrame is copied and each non-null string value is
checked against its target column limit. A violating batch is rejected before SQL is
issued. Its log records the stock code, target column, actual length, and configured
limit, so an upstream data change is directly identifiable.

No values are truncated. This preserves source data and prevents a successful refresh
from silently corrupting a field.

## Verification

Focused tests will verify:

- A legacy `varchar(40)` controller-name column upgrades to `varchar(100)`.
- A normal A-share-basic frame maps, normalizes, and writes through `to_sql`.
- An over-limit bounded value returns failure without calling `to_sql` and emits a
  diagnostic containing the stock code, column, actual length, and limit.

The focused suite is `uv run pytest test/storage/test_storage_db.py`.
