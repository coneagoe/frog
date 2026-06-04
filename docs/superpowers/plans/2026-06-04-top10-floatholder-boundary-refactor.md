# Top10 Floatholder Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `shareholder_monitor/` into clearer long-term package boundaries: reusable `top10_floatholder/` domain logic and `monitor/top10_floatholder/` alert orchestration.

**Architecture:** Keep pure/reusable前十大流通股东 analysis under `top10_floatholder/`; keep storage/email side effects under `monitor/top10_floatholder/`. Update imports, tests, and docs without changing runtime behavior, DAG schedule, storage schema, or alert semantics.

**Tech Stack:** Python 3.11+, pytest, pandas, Airflow DAG import patterns, Poetry commands. Do not create git commits unless the user explicitly requests committing.

---

## File Structure

### Create

- `top10_floatholder/__init__.py`
  - Exports reusable domain APIs.
- `top10_floatholder/ssf_detector.py`
  - Moved from `shareholder_monitor/ssf_detector.py`.
- `top10_floatholder/ssf_change_analyzer.py`
  - Moved from `shareholder_monitor/ssf_change_analyzer.py`.
- `monitor/top10_floatholder/__init__.py`
  - Exports monitor entrypoint APIs.
- `monitor/top10_floatholder/runner.py`
  - Moved from `shareholder_monitor/runner.py`; imports analyzer from `top10_floatholder`.
- `monitor/top10_floatholder/ssf_alert.py`
  - Moved from `shareholder_monitor/ssf_alert.py`.
- `test/top10_floatholder/test_ssf_detector.py`
  - Moved from `test/shareholder_monitor/test_ssf_detector.py`.
- `test/top10_floatholder/test_ssf_change_analyzer.py`
  - Moved from `test/shareholder_monitor/test_ssf_change_analyzer.py`.
- `test/monitor/top10_floatholder/test_ssf_alert.py`
  - Moved from `test/shareholder_monitor/test_ssf_alert.py`.
- `test/monitor/top10_floatholder/test_runner.py`
  - Moved from `test/shareholder_monitor/test_runner.py`.

### Modify

- `dags/scan_top10_floatholder_weekly.py`
  - Import `run_ssf_change_alert` from `monitor.top10_floatholder`.
- `factor/alphapurify_ssf_common.py`
  - Import `is_social_security_holder` from `top10_floatholder.ssf_detector`.
- `docs/ssf_count_factor_evaluation.md`
  - Update module path references.
- `docs/ssf_ratio_factor_evaluation.md`
  - Update module path references.
- `docs/ssf_ratio_change_factor_evaluation.md`
  - Update module path references.

### Delete

- `shareholder_monitor/__init__.py`
- `shareholder_monitor/runner.py`
- `shareholder_monitor/ssf_alert.py`
- `shareholder_monitor/ssf_change_analyzer.py`
- `shareholder_monitor/ssf_detector.py`
- `test/shareholder_monitor/test_runner.py`
- `test/shareholder_monitor/test_ssf_alert.py`
- `test/shareholder_monitor/test_ssf_change_analyzer.py`
- `test/shareholder_monitor/test_ssf_detector.py`

---

### Task 1: Move reusable domain logic to `top10_floatholder/`

**Files:**
- Create: `top10_floatholder/__init__.py`
- Move: `shareholder_monitor/ssf_detector.py` -> `top10_floatholder/ssf_detector.py`
- Move: `shareholder_monitor/ssf_change_analyzer.py` -> `top10_floatholder/ssf_change_analyzer.py`
- Move: `test/shareholder_monitor/test_ssf_detector.py` -> `test/top10_floatholder/test_ssf_detector.py`
- Move: `test/shareholder_monitor/test_ssf_change_analyzer.py` -> `test/top10_floatholder/test_ssf_change_analyzer.py`

- [ ] **Step 1: Move domain files**

Run:

```bash
mkdir -p top10_floatholder test/top10_floatholder
mv shareholder_monitor/ssf_detector.py top10_floatholder/ssf_detector.py
mv shareholder_monitor/ssf_change_analyzer.py top10_floatholder/ssf_change_analyzer.py
mv test/shareholder_monitor/test_ssf_detector.py test/top10_floatholder/test_ssf_detector.py
mv test/shareholder_monitor/test_ssf_change_analyzer.py test/top10_floatholder/test_ssf_change_analyzer.py
```

