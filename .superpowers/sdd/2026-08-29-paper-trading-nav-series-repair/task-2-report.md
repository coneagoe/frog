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
requires exactly `canonical_utc` for `quality_status=VALID`; NULL or `unknown`
provenance is always `INVALID`, even when the timestamp is timezone-aware. A
canonical SQLite naive datetime is interpreted as UTC to cover SQLite's loss of
timezone information on a `DateTime(timezone=True)` round trip. Non-canonical
timestamps retain a UTC-normalized ordering placeholder only. Missing event
time is also explicitly invalid.

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
collected 139 items
======================= 135 passed, 4 skipped in 38.68s ========================
```

The four skipped parameter cases are the PostgreSQL/SQLite fixture combinations
that require `TEST_POSTGRESQL_URL`; the PostgreSQL runner below executes all
four combinations.

Exit status: `0`.

### PostgreSQL Repository Tests

Command:

```text
tools/run_tests.sh test/paper_trading/storage/test_repository.py -v
```

Output summary:

```text
collected 125 items
test_replace_trading_snapshots_restores_all_old_rows_when_second_write_fails[sqlite_repository] PASSED
test_replace_trading_snapshots_restores_all_old_rows_when_second_write_fails[postgres_repository] PASSED
test_list_replay_events_preserves_decimal_payload_across_sqlite_and_postgresql PASSED
test_unproven_persisted_aware_replay_event_is_invalid[None-sqlite_repository] PASSED
test_unproven_persisted_aware_replay_event_is_invalid[None-postgres_repository] PASSED
test_unproven_persisted_aware_replay_event_is_invalid[unknown-sqlite_repository] PASSED
test_unproven_persisted_aware_replay_event_is_invalid[unknown-postgres_repository] PASSED
============================= 125 passed in 47.09s =============================
```

The parity test commits both databases, expires both ORM sessions, creates fresh
sessions, then compares each replay event's `event_at`, quality status, payload,
event type, source kind, and source ID for equality.

Fresh-session legacy tests verify both SQLite and PostgreSQL return `INVALID`
for NULL/unknown provenance with aware timestamps; the naive legacy case is
also invalid. All four backend/provenance combinations execute under the
runner.

Exit status: `0`.

### Provenance Migration Test

Command:

```text
tools/run_tests.sh test/paper_trading/storage/test_enum_migration.py -k replay_time_provenance -v
```

Output summary:

```text
1 passed, 35 deselected in 3.62s
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
  invalid when provenance is NULL/unknown, regardless of timestamp awareness;
  a separate explicit repair workflow is required to assert canonical
  provenance.
- The runner emits existing `en_US.UTF-8` and Docker `No services to build`
  warnings. They did not affect test execution.

## Final Result

Canonical UTC timestamp provenance is now explicit and auditable across SQLite
and PostgreSQL. SQLite no longer gains `VALID` solely from its dialect; only
rows written with `canonical_utc` provenance do. All required verification
commands completed with the results above.
