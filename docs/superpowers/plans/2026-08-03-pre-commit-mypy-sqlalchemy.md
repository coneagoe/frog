# Pre-commit Mypy SQLAlchemy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the isolated pre-commit mypy hook's SQLAlchemy dependency with the project environment.

**Architecture:** The hook will install the SQLAlchemy version locked for the project through `additional_dependencies`. Repository guidance will require keeping this pin synchronized when the lockfile changes. Validation runs both the isolated hook and project mypy command.

**Tech Stack:** pre-commit 4.6.0, mirrors-mypy 1.20.2, SQLAlchemy 2.0.51, uv

## Global Constraints

- Pin the hook dependency as `sqlalchemy==2.0.51`.
- Keep the mypy hook revision at `v1.20.2`.
- Do not modify application source code or runtime project dependencies.

---

### Task 1: Align The Mypy Hook Environment

**Files:**
- Modify: `.pre-commit-config.yaml:19-29`
- Modify: `AGENTS.md:76-78`

**Interfaces:**
- Consumes: `uv.lock` package version `sqlalchemy==2.0.51`.
- Produces: a pre-commit mypy environment with the project's SQLAlchemy type information installed.

- [ ] **Step 1: Add the pinned SQLAlchemy hook dependency**

```yaml
additional_dependencies:
  - sqlalchemy==2.0.51
```

- [ ] **Step 2: Document synchronization rule**

Add this rule in the Type Checking Scope section of `AGENTS.md`:

```markdown
- When updating the SQLAlchemy version in `uv.lock`, update the matching `sqlalchemy==...` pin in `.pre-commit-config.yaml`.
```

- [ ] **Step 3: Rebuild and run the isolated hook**

Run: `uv run pre-commit clean && uv run pre-commit run mypy --files paper_trading/storage/repository.py`

Expected: the hook installs SQLAlchemy 2.0.51 and reports no type errors for `repository.py`.

- [ ] **Step 4: Run project mypy**

Run: `uv run mypy`

Expected: `Success: no issues found`.

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml AGENTS.md docs/superpowers/specs/2026-08-03-pre-commit-mypy-sqlalchemy-design.md docs/superpowers/plans/2026-08-03-pre-commit-mypy-sqlalchemy.md
git commit -m "Align pre-commit mypy dependencies"
```
