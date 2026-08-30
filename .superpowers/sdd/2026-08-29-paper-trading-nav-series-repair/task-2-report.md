# Task 2 Report: Ordered Event Adapter and Repository Reads

## Status

Task 2 provenance remediation is complete. This document is the sole
authoritative result for Task 2 verification.

## Scope

Modified only for Task 2 provenance:

- `paper_trading/domain/enums.py`
- `storage/model/paper_trading.py`
- `paper_trading/storage/enum_migration.py`
- `paper_trading/storage/repository.py`
- `storage/storage_db.py`
- `test/paper_trading/storage/test_repository.py`
- `test/paper_trading/storage/test_enum_migration.py`
- this report

No matching, settlement, or Task 3+ behavior was modified.

## Provenance Design

`ReplayTimeProvenance.CANONICAL_UTC` is persisted as nullable
`event_time_provenance` on all replay source tables:

- `paper_cash_ledger`
- `paper_trades`
- `paper_corporate_actions`
- `paper_account_snapshots`

Normal repository writes mark timestamps as `canonical_utc`. The replay adapter
only interprets a naive datetime as UTC when its persisted provenance is
`canonical_utc`; this covers SQLite's loss of timezone information on a
`DateTime(timezone=True)` round trip. Missing provenance, unknown provenance,
or missing timestamps are explicitly invalid rather than inferred as UTC.

The PostgreSQL migration creates the provenance enum and nullable columns
idempotently. SQLite's schema upgrade adds the equivalent nullable `VARCHAR(20)`
columns idempotently. Neither migration backfills legacy rows, so historical
records remain `NULL` provenance and are replayed as invalid until repaired by
an explicit future workflow.

## Preserved Task 2 Behavior

- Cash ledger external-flow classification and internal settlement handling
- Creation and latest bounded baseline selection
- Complete corporate-action payloads
- Stable UTC ordering and invalid unproven timestamps
- Cash-only account snapshot selection
- Mixed-dividend economic assertions
- Bounded replacement rollback with real second-write failure on SQLite and PostgreSQL

## Verification

### Scoped Ruff

Command:

```text
uv run ruff check paper_trading/domain/enums.py storage/model/paper_trading.py paper_trading/storage/enum_migration.py paper_trading/storage/repository.py storage/storage_db.py test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_enum_migration.py
```

Output:

```text
All checks passed!
```

Exit status: `0`.

### Focused Repository And Replay Tests

Command:

```text
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/domain/test_nav_replay.py -v
```

Output summary:

```text
collected 133 items
======================= 133 passed, 2 skipped in 41.12s ========================
```

The two skipped parameter cases require `TEST_POSTGRESQL_URL`; the PostgreSQL
runner below executes them.

Exit status: `0`.

### PostgreSQL Repository Tests

Command:

```text
tools/run_tests.sh test/paper_trading/storage/test_repository.py -v
```

Output summary:

```text
collected 121 items
test_replace_trading_snapshots_restores_all_old_rows_when_second_write_fails[sqlite_repository] PASSED
test_replace_trading_snapshots_restores_all_old_rows_when_second_write_fails[postgres_repository] PASSED
test_list_replay_events_preserves_decimal_payload_across_sqlite_and_postgresql PASSED
============================= 121 passed in 43.39s =============================
```

The parity test commits both databases, expires both ORM sessions, creates fresh
sessions, then compares each replay event's `event_at`, quality status, payload,
event type, source kind, and source ID for equality.

Exit status: `0`.

### Provenance Migration Test

Command:

```text
tools/run_tests.sh test/paper_trading/storage/test_enum_migration.py -k replay_time_provenance -v
```

Output summary:

```text
1 passed, 35 deselected in 3.71s
```

The PostgreSQL migration test proves the enum and four nullable columns are
added, existing legacy provenance remains `NULL`, and rerunning migration is
idempotent. A focused SQLite test covers the equivalent nullable-column upgrade
and no-backfill behavior.

Exit status: `0`.

### Whitespace

Command: `git diff --check`

Output: no findings. Exit status: `0`.

## Concerns

- Existing historical replay rows receive no guessed provenance. They remain
  invalid when their timestamp lacks timezone evidence; a separate explicit
  repair workflow is required to assert provenance.
- The runner emits existing `en_US.UTF-8` and Docker `No services to build`
  warnings. They did not affect test execution.

## Final Result

Canonical UTC timestamp provenance is now explicit and auditable across SQLite
and PostgreSQL. SQLite no longer gains `VALID` solely from its dialect; only
rows written with `canonical_utc` provenance do. All required verification
commands completed with the results above.
