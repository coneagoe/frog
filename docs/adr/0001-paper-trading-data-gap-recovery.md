# ADR 0001: Paper-trading A-share BFQ data-gap recovery

- **Status:** Accepted
- **Date:** 2026-09-13
- **Issue:** #109

## Decision

Recover exact-date A-share BFQ gaps in one batch task after the complete
historical download, rather than issuing a request per order. Persist a mutable
gap summary plus immutable candidates, attempts, approvals, account results,
batch results, and alert cycles. Process each gap and account independently.

Keep data state separate from account business state. Data-bar write, ledger
rebuild, and snapshot recalculation are separate transactions. A successful
ledger rebuild therefore survives a later snapshot failure. Reuse and extend
`LedgerRebuildService` and `SnapshotRecalculationService` only for explicit
session/transaction boundaries; do not duplicate their replay logic.

Escalated candidates require a single-user browser approval using the existing
session cookie and CSRF token. There is no role model or second approver. The
bearer API token is reserved for trusted automation and read-only query/CLI
operations. Approval binds to an immutable candidate SHA-256 hash.

## Rationale

Batching avoids repeated provider calls, gives one consistent recovery cutoff,
and permits all download partitions to be assessed before business repair.
Per-gap/per-account isolation prevents one bad security, account, or provider
response from losing unrelated progress. Split transactions provide the needed
ledger-success/snapshot-failure guarantee. Immutable evidence makes provider
decisions and manual approvals reproducible even when the mutable summary moves
on.

## Rejected alternatives

* **Recover inline during matching:** rejected because it couples provider
  availability to order execution and can fabricate or partially replay state.
* **One transaction for the whole batch:** rejected because a large rollback
  would erase valid gaps/accounts and cannot preserve a successful ledger when a
  snapshot fails.
* **Automatic approval for every escalated candidate:** rejected because stale
  or conflicting data needs an explicit single-user decision.
* **New administrator/approval roles:** rejected for the current single-user
  product; existing browser authentication and CSRF are sufficient.
* **Copying rebuild implementations:** rejected because it would diverge from
  existing replay, locking, and idempotency behavior.
