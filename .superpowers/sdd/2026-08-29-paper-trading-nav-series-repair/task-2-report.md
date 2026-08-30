# Task 2 Report: Ordered Event Adapter and Repository Reads

## Status

Implemented Task 2 in the existing worktree changes. The cash-flow adapter does not pass persisted `net_asset_value` as `nav`; this preserves the Task 1 replay contract and prevents cash-flow replay from bypassing replay-derived NAV rules.

## Modified files

- `paper_trading/storage/repository.py`
  - Added UTC-normalized replay event adaptation for cash ledger, trades, corporate actions, and account snapshots.
  - Added stable event ordering by UTC event time, event precedence, source kind, and string `source_id`.
  - Added account-scoped inclusive replay time-range filtering and timezone/range validation.
  - Added explicit invalid quality for legacy records with missing event time, using trade/affected date at UTC midnight rather than current time.
  - Added bounded inclusive replacement of derived trading snapshots only.
  - Added active account selection through the valuation interval while retaining positive-position and order selection.
  - Added `get_replay_events()` compatibility alias for `list_replay_events()`.
- `test/paper_trading/storage/test_repository.py`
  - Added coverage for adapter ordering/UTC normalization and the cash-flow `nav` exclusion.
  - Added legacy missing-time quality coverage.
  - Added bounded trading snapshot replacement coverage.
  - Added active cash-only account selection coverage.

No `nav_series_repository.py` was needed. Matching and settlement code was not modified.

## Interfaces

- `PaperTradingRepository.list_replay_events(account_id, start_at=None, end_at=None) -> list[ReplayEvent]`
- `PaperTradingRepository.get_replay_events(account_id, start_at=None, end_at=None) -> list[ReplayEvent]`
- `PaperTradingRepository.replace_trading_snapshots(account_id, start_date, end_date, snapshots) -> list[PaperAccountSnapshot]`

Replay source IDs are strings in the form `<source_table>:<row_id>`.

## Tests

### Command

```text
uv run pytest test/paper_trading/storage/test_repository.py -v
```

### Output

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/issue-82-nav-series/.venv/bin/python
collecting ... collected 103 items
...
============================= 103 passed in 35.19s =============================
```

### Command

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py -v
```

### Output

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/issue-82-nav-series/.venv/bin/python
collecting ... collected 14 items
...
============================== 14 passed in 0.05s ==============================
```

The brief mentions new adapter tests, but no matching adapter test file exists in `test/paper_trading/storage/`; the adapter coverage was added to `test_repository.py` instead.

`git diff --check` passed.

## Concerns

- PostgreSQL-specific execution was not run; the requested focused repository tests use the configured SQLite fixture. Decimal conversion is covered by the existing SQLite repository tests, but PostgreSQL parity remains for the orchestrator to validate.
- The existing working-tree changes already included the implementation and tests; this handoff corrected the cash-flow payload to omit `nav` and added an assertion for that Task 1 contract.
- Simplify review skill was requested by repository guidance, but no native skill tool is available in this execution environment; no additional simplification was applied.
