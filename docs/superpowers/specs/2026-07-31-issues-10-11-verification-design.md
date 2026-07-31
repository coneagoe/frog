# Issues 10 and 11 Verification and Closure Design

## Goal

Verify that commit `d1cabd2` satisfies the acceptance criteria for GitHub
issues #10 and #11, then close both issues with concise evidence. Production
code changes are out of scope unless focused verification identifies a real
acceptance gap.

## Scope

### Issue 10: Run EOD Matching After Warning-Level Downloads

Verify the A-share daily-history DAG behavior in
`dags/download_stock_history_daily.py`:

- The aggregate invokes paper-trading batch matching with the same business
  date used for download and summary.
- A warning summary continues to matching so orders with exact-date bars can
  fill while orders lacking data remain accepted.
- A closed-market date skips matching.
- Fatal aggregate outcomes do not invoke matching.

### Issue 11: Make Partial-Data Snapshots Observable

Verify the matching and snapshot behavior in `paper_trading/services/` and its
storage contracts:

- Accounts with positions or same-date activity receive either an exact-date
  snapshot or a durable valuation-gap outcome for that business date.
- Missing exact-date data never becomes an execution price and affected orders
  remain accepted.
- Retry behavior is auditable and does not duplicate fills.
- Matching-run warnings and valuation-gap details remain persisted and
  observable through the existing API and CLI paths.

## Verification Method

Review `d1cabd2` against both issue bodies and execute the focused test
modules that exercise DAG warning handling, matching, snapshots, API responses,
and CLI propagation. Use `uv run pytest` for all Python test commands.

The minimum evidence set is:

1. `test/dags/test_partition_dag_sources.py` for business-date propagation,
   warning continuation, fatal gating, and closed-market skipping.
2. `test/paper_trading/services/test_matching_service.py` for mixed matching,
   missing-data diagnostics, retries, and duplicate-fill prevention.
3. `test/paper_trading/services/test_snapshot_service.py` for exact-date
   snapshots and valuation gaps.
4. `test/paper_trading/api/test_matching_api.py` and
   `test/tools/test_paper_trading_cli.py` for observable warning and gap
   outcomes.

## Closure Criteria

Close both GitHub issues only when the focused tests pass and the candidate
implementation matches every listed acceptance criterion. Add one closure
comment per issue that identifies the commit and the validation evidence.

If a check fails or diff review exposes a gap, do not close the affected issue.
Report the evidence, return to design, and create a new implementation plan
for the smallest corrective change.

## Out of Scope

- Production-code or schema changes without a failed acceptance check.
- Broad repository test, lint, or type-check gates unrelated to these issues.
- Changes to DAG schedule, dependencies, retries, task boundaries, or SLA.
- Reverting or incorporating existing unrelated worktree changes.