Expected: files are moved; no behavior has changed yet.

- [ ] **Step 2: Add domain package exports**

Create `top10_floatholder/__init__.py` with:

```python
from .ssf_change_analyzer import SSFChangeAnalysisOutcome, analyze_ssf_change
from .ssf_detector import is_social_security_holder

__all__ = [
    "SSFChangeAnalysisOutcome",
    "analyze_ssf_change",
    "is_social_security_holder",
]
```

- [ ] **Step 3: Update analyzer import**

In `top10_floatholder/ssf_change_analyzer.py`, replace the old relative detector import with:

```python
from top10_floatholder.ssf_detector import is_social_security_holder
```

If the file already uses a relative import like this:

```python
from .ssf_detector import is_social_security_holder
```

Either relative or absolute import is acceptable inside the package. Prefer keeping the relative import to minimize change:

```python
from .ssf_detector import is_social_security_holder
```

- [ ] **Step 4: Update domain tests imports**

In `test/top10_floatholder/test_ssf_detector.py`, import:

```python
from top10_floatholder.ssf_detector import is_social_security_holder
```

In `test/top10_floatholder/test_ssf_change_analyzer.py`, import:

```python
from top10_floatholder.ssf_change_analyzer import (
    SSFChangeAnalysisOutcome,
    analyze_ssf_change,
)
```

- [ ] **Step 5: Run moved domain tests**

Run:

```bash
poetry run pytest test/top10_floatholder -q
```

Expected: tests pass, proving domain logic still behaves the same after package move.

- [ ] **Step 6: Checkpoint**

Run:

```bash
git diff -- top10_floatholder test/top10_floatholder shareholder_monitor test/shareholder_monitor
```

Expected: diff shows file moves and import path updates only. Do not commit unless the user explicitly requests it.

---

### Task 2: Move monitor orchestration to `monitor/top10_floatholder/`

**Files:**
- Create: `monitor/top10_floatholder/__init__.py`
- Move: `shareholder_monitor/runner.py` -> `monitor/top10_floatholder/runner.py`
- Move: `shareholder_monitor/ssf_alert.py` -> `monitor/top10_floatholder/ssf_alert.py`
- Move: `test/shareholder_monitor/test_runner.py` -> `test/monitor/top10_floatholder/test_runner.py`
- Move: `test/shareholder_monitor/test_ssf_alert.py` -> `test/monitor/top10_floatholder/test_ssf_alert.py`

- [ ] **Step 1: Move monitor files**

Run:

```bash
mkdir -p monitor/top10_floatholder test/monitor/top10_floatholder
mv shareholder_monitor/runner.py monitor/top10_floatholder/runner.py
mv shareholder_monitor/ssf_alert.py monitor/top10_floatholder/ssf_alert.py
mv test/shareholder_monitor/test_runner.py test/monitor/top10_floatholder/test_runner.py
mv test/shareholder_monitor/test_ssf_alert.py test/monitor/top10_floatholder/test_ssf_alert.py
```

Expected: runner and alert files are now under the monitor package.

- [ ] **Step 2: Add monitor package exports**

Create `monitor/top10_floatholder/__init__.py` with:

```python
from .runner import SSFAlertSummary, run_ssf_change_alert

__all__ = ["SSFAlertSummary", "run_ssf_change_alert"]
```

- [ ] **Step 3: Update runner imports**

In `monitor/top10_floatholder/runner.py`, use:

```python
from top10_floatholder.ssf_change_analyzer import SSFChangeAnalysisOutcome, analyze_ssf_change

from .ssf_alert import build_ssf_change_alert_email
```

The complete import block should remain equivalent to:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from storage import get_storage
from top10_floatholder.ssf_change_analyzer import SSFChangeAnalysisOutcome, analyze_ssf_change
from utility import send_email

