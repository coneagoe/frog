# Issues 10 and 11 Verification and Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify commit `d1cabd2` satisfies issues #10 and #11, then close both with evidence.

**Architecture:** No production code changes are planned. Review the candidate implementation against the issue contracts, run focused acceptance tests, and close each issue only when its checks pass. Any failed criterion is a stop condition requiring a new design and corrective plan.

**Tech Stack:** GitHub CLI, Python 3.11+, pytest, Apache Airflow, SQLAlchemy, `uv`.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Do not modify production code or schemas unless verification demonstrates an acceptance gap.
- Do not alter DAG schedules, dependencies, retries, task boundaries, or SLA.
- Do not revert, stage, commit, or incorporate unrelated worktree changes.
- Do not close an issue unless every acceptance criterion has passing evidence.
- Do not create a git commit unless the user explicitly requests one.

---

## File Structure

| Area | Files | Responsibility |
| --- | --- | --- |
| Issue contracts | GitHub issues `#10`, `#11` | Closure acceptance criteria. |
| EOD workflow | `dags/download_stock_history_daily.py`, `test/dags/test_partition_dag_sources.py` | Same-date matching, warnings, fatal gating, closed dates. |
| Matching and snapshots | `paper_trading/services/matching_service.py`, `paper_trading/services/snapshot_service.py`, service tests | Exact-date execution, valuation gaps, retry safety. |
| Operator surfaces | `test/paper_trading/api/test_matching_api.py`, `test/tools/test_paper_trading_cli.py` | Observable warnings and valuation gaps. |

### Task 1: Verify Issue 10 Workflow Contract

**Files:**
- Inspect: `dags/download_stock_history_daily.py:200-313`
- Test: `test/dags/test_partition_dag_sources.py`
- Inspect: GitHub issue `#10`

**Interfaces:**
- Consumes: issue #10 acceptance criteria and candidate commit `d1cabd2`.
- Produces: evidence for same-date matching, warning continuation, fatal gating, and closed-market skipping.

- [ ] **Step 1: Read the issue and candidate diff**

Run:

```bash
gh issue view 10 --comments
git show --format=fuller --stat d1cabd2 -- dags/download_stock_history_daily.py test/dags/test_partition_dag_sources.py
```

Expected: The diff and issue describe matching on complete or warning summaries using the business date.

- [ ] **Step 2: Inspect the DAG implementation**

Confirm that aggregation invokes:

```python
run_paper_trading_matching_for_active_accounts(business_date)
```

after complete or warning summaries but not fatal summaries. Confirm the DAG passes its derived business date and returns before matching on closed-market dates.

- [ ] **Step 3: Run focused DAG acceptance tests**

Run:

```bash
uv run pytest test/dags/test_partition_dag_sources.py -q
```

Expected: PASS, including warning-summary matching, closed-market skip, fatal gating, task wiring, and business-date propagation.

- [ ] **Step 4: Gate Issue 10**

Record `PASS` only when Steps 1-3 succeed. If any step fails, do not close issue #10; report the failed criterion and return to design.

### Task 2: Verify Issue 11 Matching and Snapshot Contract

**Files:**
- Inspect: `paper_trading/services/matching_service.py:35-167`
- Inspect: `paper_trading/services/snapshot_service.py:23-100`
- Test: `test/paper_trading/services/test_matching_service.py`
- Test: `test/paper_trading/services/test_snapshot_service.py`
- Inspect: GitHub issue `#11`

**Interfaces:**
- Consumes: issue #11 acceptance criteria and Task 1 PASS evidence.
- Produces: evidence for exact-date-only execution, durable valuation gaps, and retry-safe fills.

- [ ] **Step 1: Read the issue and candidate diff**

Run:

```bash
gh issue view 11 --comments
git show --format=fuller --stat d1cabd2 -- paper_trading/services/matching_service.py paper_trading/services/snapshot_service.py paper_trading/storage/repository.py storage/model/paper_trading.py storage/storage_db.py
```

Expected: The candidate contains durable valuation-gap storage and exact-date-only matching and snapshot behavior.

- [ ] **Step 2: Inspect exact-date and retry behavior**

Confirm that missing exact-date BFQ bars leave orders `ACCEPTED`, never supply a stale execution price, and invoke:

```python
snapshot_service.generate_snapshot_or_gap(account_id, trade_date)
```

when an account cannot be valued. Confirm matching processes accepted orders so retries cannot refill terminal orders.

- [ ] **Step 3: Run focused matching and snapshot tests**

Run:

```bash
uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_snapshot_service.py -q
```

Expected: PASS, including mixed symbols, valuation gaps, snapshot retry, and duplicate-fill prevention.

- [ ] **Step 4: Gate Issue 11**

Record `PASS` only when Steps 1-3 succeed. If any step fails, do not close issue #11; report the failed criterion and return to design.

### Task 3: Verify Operator Surfaces and Close Issues

**Files:**
- Test: `test/paper_trading/api/test_matching_api.py`
- Test: `test/tools/test_paper_trading_cli.py`
- Modify externally: GitHub issues `#10`, `#11` only

**Interfaces:**
- Consumes: PASS evidence from Tasks 1 and 2.
- Produces: closed GitHub issues with criterion-specific evidence comments.

- [ ] **Step 1: Run observable-boundary tests**

Run:

```bash
uv run pytest test/paper_trading/api/test_matching_api.py test/tools/test_paper_trading_cli.py -q
```

Expected: PASS, showing the API and CLI retain matching warning counts and valuation-gap outcomes.

- [ ] **Step 2: Recheck issue state and working tree**

Run:

```bash
gh issue view 10 --json number,state,url
gh issue view 11 --json number,state,url
git status --short
```

Expected: Both issues are open, and verification has not staged or modified unrelated files.

- [ ] **Step 3: Close Issue 10 with evidence**

Run:

```bash
gh issue close 10 --comment "Verified in commit d1cabd2. Focused DAG tests passed for same-business-date matching, warning-summary continuation, closed-market skip, and fatal-summary gating."
```

Expected: GitHub reports issue #10 as closed.

- [ ] **Step 4: Close Issue 11 with evidence**

Run:

```bash
gh issue close 11 --comment "Verified in commit d1cabd2. Focused matching, snapshot, API, and CLI tests passed for exact-date execution, valuation gaps, observable warnings, and retry-safe non-duplicated fills."
```

Expected: GitHub reports issue #11 as closed.

- [ ] **Step 5: Confirm closure**

Run:

```bash
gh issue view 10 --json number,state,url
gh issue view 11 --json number,state,url
```

Expected: Both issues have `state` equal to `CLOSED`.

## Plan Self-Review

- Task 1 covers every Issue 10 criterion; Task 2 covers every Issue 11 criterion; Task 3 validates operational boundaries and makes issue closure conditional.
- The plan contains no placeholders or undefined code interfaces.
- The plan preserves the approved no-production-change scope.
