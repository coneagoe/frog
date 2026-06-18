# Poetry to uv and Ruff Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the repository from Poetry to uv and replace Black, isort, and Flake8 with Ruff across local development, pre-commit, CI, Docker, and developer-facing command documentation.

**Architecture:** Keep `pyproject.toml` as the single source of truth for project metadata and dependencies, switch dependency syncing and command execution to `uv`, and consolidate formatting/linting into `ruff format` and `ruff check`. Make the migration repo-wide but tightly scoped to packaging, tooling, container/CI setup, and human-facing command references; do not change business logic.

**Tech Stack:** Python 3.11+, uv, Ruff, mypy, pytest, pre-commit, GitHub Actions, Docker, Alpine Linux.

## Global Constraints

- Use `uv` as the only supported dependency-management and Python-command entrypoint after migration.
- Remove `poetry.lock` and commit `uv.lock` as the only lock file.
- Replace `black`, `isort`, and `flake8` with Ruff without widening lint scope beyond the current toolchain intent.
- Keep line length at `120`.
- Preserve Python version constraint `>=3.11,<3.13`.
- Keep current `pytest` and `mypy` behavior and existing mypy override scope unless a direct migration need requires adjustment.
- Do not change business logic, Airflow DAG schedule/dependencies/retries/task boundaries/SLA, or unrelated code.
- Use `uv run` instead of bare `python`/`pytest`/tool commands in repo instructions and automation.

---

## File Structure

- Modify `pyproject.toml`: replace Poetry-specific build/dev/source config with uv-compatible dependency groups/indexes and add Ruff configuration.
- Create `uv.lock`: new lock file generated from the migrated configuration.
- Delete `poetry.lock`: remove Poetry lock file.
- Modify `.pre-commit-config.yaml`: replace Black/isort/Flake8 hooks with Ruff hooks and keep mypy.
- Modify `.github/workflows/ci.yml`: install uv, cache uv data/venv, run `uv sync --group dev`, and switch checks to `uv run`.
- Modify `Dockerfile`: install uv, copy `uv.lock`, and install dependencies with uv instead of Poetry.
- Modify `README.md`: update setup and quality commands to uv/Ruff.
- Modify `CLAUDE.md`: update developer command guidance and verification whitelist to uv/Ruff.
- Modify `docs/paper_trading.md`: update manual backend startup command.
- Modify `factor/alphapurify_ssf_ratio.py`: replace Poetry install hint with uv-based hint.
- Modify `factor/alphapurify_ssf_ratio_change.py`: replace Poetry install hint with uv-based hint.
- Modify `factor/alphapurify_ssf_count.py`: replace Poetry install hint with uv-based hint.
- Modify `factor/alphapurify_volatility.py`: replace Poetry install hint with uv-based hint.
- Modify `factor/alphapurify_momentum.py`: replace Poetry install hint with uv-based hint.
- Modify `factor/alphapurify_obos.py`: replace Poetry install hint with uv-based hint.
- Modify `docs/superpowers/plans/2026-06-16-paper-trading-backend.md`: update Poetry commands inside the existing plan document.
- Modify `docs/superpowers/plans/2026-06-16-paper-trading-frontend.md`: update Poetry command inside the existing plan document.

### Task 1: Migrate Core Packaging And Locking

**Files:**
- Modify: `pyproject.toml`
- Create: `uv.lock`
- Delete: `poetry.lock`

**Interfaces:**
- Consumes: existing PEP 621 metadata and dependency list in `pyproject.toml`
- Produces: uv-compatible dependency metadata, development dependency group, Ruff config, and a committed `uv.lock`

- [ ] **Step 1: Write the failing config test**

Create `test/tools/test_packaging_metadata.py`:

```python
from pathlib import Path

import tomllib


def test_pyproject_uses_uv_and_ruff_instead_of_poetry_lint_stack():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    build_system = data["build-system"]
    assert "poetry-core" not in build_system["requires"]

    dependency_groups = data.get("dependency-groups", {})
    assert "dev" in dependency_groups

    dev_group = dependency_groups["dev"]
    assert any(str(item).startswith("ruff") for item in dev_group)
    assert not any(str(item).startswith("flake8") for item in dev_group)

    assert "tool" in data
    assert "ruff" in data["tool"]
    assert "poetry" not in data["tool"]
    assert "isort" not in data["tool"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest test/tools/test_packaging_metadata.py -q
```

Expected: FAIL because `uv` is not configured yet and/or the new assertions do not match current `pyproject.toml`.

- [ ] **Step 3: Write the minimal packaging migration**

Edit `pyproject.toml` to follow this structure:

