# Monitor Alert Outbox Reliability Report

## Scope

Issue #98 remediation adds PostgreSQL monitor enum bootstrap before outbox table creation or use, lease fencing for delivery outcomes, and explicit lost-claim reporting by the delivery task.

## Guarantees

- PostgreSQL outbox access runs `migrate_monitor_enums` in the same engine transaction before table creation or use. The migration owns creation and validation of the monitor tables and enum types.
- A claimed notification carries its `claimed_at` lease timestamp into both success and failure settlement.
- Settlement only changes a row when its ID, `processing` state, and `claimed_at` timestamp all match the worker's claim.
- A stale worker cannot mark a notification delivered, increment attempts, schedule a retry, or overwrite errors after a newer claim exists.
- A cancelled notification remains distinguishable from a lost claim. Delivery summaries expose `cancelled` and `lost_claim` independently.

## Evidence

- `test_stale_claim_cannot_settle_a_newer_claim` creates stale claim A, recovers it as claim B, and verifies A cannot settle B's lease.
- `test_runtime_outbox_bootstrap_creates_monitor_enums_before_tables` runs against the isolated PostgreSQL test service and verifies all monitor enum types and the enum-backed outbox state column exist after runtime bootstrap.
- Delivery-task tests verify successful, retry, terminal failure, cancellation, and lost-claim accounting paths.
- PostgreSQL database-script tests verify monitor enum creation and restoration of the notification foreign key dependency.
- PostgreSQL failure-retry tests assert exact backoff delays of 1, 2, 4, and 8 minutes; attempt 5 remains terminal and
  nonclaimable.

## Remaining Limits

- SMTP delivery occurs before persistence of the delivery result. A process failure after SMTP accepts mail and before settlement may produce a later retry, so email delivery remains at-least-once rather than exactly-once.
- Claims older than 30 minutes are intentionally recoverable. The fence prevents the old worker from mutating the recovered row, but cannot retract an email it already sent.

## Final review verification

- `tools/run_tests.sh test/tools/test_db_scripts_postgresql.py test/monitor/storage/test_monitor_notification_postgresql.py -v`: **8 passed in 25.26s**.
- `uv run pytest test/storage/test_monitor_notification_storage.py -q`: **8 passed in 4.90s**.
- `uv run ruff check test/tools/test_db_scripts_postgresql.py test/monitor/storage/test_monitor_notification_postgresql.py test/storage/test_monitor_notification_storage.py storage/storage_db.py`: **All checks passed!**
- `uv run ruff format --check test/tools/test_db_scripts_postgresql.py test/monitor/storage/test_monitor_notification_postgresql.py test/storage/test_monitor_notification_storage.py storage/storage_db.py`: **4 files already formatted**.