from .ssf_alert import build_ssf_change_alert_email
```

- [ ] **Step 4: Update monitor tests imports and patch targets**

In `test/monitor/top10_floatholder/test_runner.py`, import:

```python
from monitor.top10_floatholder.runner import run_ssf_change_alert
```

Replace all patch strings:

```python
"shareholder_monitor.runner.get_storage"
"shareholder_monitor.runner.send_email"
"shareholder_monitor.runner.logger"
```

with:

```python
"monitor.top10_floatholder.runner.get_storage"
"monitor.top10_floatholder.runner.send_email"
"monitor.top10_floatholder.runner.logger"
```

In `test/monitor/top10_floatholder/test_ssf_alert.py`, import:

```python
from monitor.top10_floatholder.ssf_alert import build_ssf_change_alert_email
```

- [ ] **Step 5: Run moved monitor tests**

Run:

```bash
poetry run pytest test/monitor/top10_floatholder -q
```

Expected: tests pass, proving runner and alert behavior are unchanged.

- [ ] **Step 6: Checkpoint**

Run:

```bash
git diff -- monitor/top10_floatholder test/monitor/top10_floatholder shareholder_monitor test/shareholder_monitor
```

Expected: diff shows file moves and import path updates only. Do not commit unless the user explicitly requests it.

---

### Task 3: Update production call sites and docs

**Files:**
- Modify: `dags/scan_top10_floatholder_weekly.py`
- Modify: `factor/alphapurify_ssf_common.py`
- Modify: `docs/ssf_count_factor_evaluation.md`
- Modify: `docs/ssf_ratio_factor_evaluation.md`
- Modify: `docs/ssf_ratio_change_factor_evaluation.md`
- Delete: `shareholder_monitor/__init__.py`

- [ ] **Step 1: Update DAG import**

In `dags/scan_top10_floatholder_weekly.py`, replace:

```python
from shareholder_monitor import run_ssf_change_alert  # noqa: E402
```

with:

```python
from monitor.top10_floatholder import run_ssf_change_alert  # noqa: E402
```

- [ ] **Step 2: Update factor import and comment**

In `factor/alphapurify_ssf_common.py`, replace:

```python
from shareholder_monitor.ssf_detector import is_social_security_holder
```

with:

```python
from top10_floatholder.ssf_detector import is_social_security_holder
```

Also update the docstring/comment sentence from:

```text
shareholder_monitor.ssf_detector.is_social_security_holder
```

to:

```text
top10_floatholder.ssf_detector.is_social_security_holder
```

- [ ] **Step 3: Update docs module paths**

In these files:

```text
docs/ssf_count_factor_evaluation.md
docs/ssf_ratio_factor_evaluation.md
docs/ssf_ratio_change_factor_evaluation.md
```

Replace:

```text
shareholder_monitor.ssf_detector.is_social_security_holder
```

with:

```text
top10_floatholder.ssf_detector.is_social_security_holder
```

- [ ] **Step 4: Remove old package init**

Run:

```bash
rm shareholder_monitor/__init__.py
```

Expected: `shareholder_monitor/` contains no tracked `.py` files after Tasks 1-3.

- [ ] **Step 5: Search for stale imports**

Run:

```bash
poetry run python - <<'PY'
from pathlib import Path
matches = []
for path in Path('.').rglob('*'):
    if (
        path.is_dir()
        or '.git' in path.parts
        or '__pycache__' in path.parts
        or '.review-84d0db7' in path.parts
        or (len(path.parts) >= 2 and path.parts[0] == 'docs' and path.parts[1] == 'superpowers')
    ):
        continue
    if path.suffix not in {'.py', '.md'}:
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    if 'shareholder_monitor' in text:
        matches.append(str(path))