```toml
[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pre-commit>=4.2.0,<5.0.0",
    "ruff>=0.12.0,<1.0.0",
    "types-requests>=2.32.4.20250913,<3.0.0.0",
    "mypy>=1.18.2,<2.0.0",
    "pandas-stubs>=2.3.2.250926,<3.0.0.0",
    "types-tqdm>=4.67.0.20250809,<5.0.0.0",
    "types-psycopg2>=2.9.21.20251012,<3.0.0.0",
    "scipy-stubs>=1.16.3.0,<2.0.0.0",
]

[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

Also remove these sections entirely:

```toml
[tool.poetry]
[tool.poetry.group.dev.dependencies]
[tool.isort]
[[tool.poetry.source]]
```

Then generate the lock file and remove the old one:

```bash
rm poetry.lock
uv lock
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest test/tools/test_packaging_metadata.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock test/tools/test_packaging_metadata.py
git rm poetry.lock
git commit -m "chore: migrate packaging from poetry to uv"
```

### Task 2: Replace Pre-commit And CI Toolchain Entrypoints

**Files:**
- Modify: `.pre-commit-config.yaml`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: uv-compatible `pyproject.toml` and `uv.lock` from Task 1
- Produces: repo automation that installs with uv and runs Ruff/pre-commit/tests through `uv run`

- [ ] **Step 1: Write the failing automation tests**

Create `test/tools/test_automation_commands.py`:

```python
from pathlib import Path


def test_pre_commit_uses_ruff_hooks():
    content = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "astral-sh/ruff-pre-commit" in content
    assert "id: ruff-format" in content
    assert "id: ruff" in content
    assert "github.com/psf/black" not in content
    assert "github.com/pycqa/isort" not in content
    assert "github.com/pycqa/flake8" not in content


def test_ci_uses_uv_instead_of_poetry():
    content = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "astral-sh/setup-uv" in content
    assert "uv sync --group dev" in content
    assert "uv run pre-commit run --all-files" in content
    assert "uv run pytest test" in content
    assert "install-poetry" not in content
    assert "poetry install" not in content
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest test/tools/test_automation_commands.py -q
```

Expected: FAIL because the current hooks and CI still reference Poetry/Black/isort/Flake8.

- [ ] **Step 3: Write the minimal automation migration**

Edit `.pre-commit-config.yaml` to use Ruff hooks like this:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
        exclude: '\\.csv$'
        args: [--markdown-linebreak-ext=md]
      - id: end-of-file-fixer
      - id: mixed-line-ending
        args: [--fix=lf]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.12.0
    hooks:
      - id: ruff-format
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.17.1
    hooks:
      - id: mypy
        additional_dependencies:
          - pandas-stubs
          - types-redis
          - types-requests
          - types-tqdm
          - types-psycopg2
          - scipy-stubs
```

Edit `.github/workflows/ci.yml` to follow this command shape:

```yaml
    - name: Install uv
      uses: astral-sh/setup-uv@v5

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}

    - name: Cache uv dependencies
      uses: actions/cache@v4
      with:
        path: |
          ~/.cache/uv
          .venv
        key: ${{ runner.os }}-uv-${{ matrix.python-version }}-${{ hashFiles('uv.lock') }}

    - name: Install dependencies
      run: uv sync --group dev

    - name: Run pre-commit hooks
      run: uv run pre-commit run --all-files

    - name: Run tests
      run: uv run pytest test
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest test/tools/test_automation_commands.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml test/tools/test_automation_commands.py
git commit -m "chore: switch automation to uv and ruff"
```

### Task 3: Migrate Docker And Developer Command Documentation

**Files:**
- Modify: `Dockerfile`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/paper_trading.md`
- Modify: `docs/superpowers/plans/2026-06-16-paper-trading-backend.md`
- Modify: `docs/superpowers/plans/2026-06-16-paper-trading-frontend.md`
- Modify: `factor/alphapurify_ssf_ratio.py`
- Modify: `factor/alphapurify_ssf_ratio_change.py`
- Modify: `factor/alphapurify_ssf_count.py`
- Modify: `factor/alphapurify_volatility.py`
- Modify: `factor/alphapurify_momentum.py`
- Modify: `factor/alphapurify_obos.py`

**Interfaces:**
- Consumes: uv/Ruff command model from Tasks 1-2
- Produces: consistent human-facing commands and Docker install flow with no Poetry references in maintained docs/prompts

- [ ] **Step 1: Write the failing docs/container tests**

Create `test/tools/test_command_documentation.py`:

```python
from pathlib import Path


