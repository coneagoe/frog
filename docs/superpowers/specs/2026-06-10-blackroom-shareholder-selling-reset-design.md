# Blackroom Shareholder Selling Reset Design

## Goal

Modify shareholder-selling blackroom punishment so bans start from the shareholder-selling announcement date and repeated selling resets an existing active blackroom ban.

## Requirements

- A shareholder-selling announcement bans the stock for 180 days by default; the existing CLI `--ban-days` argument may override this duration for a sync run.
- The ban starts at the announcement date (`ann_date`), not at sync execution time.
- If the stock is not currently in the blackroom, create one active blackroom record.
- If the stock is already in the blackroom and another shareholder-selling announcement is synced, update the existing active record instead of skipping or creating a duplicate.
- Reset means updating the existing active record with:
  - `start_at`: announcement date at UTC midnight
  - `ban_days`: the effective sync duration, defaulting to `180`
  - `remaining_days`: same as `ban_days`
  - `note`: latest shareholder-selling announcement note
- Keep the existing CLI entrypoint: `poetry run python tools/stock_monitor_cli.py blackroom sync-shareholder-selling ...`.

## Scope

In scope:

- `monitor/shareholder_selling_punishment.py`
- Unit tests for shareholder-selling punishment behavior
- Minimal service/storage helper changes if needed to locate the active blackroom record id

Out of scope:

- Changing DAG schedules, task boundaries, retries, or SLA
- Adding separate historical blackroom records for every announcement
- Changing manual blackroom ban behavior
- Changing countdown behavior

## Current Behavior

`ShareholderSellingPunishmentService.sync()` fetches Tushare `stk_holdertrade` rows with `in_de="DE"`, deduplicates them by stock, checks whether each stock is banned, and currently skips already-banned stocks.

New bans call `BlackroomService.ban(...)`, which creates records with `ban_days`, `remaining_days`, `start_at`, and storage-calculated `expire_at`.

## Proposed Behavior

For each deduplicated stock row:

1. Parse `ann_date` as `YYYYMMDD` and convert it to timezone-aware UTC midnight.
2. Check whether the stock has an active blackroom record.
3. If no active record exists:
   - Create a new shareholder-selling blackroom record with `start_at=announcement_start`, `ban_days=ban_days`, and the announcement note.
4. If an active record exists:
   - Update that record with `start_at=announcement_start`, `ban_days=ban_days`, `remaining_days=ban_days`, `source="shareholder_selling"`, and the announcement note.
   - Storage will recompute `expire_at` from `start_at + ban_days`.

## Data Flow

```text
Tushare stk_holdertrade rows
  -> normalize ts_code to stock_code/market
  -> dedupe by stock_code/market
  -> parse ann_date
  -> active blackroom lookup
  -> create new record OR reset existing active record
  -> return sync counts and touched records
```

## Result Shape

Keep existing success envelope:

```python
{
    "success": True,
    "code": "OK",
    "message": "sync completed",
    "data": {...},
}
```

Update `data` to distinguish outcomes:

- `fetched`: raw provider row count
- `unique_stocks`: deduplicated stock count
- `added`: newly-created blackroom records
- `reset`: existing active records reset
- `skipped`: no longer used for active bans; remains `0` for backward-compatible presence if retained
- `records`: touched stock records, including an `action` field of `"added"` or `"reset"`

## Error Handling

- Invalid sync date range still returns `VALIDATION_ERROR`.
- Invalid `ban_days` still returns `VALIDATION_ERROR`.
- Invalid row `ann_date` returns failure rather than silently using sync time.
- Blackroom lookup, create, or update failures propagate using existing `_propagate_failure(...)` behavior.

## Testing

Add or update tests in `test/monitor/test_shareholder_selling_punishment.py`:

- New stock creates a ban with `start_at` equal to announcement date UTC midnight.
- Existing active stock resets the existing record instead of being skipped.
- Reset passes `ban_days`, `remaining_days`, `start_at`, `source`, and latest note to `BlackroomService.update_record(...)`.
- Result counts include `added` and `reset` correctly.
- Invalid `ann_date` fails predictably.

Run focused verification with:

```bash
poetry run pytest test/monitor/test_shareholder_selling_punishment.py
```