print('\n'.join(matches))
raise SystemExit(1 if matches else 0)
PY
```

Expected: no output and exit code 0. Historical mentions inside `docs/superpowers/` are excluded.

---

### Task 4: Validate DAG import and focused test suite

**Files:**
- Test: `test/dags/test_scan_top10_floatholder_weekly.py`
- Test: `test/top10_floatholder/*`
- Test: `test/monitor/top10_floatholder/*`

- [ ] **Step 1: Run focused package tests**

Run:

```bash
poetry run pytest test/top10_floatholder test/monitor/top10_floatholder -q
```

Expected: all moved domain and monitor tests pass.

- [ ] **Step 2: Run DAG test**

Run:

```bash
poetry run pytest test/dags/test_scan_top10_floatholder_weekly.py -q
```

Expected: DAG imports successfully and task wiring assertions continue to pass. No DAG schedule, dependencies, retries, task boundaries, or SLA should change.

- [ ] **Step 3: Run import smoke checks**

Run:

```bash
poetry run python - <<'PY'
from monitor.top10_floatholder import SSFAlertSummary, run_ssf_change_alert
from top10_floatholder import SSFChangeAnalysisOutcome, analyze_ssf_change, is_social_security_holder

assert callable(run_ssf_change_alert)
assert SSFAlertSummary.__name__ == 'SSFAlertSummary'
assert callable(analyze_ssf_change)
assert SSFChangeAnalysisOutcome.INSUFFICIENT_HISTORY.name == 'INSUFFICIENT_HISTORY'
assert is_social_security_holder('全国社保基金一一八组合') is True
PY
```

Expected: command exits 0 with no output.

---

### Task 5: Run final checks and inspect diff

**Files:**
- All files changed by Tasks 1-4.

- [ ] **Step 1: Run full relevant tests**

Run:

```bash
poetry run pytest test/top10_floatholder test/monitor/top10_floatholder test/dags/test_scan_top10_floatholder_weekly.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run broader suite if time allows**

Run:

```bash
poetry run pytest test -q
```

Expected: repository tests pass. If unrelated legacy failures appear, record exact failing tests and confirm the focused refactor tests still pass.

- [ ] **Step 3: Inspect changed files**

Run:

```bash
git status --short
git diff --stat
```

Expected changed files include only:

```text
docs/superpowers/specs/2026-06-04-top10-floatholder-monitor-boundary-design.md
docs/superpowers/plans/2026-06-04-top10-floatholder-boundary-refactor.md
dags/scan_top10_floatholder_weekly.py
factor/alphapurify_ssf_common.py
docs/ssf_count_factor_evaluation.md
docs/ssf_ratio_factor_evaluation.md
docs/ssf_ratio_change_factor_evaluation.md
top10_floatholder/*
monitor/top10_floatholder/*
test/top10_floatholder/*
test/monitor/top10_floatholder/*
deleted shareholder_monitor/*
deleted test/shareholder_monitor/*
```

- [ ] **Step 4: Final stale path search**

Run:

```bash
poetry run python - <<'PY'
from pathlib import Path
terms = ['shareholder_monitor', 'from shareholder_monitor', 'patch("shareholder_monitor']
matches = []
for path in Path('.').rglob('*'):
    if (
        path.is_dir()
        or '.git' in path.parts
        or '__pycache__' in path.parts
        or '.review-84d0db7' in path.parts
        or (len(path.parts) >= 2 and path.parts[0] == 'docs' and path.parts[1] == 'superpowers')
    ):
        continue
    if path.suffix not in {'.py', '.md'}:
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    for term in terms:
        if term in text:
            matches.append(f'{path}: {term}')
print('\n'.join(matches))
raise SystemExit(1 if matches else 0)
PY
```

Expected: no output and exit code 0. Historical mentions inside `docs/superpowers/` are excluded.

- [ ] **Step 5: Report completion**

Summarize:

```text
Moved reusable 前十大流通股东 SSF detection/analysis to top10_floatholder/.
Moved monitor runner/email alert orchestration to monitor/top10_floatholder/.
Updated DAG, factor, tests, and docs imports.
Focused tests: <paste command results>.
Full tests: <paste command result or explain if skipped>.
```

Do not commit unless the user explicitly requests it.

---

## Self-Review Notes

- Spec coverage: The plan implements the approved split between `top10_floatholder/` domain logic and `monitor/top10_floatholder/` orchestration, updates DAG/factor/docs/tests, preserves behavior, and verifies stale imports are gone.
- Placeholder scan: No TBD/TODO/fill-in placeholders remain; commands and import strings are explicit.
- Type consistency: Exported names match existing names: `SSFAlertSummary`, `run_ssf_change_alert`, `SSFChangeAnalysisOutcome`, `analyze_ssf_change`, and `is_social_security_holder`.
- Higher-priority repository instruction: Python commands use `poetry run`; commit steps are omitted because commits require explicit user request.