FILES_WITHOUT_POETRY = [
    "Dockerfile",
    "README.md",
    "CLAUDE.md",
    "docs/paper_trading.md",
    "factor/alphapurify_ssf_ratio.py",
    "factor/alphapurify_ssf_ratio_change.py",
    "factor/alphapurify_ssf_count.py",
    "factor/alphapurify_volatility.py",
    "factor/alphapurify_momentum.py",
    "factor/alphapurify_obos.py",
    "docs/superpowers/plans/2026-06-16-paper-trading-backend.md",
    "docs/superpowers/plans/2026-06-16-paper-trading-frontend.md",
]


def test_selected_docs_and_hints_no_longer_reference_poetry():
    for file_name in FILES_WITHOUT_POETRY:
        content = Path(file_name).read_text(encoding="utf-8")
        assert "poetry" not in content.lower(), file_name


def test_dockerfile_installs_with_uv():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "uv" in content
    assert "poetry" not in content.lower()
    assert "uv.lock" in content
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest test/tools/test_command_documentation.py -q
```

Expected: FAIL because the listed files still contain Poetry commands and the Dockerfile still installs Poetry.

- [ ] **Step 3: Write the minimal docs/container migration**

Update `Dockerfile` so the install flow looks like this:

```dockerfile
FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TUSHARE_TOKEN=${TUSHARE_TOKEN}

RUN apk add --no-cache procps bash gcc g++ musl-dev linux-headers curl
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:${PATH}"
```

Update command examples in `README.md`, `CLAUDE.md`, `docs/paper_trading.md`, and both existing plan docs to use commands in this shape:

```bash
uv sync --group dev
uv run pre-commit install
uv run pre-commit run --all-files
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest test
uv run uvicorn paper_trading.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Update the six `factor/alphapurify_*.py` install hints to this exact message pattern:

```python
"alphapurify 未安装，请先执行: uv add alphapurify"
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
uv run pytest test/tools/test_command_documentation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile README.md CLAUDE.md docs/paper_trading.md docs/superpowers/plans/2026-06-16-paper-trading-backend.md docs/superpowers/plans/2026-06-16-paper-trading-frontend.md factor/alphapurify_ssf_ratio.py factor/alphapurify_ssf_ratio_change.py factor/alphapurify_ssf_count.py factor/alphapurify_volatility.py factor/alphapurify_momentum.py factor/alphapurify_obos.py test/tools/test_command_documentation.py
git commit -m "docs: update repo commands for uv and ruff"
```

### Task 4: Run Full Migration Verification

**Files:**
- Modify: any files from Tasks 1-3 only if verification reveals migration-specific defects

**Interfaces:**
- Consumes: completed repo migration from Tasks 1-3
- Produces: verified uv/Ruff migration with recorded evidence from focused and full checks

- [ ] **Step 1: Run dependency sync**

Run:

```bash
uv sync --group dev
```

Expected: dependencies resolve successfully and `.venv` is populated from `uv.lock`.

- [ ] **Step 2: Run the repo quality gate**

Run:

```bash
uv run pre-commit run --all-files
```

Expected: PASS, or only migration-caused failures that are fixed within the touched file set.

- [ ] **Step 3: Run the test suite**

Run:

```bash
uv run pytest test
```

Expected: PASS, or only pre-existing unrelated failures that are documented and left untouched.

- [ ] **Step 4: Run explicit Ruff and mypy verification**

Run:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Expected: PASS, or only pre-existing unrelated failures that are documented and left untouched.

- [ ] **Step 5: Run Docker build verification**

Run:

```bash
docker compose build app
```

Expected: the `app` image builds successfully using `uv` instead of Poetry.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .pre-commit-config.yaml .github/workflows/ci.yml Dockerfile README.md CLAUDE.md docs/paper_trading.md docs/superpowers/plans/2026-06-16-paper-trading-backend.md docs/superpowers/plans/2026-06-16-paper-trading-frontend.md factor/alphapurify_ssf_ratio.py factor/alphapurify_ssf_ratio_change.py factor/alphapurify_ssf_count.py factor/alphapurify_volatility.py factor/alphapurify_momentum.py factor/alphapurify_obos.py test/tools/test_packaging_metadata.py test/tools/test_automation_commands.py test/tools/test_command_documentation.py
git commit -m "chore: migrate repo from poetry to uv"
```

## Self-Review Notes

- Spec coverage: packaging, lock file, Ruff replacement, pre-commit, CI, Docker, maintained docs, runtime install hints, and verification are all covered by explicit tasks.
- Placeholder scan: each task contains exact file paths, commands, expected outputs, and concrete content shapes.
- Type consistency: later tasks depend only on the `uv`/Ruff interfaces established in Task 1 and reused consistently as `uv sync --group dev`, `uv run`, `ruff format`, and `ruff check`.
